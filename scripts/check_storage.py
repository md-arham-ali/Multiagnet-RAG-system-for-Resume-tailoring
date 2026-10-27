#!/usr/bin/env python3
"""
Data Storage + Handling checks that pytest's fakes cannot make.

    .venv/bin/python scripts/check_storage.py            # --scan: integrity of the REAL data, read-only
    .venv/bin/python scripts/check_storage.py --stress   # races and crashes, in a temp dir only

--scan reads knowledge_base/, logs/, outputs/ and uploads/ and changes nothing:
every JSON file parses, no torn `.tmp` file is left behind, ids are unique,
auth records agree with each other, every run log's export points at real files,
every CV index points at real PDFs, and the checkpoint database passes SQLite's
integrity check.

--stress points the writers at a temp dir and hammers them with real threads and
a real `kill -9`: what the strict xfails in tests/test_backend_auth.py pin with
injected interleavings, measured here as records actually lost. A check pinned to
an open bug reports ⚠ (with the bug number) and never fails the run.

Exits non-zero if a check fails.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config

PASS, FAIL, KNOWN = "\033[32m✓\033[0m", "\033[31m✗\033[0m", "\033[33m⚠\033[0m"
_failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _failures
    if not ok:
        _failures += 1
    print(f"  {PASS if ok else FAIL} {label}{'' if ok else f'  -> {detail}'}")


def known(label: str, ok: bool, ref: str, detail: str = "") -> None:
    print(f"  {PASS if ok else KNOWN} {label}{'' if ok else f'  -> still open ({ref}) {detail}'}")


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)


# ----------------------------------------------------------------------------- scan
def scan() -> None:
    kb = config.KB_DIR
    print("\n1. every knowledge_base JSON / JSONL file parses as UTF-8")
    files = [p for p in kb.rglob("*") if p.is_file() and p.suffix in (".json", ".jsonl")
             and "chroma" not in p.parts]
    bad = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
            if p.suffix == ".json":
                json.loads(text) if text.strip() else None
            else:
                for line in text.splitlines():
                    if line.strip():
                        json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            bad.append(f"{rel(p)}: {type(exc).__name__}")
    check(f"{len(files)} files parse", not bad, "; ".join(bad[:5]))
    empty = [rel(p) for p in files if p.suffix == ".json" and p.stat().st_size == 0]   # an empty .jsonl log is valid
    check("no zero-byte .json file", not empty, str(empty[:5]))

    print("\n2. no torn temp file left behind by a crashed write")
    roots = [kb, config.BASE_DIR / "logs", config.OUTPUTS_DIR, config.CV_UPLOADS_DIR]
    tmps = [rel(p) for r in roots if r.exists() for p in r.rglob("*.tmp")]
    check("no *.tmp under knowledge_base/, logs/, outputs/, uploads/", not tmps, str(tmps[:5]))

    print("\n3. profile records: unique ids per file")
    for p in sorted((kb / "profile").glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8") or "[]")
        rows = data if isinstance(data, list) else data.get("records", []) if isinstance(data, dict) else []
        key = next((k for k in (rows[0] if rows and isinstance(rows[0], dict) else {}) if k == "id" or k.endswith("_id")), None)
        ids = [r.get(key) for r in rows if isinstance(r, dict)] if key else []
        dupes = [i for i, n in Counter(ids).items() if n > 1]
        check(f"{p.name}: {len(rows)} records, ids unique ({key})", not dupes, f"duplicates {dupes[:5]}")

    print("\n4. manual_entries.json: ownership and leftovers")
    entries = json.loads((kb / "profile" / "manual_entries.json").read_text(encoding="utf-8") or "[]")
    ownerless = [e["id"] for e in entries if not e.get("owner") and e.get("section") == "gap_answers"]
    known("every gap answer carries an owner", not ownerless,
          "Data Storage role file, 'gate-2 answers are missing from a user's own export'", f"{len(ownerless)} ownerless")
    tests = [e["id"] for e in entries if "UITEST" in json.dumps(e) or "delete me" in json.dumps(e)]
    known("no test entry left in the shared pool", not tests, "#119 item 4 (no delete route)", str(tests))

    print("\n5. auth records agree with each other")
    auth = config.KB_AUTH_DIR
    tokens = json.loads((auth / "tokens.json").read_text(encoding="utf-8") or "[]")
    profiles = json.loads((auth / "profiles.json").read_text(encoding="utf-8") or "[]")
    requests = json.loads((auth / "requests.json").read_text(encoding="utf-8") or "[]")
    check("token ids unique", len({t["id"] for t in tokens}) == len(tokens))
    check("raw tokens unique", len({t["token"] for t in tokens}) == len(tokens))
    pids = {p["profile_id"] for p in profiles}
    check("profile ids unique", len(pids) == len(profiles))
    names = Counter(p["identifier_norm"] for p in profiles)
    check("profile names unique", not [n for n, c in names.items() if c > 1], str([n for n, c in names.items() if c > 1][:5]))
    dangling = [t["id"] for t in tokens if t.get("profile_id") and t["profile_id"] not in pids]
    check("every token's profile_id exists", not dangling, str(dangling[:5]))
    legacy = [t["id"] for t in tokens if not t.get("profile_id")]
    print(f"    ({len(tokens)} tokens, {len(profiles)} profiles, {len(legacy)} legacy tokens not yet backfilled, "
          f"{sum(r.get('status') == 'pending' for r in requests)} pending requests)")
    approved_ghosts = [r["id"] for r in requests if r.get("status") == "approved" and r.get("token_id")
                       and r["token_id"] not in {t["id"] for t in tokens}]
    check("every approved request points at a live token", not approved_ghosts, str(approved_ghosts[:5]))

    print("\n6. run logs and the files they point at")
    from backend.runs import registry
    logs = sorted(config.RUNS_DIR.glob("*.json"))
    broken, missing, referenced = [], [], set()
    for p in logs:
        try:
            record = json.loads(p.read_text(encoding="utf-8"))
            assert isinstance(record, dict) and isinstance(record.get("events"), list)
        except Exception as exc:
            broken.append(f"{p.name}: {type(exc).__name__}")
            continue
        for relative in registry.current_export(record).values():
            target = config.OUTPUTS_DIR / relative
            referenced.add(target.resolve())
            if not target.exists():
                missing.append(f"{p.stem} -> {relative}")
    check(f"{len(logs)} run logs are objects with an events list", not broken, "; ".join(broken[:5]))
    check("every saved-CV pointer resolves to a file", not missing, "; ".join(missing[:5]))
    outputs = [p for p in config.OUTPUTS_DIR.rglob("*") if p.is_file() and p.suffix in (".md", ".txt")
               and p.parent != config.OUTPUTS_DIR] if config.OUTPUTS_DIR.exists() else []
    orphans = [rel(p) for p in outputs if p.resolve() not in referenced]
    print(f"    ({len(outputs)} exported files under outputs/<owner>/, {len(orphans)} not referenced by any run log"
          f"{': ' + ', '.join(orphans[:4]) if orphans else ''})")

    print("\n7. CV uploads: index and files agree")
    gaps = []
    for index in sorted(config.CV_UPLOADS_DIR.glob("*/cv/index.json")) if config.CV_UPLOADS_DIR.exists() else []:
        data = json.loads(index.read_text(encoding="utf-8") or "{}")
        named = set()

        def walk(node):
            if isinstance(node, dict):
                if isinstance(node.get("stored_name"), str):
                    named.add(node["stored_name"])
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(data)
        on_disk = {p.name for p in index.parent.iterdir() if p.name != "index.json"}
        if named - on_disk:
            gaps.append(f"{index.parent.parent.name}: indexed, no file {sorted(named - on_disk)}")
        if on_disk - named:
            gaps.append(f"{index.parent.parent.name}: file, not indexed {sorted(on_disk - named)}")
    check("every indexed CV exists and every PDF is indexed", not gaps, "; ".join(gaps[:4]))

    print("\n8. the checkpoint database")
    db = Path(config.CHECKPOINT_DB)
    if db.exists():
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
            result = con.execute("PRAGMA integrity_check").fetchone()[0]
        check(f"{rel(db)} integrity_check ({db.stat().st_size / 1e6:.1f} MB)", result == "ok", result)
    else:
        print(f"    ({rel(db)} not present)")

    print("\n9. the log plane")
    bad = []
    lp = config.BASE_DIR / "logs" / "logplane"
    for p in sorted(lp.glob("*.jsonl")) if lp.exists() else []:
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            try:
                json.loads(line)
            except json.JSONDecodeError:
                bad.append(f"{p.name}:{n}")
    check("every log-plane line parses", not bad, str(bad[:5]))


# ----------------------------------------------------------------------------- stress
class _NoIndex:
    """Stands in for the profile VectorStore: the race is in the JSON file."""
    def upsert(self, *a, **k):
        pass

    def add(self, *a, **k):
        pass


def _hammer(n_threads: int, fn) -> list[BaseException]:
    errors: list[BaseException] = []
    barrier = threading.Barrier(n_threads)

    def run(i):
        barrier.wait(timeout=10)
        try:
            fn(i)
        except BaseException as exc:   # noqa: BLE001 - counted, reported
            errors.append(exc)
    threads = [threading.Thread(target=run, args=(i,), daemon=True) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return errors


_KILL_CHILD = """
import sys, json
sys.path.insert(0, sys.argv[2])
from backend.jsonstore import write_json
from pathlib import Path
p, i = Path(sys.argv[1]), 0
while True:
    i += 1
    write_json(p, [{"i": i, "pad": "x" * 2000} for _ in range(200)])
