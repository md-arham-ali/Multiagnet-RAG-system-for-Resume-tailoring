"""
Stage 2 of CV matching: a CVTree -> one LineLink per CV line, against the
`profile` collection (read only). Hybrid search (embeddings + keyword, reranked),
section by section. Explained in context/code_explanations.md, section
`scripts/match_cv_test.py`.

    from utils.cv_handling.cv_match import match_cvs, resolve_pdfs
    results = match_cvs(resolve_pdfs())     # {pdf name: Matcher}, prints + writes JSON
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

import config
from utils.cv_handling.cv_extract import parse_cv, print_parse, short, walk
from utils.cv_handling.cv_ingest import SECTION_TO_KB_TYPE, ingested_pdfs
from state.state import CVNode, CVTree, LineLink, MatchStatus, NodeKind, SectionType
from vectordb.embeddings import Embedder
from vectordb.reranker import Reranker
from vectordb.retriever import Retriever
from vectordb.store import Hit, VectorStore


# =============================================================================
# Settings
# =============================================================================

PROFILE_COLLECTION = "profile"
BULLET_COLLECTION = "profile_bullets"

FETCH = 10
K_CANDIDATES = 5
THRESHOLDS: dict[NodeKind, tuple[float, float]] = {
    NodeKind.ENTRY: (0.50, 0.20),
    NodeKind.ITEM: (0.50, 0.20),
    NodeKind.BULLET: (0.50, 0.20),
}
KEY_EXACT = 0.95
KEY_PROMOTES = {NodeKind.ENTRY: True, NodeKind.ITEM: True, NodeKind.BULLET: False}
TIE_MARGIN = 0.02


# =============================================================================
# Stage 2 tables: CV tree -> profile records
# =============================================================================

TEXT, DOCUMENT = "_text", "_document"
KEY_PAIRS: dict[str, list[tuple[str, str]]] = {
    "work_experience": [("org", "company"), ("role", "role")],
    "project": [("title", "title")],
    "education": [("degree", "degree"), ("degree", "major")],
    "extracurricular": [("activity", "activity")],
    "skill": [(TEXT, "name")],
    "coursework": [(TEXT, "course")],
    "achievement": [(TEXT, DOCUMENT)],
}
KEY_MEAN = {"work_experience"}
ENTRY_QUERY_KEYS = ("role", "title", "tech", "kind", "org", "activity", "institution", "degree")
ITEM_QUERY_PREFIX = {"skill": "Skill: ", "coursework": "Course: ", "achievement": "Achievement: "}
BULLET_SOURCES: list[tuple[str, str, str, list[tuple[str, ...]]]] = [
    ("work_experience", "profile/work_experience.json", "experience_id",
     [("resume_bullets",), ("achievements",)]),
    ("project", "profile/projects.json", "project_id",
     [("resume_material", "one_line"), ("resume_material", "full_bullet_points")]),
    ("extracurricular", "profile/extracurriculars.json", "activity_id",
     [("description",), ("achievements",)]),
    ("education", "profile/education.json", "education_id", [("achievements",)]),
]
DETAIL_FIELDS = {"best_id": "id", "rerank": "rerank", "cosine": "cos", "keyword": "kw", "via": "via",
                 "matched_bullet_id": "bullet_id", "matched_bullet_text": "bullet_text",
                 "bullet_cosine": "bullet_cos", "bullet_keyword": "bullet_kw",
                 "key_score": "key", "exact_key": "exact"}


# =============================================================================
# Stage 2: vectors, bullet index, retriever
# =============================================================================

class VectorTable:
    # One Chroma collection held in memory: ids, texts, metadata and stored vectors.

    def __init__(self, ids: list[str], docs: list[str], metas: list[dict], vecs: np.ndarray) -> None:
        # in : parallel lists of ids, documents, metadata, and a (rows x dim) vector array
        self.ids, self.docs, self.metas, self.vecs = ids, docs, metas, vecs
        self.row = {id_: i for i, id_ in enumerate(ids)}
        by_type: dict[str, list[int]] = {}
        for i, m in enumerate(metas):
            by_type.setdefault(str(m.get("type", "")), []).append(i)
        self._by_type = {t: np.asarray(ix, dtype=int) for t, ix in by_type.items()}

    @classmethod
    def load(cls, collection) -> "VectorTable":
        # Reads a whole Chroma collection into memory.
        # in : collection = a Chroma collection object
        # out: a VectorTable
        res = collection.get(include=["embeddings", "documents", "metadatas"])
        ids = list(res["ids"])
        vecs = np.asarray(res["embeddings"], dtype=np.float32) if ids else np.zeros((0, 0), np.float32)
        return cls(ids, [d or "" for d in res["documents"]], [m or {} for m in res["metadatas"]], vecs)

    def rows(self, kb_type: str) -> np.ndarray:
        # in : kb_type = a record type ("skill", "project", ...)
        # out: row numbers of every record of that type
        return self._by_type.get(kb_type, np.zeros(0, dtype=int))

    def cos_of(self, id_: str, vec: np.ndarray) -> Optional[float]:
        # Cosine between a stored record vector and a query vector.
        # in : id_ = record id, vec = query vector
        # out: cosine (4 dp), or None if the id is not in the table
        i = self.row.get(id_)
        return None if i is None else round(float(self.vecs[i] @ vec), 4)


def dig(record: dict, path: tuple[str, ...]):
    # Follows a key path into nested dicts ("resume_material" -> "one_line").
    # in : record = a dict, path = keys to follow
    # out: the value found, or None
    for p in path:
        record = record.get(p) if isinstance(record, dict) else None
    return record


def collect_bullets(profile_ids: set[str]) -> tuple[list[str], list[str], list[dict]]:
    # Gathers every profile record's own CV bullets from the KB fixture files.
    # in : profile_ids = ids that exist in the profile collection
    # out: (row ids, bullet texts, metadata dicts) for the bullet index
    ids, texts, metas = [], [], []
    for rtype, rel, id_field, paths in BULLET_SOURCES:
        path = config.KB_DIR / rel
        if not path.exists():
            continue
        for rec in json.loads(path.read_text(encoding="utf-8")):
            parent = f"{rtype}:{rec[id_field]}"
            if parent not in profile_ids:
                continue
            found: list[str] = []
            for p in paths:
                v = dig(rec, p)
                found += [v] if isinstance(v, str) else [x for x in (v or []) if isinstance(x, str)]
            for i, t in enumerate(t for t in found if t.strip()):
                ids.append(f"{parent}#b{i}")
                texts.append(t.strip())
                metas.append({"type": rtype, "parent_id": parent, "bullet_index": i})
    return ids, texts, metas


def build_bullet_index(sandbox_store: VectorStore, profile_ids: set[str], rebuild: bool) -> VectorTable:
    # Makes sure the sandbox bullet collection exists and is current, then loads it.
    # in : sandbox_store = store on the sandbox index (config.CV_SANDBOX_DIR), profile_ids = valid parent ids,
    #      rebuild = force a re-embed
    # out: VectorTable of the bullet collection
    ids, texts, metas = collect_bullets(profile_ids)
    if rebuild or sandbox_store.count(BULLET_COLLECTION) != len(ids):
        sandbox_store.reset(BULLET_COLLECTION)
        print(f"embedding {len(ids)} profile bullets into sandbox '{BULLET_COLLECTION}' (one time)")
        for s in range(0, len(ids), 256):
            sandbox_store.add(BULLET_COLLECTION, ids[s:s + 256], texts[s:s + 256], metas[s:s + 256])
    table = VectorTable.load(sandbox_store._collection(BULLET_COLLECTION))
    print(f"profile bullets in sandbox '{BULLET_COLLECTION}': {len(table.ids)}")
    return table


class EmbeddedRetriever(Retriever):
    # The project's Retriever, but semantic() uses vectors the Matcher already computed.

    def __init__(self, store: VectorStore, reranker: Reranker, table: VectorTable) -> None:
        # in : store = where to search, reranker = cross-encoder, table = the same collection in memory
        super().__init__(store=store, reranker=reranker)
        self.table = table
        self.vectors: dict[str, np.ndarray] = {}

    def semantic(self, collection: str, query: str, k: int = 5, where: Optional[dict] = None) -> list[Hit]:
        # Nearest records to the query's pre-computed vector (falls back to embedding it).
        # in : collection = collection name, query = query text, k = how many, where = metadata filter
        # out: list of Hit, best first
        vec = self.vectors.get(query)
        if vec is None:
            return super().semantic(collection, query, k=k, where=where)
        kb_type = (where or {}).get("type")
        k = min(k, len(self.table.rows(kb_type)) if isinstance(kb_type, str) else len(self.table.ids))
        if k <= 0:
            return []
        res = self.store._collection(collection).query(
            query_embeddings=[vec.tolist()], n_results=k, where=where or None)
        return [Hit(id=i, document=d, metadata=m or {}, score=round(1.0 - dist, 4), distance=round(dist, 4))
                for i, d, m, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0],
                                         res["distances"][0])]


# =============================================================================
# Stage 2: scoring helpers
# =============================================================================

@dataclass
class Cand:
    # One profile record as a candidate for one CV line, with its scores.
    id: str
    document: str
    metadata: dict
    rerank: float
    cos: Optional[float]
    kw: Optional[float]
    via: str = "record"
    bullet_id: Optional[str] = None
    bullet_text: Optional[str] = None
    bullet_cos: Optional[float] = None
    bullet_kw: Optional[float] = None
    key: Optional[float] = None
    exact: bool = False


def norm(s: str) -> str:
    # Lowercases and strips punctuation for name comparisons.
    # in : s = any text
    # out: normalised text
    return " ".join(re.sub(r"[^a-z0-9+#.]+", " ", s.lower()).split())


def head(s: str) -> str:
    # Drops parenthesised parts ("Python (Pandas, NumPy)" -> "Python").
    # in : s = any text
    # out: the text without (...)
    return " ".join(re.sub(r"\([^)]*\)", " ", s).split())


def keyword_score(query: str, doc: str) -> float:
    # Word-overlap score, the same measure Retriever.keyword uses.
    # in : query = CV line text, doc = record text
    # out: score 0..1
    from rapidfuzz import fuzz

    return round(fuzz.token_set_ratio(query, doc) / 100.0, 4)


def key_match(node: CVNode, kb_type: str, document: str, metadata: dict) -> tuple[Optional[float], bool]:
    # Compares a CV line's name/title fields with a record's name/title fields.
    # in : node = CV node, kb_type = record type, document/metadata = the record's text and fields
    # out: (fuzzy key score 0..1 or None, True if the names match exactly)
    from rapidfuzz import fuzz

    pairs = KEY_PAIRS.get(kb_type, [])
    scores, exacts = [], []
    for mine, theirs in pairs:
        a = norm(head(node.text) if mine == TEXT else node.attrs.get(mine, ""))
        b = norm(document if theirs == DOCUMENT else str(metadata.get(theirs, "")))
        if not a or not b:
            continue
        if theirs == DOCUMENT:
            scores.append(fuzz.partial_ratio(a, b) / 100.0)
        else:
            scores.append(fuzz.token_set_ratio(a, b) / 100.0)
            exacts.append(fuzz.ratio(a, b) >= KEY_EXACT * 100)
    if not scores:
        return None, False
    if kb_type in KEY_MEAN:
        return round(sum(scores) / len(scores), 4), len(exacts) == len(pairs) and all(exacts)
    return round(max(scores), 4), any(exacts)


def status_for(kind: NodeKind, c: Cand) -> MatchStatus:
    # Grades a chosen candidate as matched / partial / unmatched.
    # in : kind = node kind (sets the thresholds), c = the chosen candidate
    # out: a MatchStatus
    match_min, partial_min = THRESHOLDS[kind]
    if KEY_PROMOTES[kind] and c.exact:
        return MatchStatus.MATCHED if c.rerank >= partial_min else MatchStatus.PARTIAL
    if c.rerank >= match_min:
        return MatchStatus.MATCHED
    return MatchStatus.PARTIAL if c.rerank >= partial_min else MatchStatus.UNMATCHED


def pick(cands: list[Cand], entry_pick: Optional[Cand] = None, bullet: bool = False) -> tuple[Cand, str]:
    # Chooses the record for a line from its ranked candidates.
    # in : cands = candidates, best rerank first; entry_pick = the entry's record (bullets only);
    #      bullet = use the bullet rule (stay with the entry's record unless clearly beaten)
    # out: (chosen candidate, reason text)
    best = cands[0]
    if not bullet:
        exact = [c for c in cands if c.exact]
        return (max(exact, key=lambda c: c.rerank), "exact key match") if exact else (best, "top rerank")
    own = next((c for c in cands if entry_pick is not None and c.id == entry_pick.id), None)
    if own is None:
        return best, "entry unmatched, whole type"
    if own.rerank >= THRESHOLDS[NodeKind.BULLET][0] or round(best.rerank - own.rerank, 4) <= TIE_MARGIN:
        return own, "entry's record"
    return best, "another record beats the entry's"


def plan_jobs(tree: CVTree) -> tuple[list[tuple[CVNode, str]], list[str]]:
    # Lists every node to match with its section's record type, in tree order.
    # in : tree = the parsed CV tree
    # out: ([(node, kb_type), ...], ids of nodes skipped because their section is not matched)
    jobs, skipped = [], []
    for section in tree.root.children:
        kb_type = SECTION_TO_KB_TYPE.get(section.section_type)
        if kb_type is None:
            skipped += [n.node_id for n in walk(section) if n is not section]
            continue
        for child in section.children:
            if child.kind == NodeKind.ENTRY and section.section_type == SectionType.SKILLS:
                jobs += [(item, kb_type) for item in child.children]
            else:
                jobs.append((child, kb_type))
                if child.kind == NodeKind.ENTRY:
                    jobs += [(b, kb_type) for b in child.children]
    return jobs, skipped


# =============================================================================
# Stage 2: matcher
# =============================================================================

class Matcher:
    # Links every CV node to profile records: embed, hybrid search, pick, grade.

    def __init__(self, embedder: Embedder, reranker: Reranker, profile: VectorTable, bullets: VectorTable,
                 profile_retr: EmbeddedRetriever, bullet_retr: EmbeddedRetriever, k: int) -> None:
        # in : models, the two in-memory tables, the two retrievers, k = candidates to report
        self.embedder, self.reranker = embedder, reranker
        self.profile, self.bullets = profile, bullets
        self.profile_retr, self.bullet_retr = profile_retr, bullet_retr
        self.k = k
        self.vectors: dict[str, np.ndarray] = {}
        self.links: dict[str, LineLink] = {}
        self.details: dict[str, dict] = {}
        self.skipped: list[str] = []
        self.out_of_scope: Counter = Counter()

    @staticmethod
    def query_for(node: CVNode, kb_type: str) -> str:
        # Builds the search text for a node.
        # in : node = CV node, kb_type = its section's record type
        # out: query text (entry header parts, prefixed item, or bullet text)
        if node.kind == NodeKind.ENTRY:
            return " ".join(node.attrs[k] for k in ENTRY_QUERY_KEYS if node.attrs.get(k)) or node.text
        if node.kind == NodeKind.ITEM:
            return ITEM_QUERY_PREFIX.get(kb_type, "") + node.text
        return node.text

    def embed_lines(self, queries: dict[str, str]) -> None:
        # Embeds every non-empty query in one batch and hands the vectors to both retrievers.
        # in : queries = {node_id: query text}
        todo = [nid for nid, q in queries.items() if re.search(r"\w", q)]
        if not todo:
            return
        vecs = np.asarray(self.embedder.embed([queries[n] for n in todo]), dtype=np.float32)
        for nid, v in zip(todo, vecs):
            self.vectors[nid] = v
            self.profile_retr.vectors[queries[nid]] = v
            self.bullet_retr.vectors[queries[nid]] = v
        print(f"embedded {len(todo)} CV lines in one batch ({vecs.shape[1]}-d)")

    def in_scope(self, metadata: Optional[dict], kb_type: str) -> bool:
        # Keeps a result only if its record type is the section's type; counts drops.
        # in : metadata = a result's metadata, kb_type = the section's type
        # out: True to keep it
        if (metadata or {}).get("type") == kb_type:
            return True
        self.out_of_scope[kb_type] += 1
        return False

    def search(self, retr: EmbeddedRetriever, collection: str, query: str, kb_type: str) -> list[Hit]:
        # Hybrid search (semantic + keyword, reranked) inside one record type.
        # in : retr = retriever to use, collection = collection name, query = text, kb_type = type
        # out: in-scope hits with rerank scores
        hits = retr.hybrid(collection, query, k=2 * FETCH, fetch=FETCH, where={"type": kb_type})
        return [h for h in hits if self.in_scope(h.metadata, kb_type)]

    def cand(self, rid: str, query: str, vec: np.ndarray, rerank: float) -> Cand:
        # Builds a candidate for a profile record, with its cosine and keyword scores.
        # in : rid = profile record id, query = line text, vec = line vector, rerank = rerank score
        # out: a Cand
        i = self.profile.row[rid]
        return Cand(rid, self.profile.docs[i], self.profile.metas[i], rerank=rerank,
                    cos=self.profile.cos_of(rid, vec), kw=keyword_score(query, self.profile.docs[i]))

    def record_pool(self, query: str, vec: np.ndarray, kb_type: str) -> dict[str, Cand]:
        # Candidates from the hybrid search over the profile records of one type.
        # in : query = line text, vec = line vector, kb_type = type
        # out: {record id: Cand}
        return {h.id: self.cand(h.id, query, vec, float(h.rerank_score))
                for h in self.search(self.profile_retr, PROFILE_COLLECTION, query, kb_type)
                if h.id in self.profile.row}

    def add_keys(self, pool: dict[str, Cand], node: CVNode, query: str, vec: np.ndarray, kb_type: str) -> None:
        # Scores names on the pool and adds any exact-name record the search missed (reranked).
        # in : pool = candidates so far (changed in place), node = CV node, query/vec = line text/vector
        for c in pool.values():
            c.key, c.exact = key_match(node, kb_type, c.document, c.metadata)
        extra = []
        for i in self.profile.rows(kb_type):
            rid = self.profile.ids[i]
            if rid in pool:
                continue
            key, exact = key_match(node, kb_type, self.profile.docs[i], self.profile.metas[i])
            if exact:
                c = self.cand(rid, query, vec, 0.0)
                c.key, c.exact = key, exact
                extra.append(c)
        for c, s in zip(extra, self.reranker.score(query, [c.document for c in extra]) if extra else []):
            c.rerank = round(s, 4)
            pool[c.id] = c

    def add_bullet_evidence(self, pool: dict[str, Cand], query: str, vec: np.ndarray, kb_type: str) -> None:
        # Lets a record score through its own CV bullets when one reranks higher than its summary.
        # in : pool = candidates so far (changed in place), query/vec = bullet text/vector, kb_type = type
        for h in self.search(self.bullet_retr, BULLET_COLLECTION, query, kb_type):
            parent = (h.metadata or {}).get("parent_id")
            i = self.profile.row.get(parent)
            if i is None or not self.in_scope(self.profile.metas[i], kb_type):
                continue
            c = pool.get(parent) or pool.setdefault(parent, self.cand(parent, query, vec, -1.0))
            if h.rerank_score > c.rerank:
                c.rerank, c.via = float(h.rerank_score), "bullet"
                c.bullet_id, c.bullet_text = h.id, h.document
                c.bullet_cos = self.bullets.cos_of(h.id, vec)
                c.bullet_kw = keyword_score(query, h.document or "")

    def emit(self, node: CVNode, query: str, chosen: Optional[Cand], cands: list[Cand],
             status: MatchStatus, reason: str) -> None:
        # Records the result for one node: its LineLink and the score details.
        # in : node, query, chosen candidate (or None), ranked candidates, status, reason text
        partial_min = THRESHOLDS[node.kind][1]
        ids = [] if chosen is None or status == MatchStatus.UNMATCHED else (
            [chosen.id] + [c.id for c in cands if c.id != chosen.id and c.rerank >= partial_min])
        self.links[node.node_id] = LineLink(
            node_id=node.node_id, kind=node.kind, section_type=node.section_type, text=node.text,
            status=status, source_ids=ids, score=chosen.rerank if chosen else 0.0)
        shown = cands[: self.k] + [c for c in cands[self.k:] if c.exact or c is chosen]
        details = {"reason": reason, "query": query,
                   **{k: getattr(chosen, a) if chosen else None for k, a in DETAIL_FIELDS.items()},
                   "compared": len(cands),
                   "candidates": [{"id": c.id, "rerank": c.rerank, "cosine": c.cos, "keyword": c.kw,
                                   "via": c.via, "exact": c.exact} for c in shown]}
        details["exact_key"] = bool(details["exact_key"])
        self.details[node.node_id] = details

    def match(self, node: CVNode, kb_type: str, query: str, entry_pick: Optional[Cand]) -> Optional[Cand]:
        # Matches one node (entry, item or bullet) against its section's records.
        # in : node, kb_type, query = its search text, entry_pick = its entry's record (bullets)
        # out: the chosen candidate if not unmatched, else None
        vec = self.vectors[node.node_id]
        bullet = node.kind == NodeKind.BULLET
        pool = self.record_pool(query, vec, kb_type)
        if bullet:
            self.add_bullet_evidence(pool, query, vec, kb_type)
        else:
            self.add_keys(pool, node, query, vec, kb_type)
        if not pool:
            self.emit(node, query, None, [], MatchStatus.UNMATCHED, f"no '{kb_type}' records in the profile")
            return None
        cands = sorted(pool.values(), key=lambda c: (-c.rerank, c.id))
        chosen, how = pick(cands, entry_pick, bullet)
        via = f" (via {chosen.via})" if bullet else ""
        status = status_for(node.kind, chosen)
        self.emit(node, query, chosen, cands, status, f"{how}{via}, {len(cands)} '{kb_type}' candidates reranked")
        return chosen if status != MatchStatus.UNMATCHED else None

    def run(self, tree: CVTree) -> None:
        # Stage 2 entry point: embeds all lines, then matches each node in tree order.
        # in : tree = the parsed CV tree (results land in self.links / self.details)
        jobs, self.skipped = plan_jobs(tree)
        queries = {n.node_id: self.query_for(n, t) for n, t in jobs}
        self.embed_lines(queries)
        entry_pick: Optional[Cand] = None
        for node, kb_type in jobs:
            query = queries[node.node_id]
            if node.node_id in self.vectors:
                chosen = self.match(node, kb_type, query, entry_pick)
            else:
                chosen = None
                self.emit(node, query, None, [], MatchStatus.UNMATCHED, "empty query")
            if node.kind == NodeKind.ENTRY:
                entry_pick = chosen


# =============================================================================
# Output
# =============================================================================

def num(x: Optional[float]) -> str:
    # Formats a score, or "-" when missing.
    # in : x = a number or None
    # out: two-decimal text
    return f"{x:.2f}" if x is not None else "  - "


def row(label: str, kind: str, status: str = "", score: Optional[float] = None, cos: Optional[float] = None,
        kw: Optional[float] = None, flags: str = "", best: str = "", text: str = "") -> str:
    # Formats one printed result row (scores left blank when there are none).
    # in : the row's columns
    # out: one aligned line of text
    nums = f"{score:>5.3f} {num(cos):>4} {num(kw):>4}" if score is not None else " " * 15
    return f"{label:<24} {kind:<6} {status:<9} {nums} {flags:<2} {short(best, 40):<40} {short(text, 60)}"


def print_matches(tree: CVTree, m: Matcher) -> None:
    # Prints the tree with each line's status, scores and chosen record.
    # in : tree = parsed tree, m = the matcher after run()
    thresholds = ", ".join(f"{k.value} {a:.2f}/{b:.2f}" for k, (a, b) in THRESHOLDS.items())
    print(f"\n=== match: {tree.source_file}  (rerank match/partial: {thresholds}, PROVISIONAL)")
    print("    columns: status  rerank  cos  kw  flags  best id  text")
    print("    flags: = exact key   b = scored via the record's own bullet (cos/kw are then the bullet's)")
    skipped = set(m.skipped)
    for node in walk(tree.root):
        if node.kind == NodeKind.CV:
            continue
        pad = "  " * (node.depth - 1)
        if node.kind == NodeKind.SECTION:
            kb = SECTION_TO_KB_TYPE.get(node.section_type)
            scope = (f"matched only against '{kb}' records ({len(m.profile.rows(kb))} in profile, "
                     f"{len(m.bullets.rows(kb))} of their bullets)") if kb else "not matched"
            print(f"\n{pad}[{node.node_id}] {node.title}  -> {scope}")
            continue
        label = f"{pad}{node.node_id}"
        link = m.links.get(node.node_id)
        if node.node_id in skipped:
            print(row(label, node.kind.value, "skipped", text=node.text))
        elif link is None:
            print(row(label, "group", text=node.text))
        else:
            d = m.details[node.node_id]
            b = d["via"] == "bullet"
            print(row(label, node.kind.value, link.status.value, link.score,
                      d["bullet_cosine"] if b else d["cosine"], d["bullet_keyword"] if b else d["keyword"],
                      ("=" if d["exact_key"] else "") + ("b" if b else ""), d["best_id"] or "-", node.text))


def print_summary(tree: CVTree, m: Matcher) -> None:
    # Prints status counts per section and the three safety checks.
    # in : tree = parsed tree, m = the matcher after run()
    print(f"\n=== summary: {tree.source_file}")
    print(f"  {'section':<20} {'profile type':<16} {'matched':>8} {'partial':>8} {'unmatched':>10} {'skipped':>8}")
    skipped, totals, cross = set(m.skipped), Counter(), []
    for sec in tree.root.children:
        kb = SECTION_TO_KB_TYPE.get(sec.section_type)
        c = Counter()
        for n in walk(sec):
            if n is sec:
                continue
            if n.node_id in skipped:
                c["skipped"] += 1
            elif n.node_id in m.links:
                link = m.links[n.node_id]
                c[link.status.value] += 1
                cross += [(n.node_id, sid) for sid in link.source_ids
                          if sid not in m.profile.row or m.profile.metas[m.profile.row[sid]].get("type") != kb]
        totals.update(c)
        print(f"  {sec.node_id:<20} {kb or '-':<16} {c['matched']:>8} {c['partial']:>8} "
              f"{c['unmatched']:>10} {c['skipped']:>8}")
    print(f"  {'TOTAL':<20} {'':<16} {totals['matched']:>8} {totals['partial']:>8} "
          f"{totals['unmatched']:>10} {totals['skipped']:>8}")
    print(f"  every link stays in its section's type: {'OK' if not cross else f'BROKEN {cross[:5]}'}")
    dropped = sum(m.out_of_scope.values())
    print(f"  out-of-section candidates dropped: {dropped}"
          f"{'' if not dropped else f'  {dict(m.out_of_scope)} (type filter slipped)'}")
    missing = [n.node_id for n, _ in plan_jobs(tree)[0] if n.node_id not in m.links]
    print(f"  every matchable node has one link: {'OK' if not missing else f'MISSING {missing}'}")


def display_path(path: Path) -> str:
    # Shows a path relative to the project when it is inside it.
    # in : path = any path
    # out: "test_work/cv_match/x.json" style text, or the absolute path
    try:
        return str(Path(path).resolve().relative_to(config.BASE_DIR))
    except ValueError:
        return str(path)


def write_outputs(tree: CVTree, m: "Matcher", out_dir: Path = config.CV_MATCH_DIR) -> list[Path]:
    # Writes the parsed tree and the links (with all scores) as JSON files.
    # in : tree = parsed tree, m = the matcher after run(), out_dir = folder to write into
    # out: [tree json path, links json path]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(tree.source_file).stem
    payload = {
        "source_file": tree.source_file,
        "collection": PROFILE_COLLECTION,
        "bullet_collection": BULLET_COLLECTION,
        "scoring": "Retriever.hybrid (semantic + keyword, merged, reranked); status on rerank",
        "thresholds": {
            **{k.value: {"match_min": a, "partial_min": b} for k, (a, b) in THRESHOLDS.items()},
            "FETCH": FETCH, "KEY_EXACT": KEY_EXACT,
            "KEY_PROMOTES": {k.value: v for k, v in KEY_PROMOTES.items()},
            "TIE_MARGIN": TIE_MARGIN, "provisional": True,
        },
        "links": {nid: link.model_dump(mode="json") for nid, link in m.links.items()},
        "details": m.details,
        "skipped": m.skipped,
        "section_scope": {s.value: t for s, t in SECTION_TO_KB_TYPE.items()},
        "out_of_section_dropped": dict(m.out_of_scope),
    }
    files = {out_dir / f"{stem}.tree.json": tree.model_dump_json(indent=2),
             out_dir / f"{stem}.links.json": json.dumps(payload, indent=2, ensure_ascii=False)}
    for path, text in files.items():
        path.write_text(text, encoding="utf-8")
    return list(files)


# =============================================================================
# Callable entry points
# =============================================================================

def resolve_pdfs(pdf: Optional[str] = None, input_dir: Path = config.CV_INPUT_DIR,
                 index_dir: Path = config.CV_SANDBOX_DIR) -> list[Path]:
    # Decides which CV PDFs to match.
    # in : pdf = one file name or path (None = every CV in the sandbox index),
    #      input_dir = folder the CVs live in, index_dir = sandbox Chroma folder
    # out: list of existing PDF paths (empty if none)
    input_dir = Path(input_dir)
    if pdf:
        p = Path(pdf)
        pdfs = [p if p.exists() else input_dir / pdf]
    else:
        names = ingested_pdfs(index_dir)
        if not names:
            print("Sandbox index is empty. Run scripts/ingest_pdfs_test.py first.")
        pdfs = [input_dir / n for n in names]
    for p in pdfs:
        if not p.exists():
            print(f"  ! not found, skipped: {p}")
    return [p for p in pdfs if p.exists()]


def load_matcher_parts(rebuild_bullets: bool = False, index_dir: Path = config.CV_SANDBOX_DIR) -> Optional[tuple]:
    # Loads the models, the profile vectors and the bullet index, and builds both retrievers.
    # in : rebuild_bullets = force a re-embed of the bullet collection, index_dir = sandbox Chroma folder
    # out: (embedder, reranker, profile table, bullet table, profile retriever, bullet retriever),
    #      or None if the profile index is missing or built with another model
    embedder = Embedder()
    store = VectorStore(embedder=embedder)
    if store.count(PROFILE_COLLECTION) == 0:
        print(f"\nProfile collection '{PROFILE_COLLECTION}' is empty. Build it first (scripts/build_vectordb.py).")
        return None
    profile = VectorTable.load(store._collection(PROFILE_COLLECTION))
    if profile.vecs.shape[1] != embedder.dim:
        print(f"\nIndex vectors are {profile.vecs.shape[1]}-d but {config.EMBEDDING_MODEL} gives "
              f"{embedder.dim}-d: the index was built with another model. Rebuild it.")
        return None
    print(f"\nprofile records in '{PROFILE_COLLECTION}': {len(profile.ids)} "
          f"({profile.vecs.shape[1]}-d, read from the DB)")
    sandbox = VectorStore(embedder=embedder, persist_dir=index_dir)
    bullets = build_bullet_index(sandbox, set(profile.ids), rebuild_bullets)
    reranker = Reranker()
    return (embedder, reranker, profile, bullets,
            EmbeddedRetriever(store, reranker, profile), EmbeddedRetriever(sandbox, reranker, bullets))


def match_cvs(pdfs: list[Path], k: int = K_CANDIDATES, rebuild_bullets: bool = False,
              out_dir: Optional[Path] = config.CV_MATCH_DIR, index_dir: Path = config.CV_SANDBOX_DIR,
              report: bool = True) -> Optional[dict[str, "Matcher"]]:
    # Runs the whole pipeline for a list of CVs: parse, load models, match, report, write.
    # in : pdfs = CV paths, k = candidates reported per line, rebuild_bullets = re-embed bullets,
    #      out_dir = where JSON goes (None = write nothing), index_dir = sandbox Chroma folder,
    #      report = print the parse / match / summary tables
    # out: {pdf file name: Matcher with .links and .details}, or None if the profile index is unusable
    parsed = []
    for pdf in pdfs:
        tree, lines = parse_cv(Path(pdf))
        if report:
            print_parse(tree, lines)
        parsed.append(tree)
    parts = load_matcher_parts(rebuild_bullets, index_dir)
    if parts is None:
        return None
    results: dict[str, Matcher] = {}
    for tree in parsed:
        m = Matcher(*parts, k=k)
        m.run(tree)
        if report:
            print_matches(tree, m)
            print_summary(tree, m)
        if out_dir is not None:
            for path in write_outputs(tree, m, out_dir):
                print(f"  wrote {display_path(path)}")
        results[tree.source_file] = m
    return results
