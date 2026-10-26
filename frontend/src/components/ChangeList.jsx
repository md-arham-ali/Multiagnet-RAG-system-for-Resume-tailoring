import React, { useState } from "react";
import { CHANGE_WAS, CHANGE_NOW, changeRecords, CHANGE_RECORD_MISSING } from "../copy.js";

// The final review's "What changed from your CV": one card per changed line, from
// gate_wait.changes ({node_id, where, before, after, reason, evidence_ids}).

// Past this many word pairs a line is shown whole, without word highlights. A CV
// bullet is under 40 words, so the table is tiny in practice.
const MAX_CELLS = 10000;

// Which words differ between two lines: a longest common subsequence over
// whitespace-split words. Returns null when the lines are too long to compare.
function wordDiff(before, after) {
  const a = before.split(/\s+/).filter(Boolean);
  const b = after.split(/\s+/).filter(Boolean);
  if (a.length * b.length > MAX_CELLS) return null;
  const common = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--)
      common[i][j] = a[i] === b[j] ? common[i + 1][j + 1] + 1 : Math.max(common[i + 1][j], common[i][j + 1]);
  const was = [];
  const now = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      was.push({ word: a[i++], changed: false });
      now.push({ word: b[j++], changed: false });
    } else if (common[i + 1][j] >= common[i][j + 1]) {
      was.push({ word: a[i++], changed: true });
    } else {
      now.push({ word: b[j++], changed: true });
    }
  }
  while (i < a.length) was.push({ word: a[i++], changed: true });
  while (j < b.length) now.push({ word: b[j++], changed: true });
  return { was, now };
}

// `where` is "Section › Entry" for a line under an entry, or just "Section"
// (utils/human_gate.final_changes). Groups keep the order the changes came in.
function groupBySection(changes) {
  const sections = [];
  for (const change of changes) {
    const [section = "", ...rest] = (change.where || "").split(" › ");
    const entry = rest.join(" › ");
    let s = sections.find((x) => x.section === section);
    if (!s) sections.push((s = { section, entries: [] }));
    let e = s.entries.find((x) => x.entry === entry);
    if (!e) s.entries.push((e = { entry, changes: [] }));
    e.changes.push(change);
  }
  return sections;
}

const Words = ({ words, changedClass }) =>
  words.map((t, k) => (
    <React.Fragment key={k}>
      {k > 0 && " "}
      <span className={t.changed ? changedClass : undefined}>{t.word}</span>
    </React.Fragment>
  ));

// One labelled line of a card: "was" or "now", then the text with its changed
// words marked. A new or removed line has nothing to compare, so it shows whole.
function Line({ label, tone, text, words, changedClass, missing }) {
  return (
    <div className="flex gap-2">
      <span className="w-8 shrink-0 text-[#5c5f66]">{label}</span>
      <span className={`min-w-0 ${tone}`}>
        {!text ? missing : words ? <Words words={words} changedClass={changedClass} /> : text}
      </span>
    </div>
  );
}

function ChangeCard({ change, evidenceText }) {
  const [open, setOpen] = useState(false);
  const diff = change.before && change.after ? wordDiff(change.before, change.after) : null;
  const ids = change.evidence_ids || [];
  return (
    <div className="border border-[#26282e] rounded p-2 bg-[#0b0c0e] text-[12px] space-y-0.5">
      <Line
        label={CHANGE_WAS}
        tone="text-[#f87171]/80"
        text={change.before}
        words={diff?.was}
        changedClass="line-through decoration-[#f87171]/60 bg-[#f87171]/10"
        missing="(new line)"
      />
      <Line
        label={CHANGE_NOW}
        tone="text-[#4ade80]"
        text={change.after}
        words={diff?.now}
        changedClass="bg-[#4ade80]/15 underline decoration-[#4ade80]/40"
        missing="(removed)"
      />
      {change.reason && <div className="text-[#85888f] pt-1">why: {change.reason}</div>}
      {ids.length > 0 && (
        <div className="pt-1">
          <button onClick={() => setOpen((o) => !o)} className="text-[#5c5f66] hover:text-[#85888f]">
            {open ? "▾" : "▸"} {changeRecords(ids.length)}
          </button>
          {open && (
            <div className="mt-1 space-y-1 pl-3 border-l border-[#26282e]">
              {ids.map((id) => (
                <div key={id}>
                  <span className="text-[#5c5f66]">{id}</span>
                  {evidenceText[id] != null ? (
                    <div className="text-[#85888f] whitespace-pre-wrap">{evidenceText[id]}</div>
                  ) : (
                    <div className="text-[#5c5f66] italic">{CHANGE_RECORD_MISSING}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// evidenceText: source_id → record text, from this run's own steps (PipelineView).
export default function ChangeList({ changes, evidenceText = {} }) {
  return groupBySection(changes).map((s) => (
    <div key={s.section || "-"} className="space-y-2">
      {s.section && <div className="text-[12px] text-[#85888f] pt-1">{s.section}</div>}
      {s.entries.map((e) => (
        <div key={e.entry || "-"} className="space-y-2">
          {e.entry && <div className="text-[11px] text-[#5c5f66]">{e.entry}</div>}
          {e.changes.map((c) => (
            <ChangeCard key={c.node_id} change={c} evidenceText={evidenceText} />
          ))}
        </div>
      ))}
    </div>
  ));
}