"""


def stress() -> None:
    from backend import jsonstore
    from learning import profile_store, store as learning_store

    tmp = Path(tempfile.mkdtemp(prefix="check-storage-"))
    print(f"\n(working in {tmp})")
    config.KB_LEARNING_DIR = tmp / "learning"
    learning_store.config.KB_LEARNING_DIR = config.KB_LEARNING_DIR

    print("\n10. learning store: 16 threads x 10 corrections, one file")
    errs = _hammer(16, lambda i: [learning_store.save_correction("critic", f"o{i}-{k}", f"c{i}-{k}", "r")
                                  for k in range(10)])
    saved = len(learning_store.load_learning("critic").get("corrections", []))
    known(f"no correction lost ({saved}/160 kept, {len(errs)} errors)", saved == 160 and not errs,
          "audit #12 / #35 (corrections.json)", f"{160 - saved} lost; {Counter(type(e).__name__ for e in errs)}")

    print("\n11. jsonstore.write_json: 8 threads x 50 writes, one path")
    target = tmp / "shared.json"
    errs = _hammer(8, lambda i: [jsonstore.write_json(target, {"writer": i, "k": k}) for k in range(50)])
    try:
        json.loads(target.read_text(encoding="utf-8"))
        parses = True
    except Exception:
        parses = False
    check("the file parses after the storm", parses)
    known(f"no writer crashed ({len(errs)} errors)", not errs, "#62 item 1 (one shared .tmp name)",
          str(Counter(type(e).__name__ for e in errs)))

    print("\n12. jsonstore.update_json: 16 threads x 25 increments")
    counter = tmp / "counter.json"
    _hammer(16, lambda i: [jsonstore.update_json(counter, lambda v: ((v or 0) + 1, None), default=0)
                           for _ in range(25)])
    total = json.loads(counter.read_text(encoding="utf-8"))
    check(f"the per-path lock keeps every increment ({total}/400)", total == 400)

    print("\n13. manual_entries.json: save_gap_answers racing update_json (8 + 8 threads x 5)")
    profile_store.MANUAL_ENTRIES = tmp / "manual_entries.json"
    jsonstore.write_json(profile_store.MANUAL_ENTRIES, [])

    def writer(i):
        for k in range(5):
            if i % 2:
                profile_store.save_gap_answers([{"requirement": "SQL", "content": f"gap {i}-{k}"}], store=_NoIndex())
            else:
                jsonstore.update_json(profile_store.MANUAL_ENTRIES,
                                      lambda v, i=i, k=k: ((v or []) + [{"id": f"ui{i}-{k}"}], None), default=[])
    errs = _hammer(16, writer)
    try:
        kept = len(json.loads(profile_store.MANUAL_ENTRIES.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        kept = None
    check("manual_entries.json still parses", kept is not None, "the file was torn (#62 item 1)")
    known(f"no entry lost ({kept}/80 kept, {len(errs)} errors)", kept == 80 and not errs, "#35",
          f"{80 - (kept or 0)} lost; {Counter(type(e).__name__ for e in errs)}")

    print("\n14. kill -9 in the middle of write_json, 15 times")
    victim = tmp / "victim.json"
    torn = 0
    for _ in range(15):
        child = subprocess.Popen([sys.executable, "-c", _KILL_CHILD, str(victim), str(ROOT)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(random.Random(_).uniform(0.4, 1.2))
        os.kill(child.pid, signal.SIGKILL)
        child.wait(timeout=10)
        if victim.exists():
            try:
                json.loads(victim.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                torn += 1
    check(f"the file always parses after a kill ({15 - torn}/15)", torn == 0)
    orphans = list(tmp.glob(f".{victim.name}.*.tmp"))
    print(f"    ({len(orphans)} orphaned temp file(s) after 15 kills: a write killed between mkstemp and the"
          f" rename leaves one; nothing deletes it, and section 2 of --scan flags any in the real folders)")
    check("a rewritten file keeps its mode (0644, not mkstemp's 0600)", (victim.stat().st_mode & 0o777) == 0o644,
          oct(victim.stat().st_mode & 0o777))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stress", action="store_true", help="races and crashes in a temp dir (no real data touched)")
    args = parser.parse_args()
    stress() if args.stress else scan()
    print(f"\n{'ALL CHECKS PASSED' if not _failures else f'{_failures} CHECK(S) FAILED'}\n")
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())
