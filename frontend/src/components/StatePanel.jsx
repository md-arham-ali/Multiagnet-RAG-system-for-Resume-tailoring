import React from "react";
import { AGENT_TITLES } from "./AgentGraph.jsx";
import { STUB_NOTE } from "../copy.js";

// ---------- small shared pieces ----------
const Chip = ({ children, tone = "default" }) => (
  <span
    className={`inline-block px-1.5 py-0.5 mr-1 mb-1 rounded text-[11px] border ${
      tone === "must"
        ? "border-[#e8b44c]/40 text-[#e8b44c]"
        : tone === "bad"
        ? "border-[#f87171]/40 text-[#f87171]"
        : tone === "good"
        ? "border-[#4ade80]/40 text-[#4ade80]"
        : "border-[#26282e] text-[#85888f]"
    }`}
  >
    {children}
  </span>
);

const Row = ({ label, children }) => (
  <div className="flex gap-2 py-0.5 text-[12px]">
    <span className="text-[#5c5f66] w-32 shrink-0">{label}</span>
    <span className="text-[#d7d9de] min-w-0">{children}</span>
  </div>
);

const Pct = ({ value }) => (
  <span className="inline-flex items-center gap-2">
    <span className="w-24 h-1 bg-[#26282e] rounded inline-block">
      <span
        className="h-1 bg-[#4ade80] rounded block"
        style={{ width: `${Math.round((value || 0) * 100)}%` }}
      />
    </span>
    {Math.round((value || 0) * 100)}%
  </span>
);

const LINK_TONE = { matched: "good", unmatched: "bad" };
const LINK_WORD = { matched: "backed", partial: "partly", unmatched: "not found" };

// cv_link's per-line view, grouped under the CV's own section headings. A
// line's node_id starts with its section's id ("experience.0.b2").
function CvLines({ tree, links }) {
  const titles = Object.fromEntries((tree?.root?.children || []).map((s) => [s.node_id, s.title]));
  const sections = new Map();
  for (const l of links) {
    const id = String(l.node_id || "").split(".")[0];
    if (!sections.has(id)) sections.set(id, []);
    sections.get(id).push(l);
  }
  return (
    <div className="mt-3 space-y-3">
      {[...sections].map(([id, lines]) => (
        <div key={id}>
          <div className="text-[11px] text-[#85888f] mb-1">{titles[id] || lines[0].section_type || id}</div>
          {lines.map((l, i) => (
            <div key={l.node_id || i} className={`flex gap-2 py-0.5 text-[12px] ${l.kind === "bullet" ? "pl-4" : ""}`}>
              <span className="shrink-0">
                <Chip tone={LINK_TONE[l.status]}>{LINK_WORD[l.status] || l.status}</Chip>
              </span>
              <span className="min-w-0">
                <span className="text-[#d7d9de]">{l.text}</span>
                {l.source_ids?.length > 0 && (
                  <span className="block text-[11px] text-[#5c5f66]">{l.source_ids.join(", ")}</span>
                )}
              </span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

// ---------- one renderer per agent artifact (shared with GateScreen/Drawer) ----------
// `detail` is set by the drawer only, for artifacts too long to show in full on a card.
export function renderArtifact(node, artifact, { detail = false } = {}) {
  if (!artifact) return <div className="text-[#5c5f66] text-[12px]">no output yet</div>;
  const a = artifact;

  if (node === "jd_analysis" && a.requirements)
    return (
      <div>
        <Row label="role">{a.requirements.role_title || "—"}</Row>
        {a.requirements.seniority && <Row label="seniority">{a.requirements.seniority}</Row>}
        <Row label="requirements">
          <span>
            {(a.requirements.requirements || []).map((r, i) => (
              <Chip key={i} tone={r.kind === "must_have" ? "must" : "default"}>
                {r.text}
              </Chip>
            ))}
          </span>
        </Row>
        <Row label="keywords">
          <span>{(a.requirements.keywords || []).map((k, i) => <Chip key={i}>{k}</Chip>)}</span>
        </Row>
      </div>
    );

  // profile_enrich returns the same {evidence: [...]} shape as profile, so one
  // branch renders both.
  if (node === "profile" || node === "profile_enrich")
    return (
      <div>
        {(a.evidence || []).map((b, i) => (
          <div key={i} className="border border-[#26282e] rounded p-2 mb-1.5">
            <div className="text-[11px] text-[#5c5f66] mb-1">{b.source_id}</div>
            <div className="text-[12px]">{b.content}</div>
            {b.skills?.length > 0 && (
              <div className="mt-1">{b.skills.map((s, j) => <Chip key={j}>{s}</Chip>)}</div>
            )}
          </div>
        ))}
        {(a.gap_questions || []).map((g, i) => (
          <div key={i} className="text-[12px] text-[#6ca0f5] py-0.5">? {g.question}</div>
        ))}
        {!(a.evidence || []).length && (
          <div className="text-[#5c5f66] text-[12px]">
            {node === "profile_enrich"
              ? "nothing added — no answers were given at the evidence checkpoint"
              : "no evidence returned"}
          </div>
        )}
      </div>
    );

  if (node === "matching" && a.fit_report)
    return (
      <div>
        <Row label="overall fit"><Pct value={a.fit_report.overall_fit} /></Row>
        <Row label="must-have cover"><Pct value={a.fit_report.must_have_coverage} /></Row>
        {(a.fit_report.matches || []).map((m, i) => (
          <div key={i} className="flex gap-2 py-0.5 text-[12px]">
            <Chip tone={m.support === "strong" ? "good" : m.support === "none" ? "bad" : "default"}>
              {m.support}
            </Chip>
            <span className="text-[#d7d9de]">{m.requirement}</span>
          </div>
        ))}
        {(a.fit_report.unmet_must_haves || []).map((u, i) => (
          <div key={i} className="text-[12px] text-[#f87171] py-0.5">unmet: {u}</div>
        ))}
      </div>
    );

  // The whole parsed CV is in this artifact; a card shows counts, the drawer
  // shows every line.
  if (node === "cv_link") {
    const links = a.line_links || [];
    if (!links.length) return <div className="text-[#5c5f66] text-[12px]">no CV lines were checked</div>;
    const count = (status) => links.filter((l) => l.status === status).length;
    return (
      <div>
        {a.cv_tree?.source_file && <Row label="CV">{a.cv_tree.source_file}</Row>}
        <Row label="lines checked">{links.length}</Row>
        <Row label="backed by profile">
          <span>
            <Chip tone="good">{count("matched")} yes</Chip>
            <Chip>{count("partial")} partly</Chip>
            <Chip tone="bad">{count("unmatched")} no</Chip>
          </span>
        </Row>
        {detail && <CvLines tree={a.cv_tree} links={links} />}
      </div>
    );
  }

  if (node === "document" && a.document)
    return (
      <div>
        <Row label="type">{a.document.kind}</Row>
        <pre className="text-[12px] whitespace-pre-wrap bg-[#0b0c0e] border border-[#26282e] rounded p-2 mt-1 max-h-64 overflow-y-auto">
          {a.document.content}
        </pre>
        {(a.document.unsupported_flags || []).map((f, i) => (
          <div key={i} className="text-[12px] text-[#f87171] mt-1">⚑ {f}</div>
        ))}
      </div>
    );

  if (node === "critic" && a.critique)
    return (
      <div>
        <Row label="verdict">
          <Chip tone={a.critique.verdict === "pass" ? "good" : "bad"}>{a.critique.verdict}</Chip>
        </Row>
        {(a.critique.items || []).map((it, i) => (
          <div key={i} className="text-[12px] py-0.5">
            <Chip tone={it.severity === "major" ? "bad" : "default"}>{it.severity}</Chip>
            {it.rubric_item} {it.instruction && <span className="text-[#85888f]">— {it.instruction}</span>}
          </div>
        ))}
      </div>
    );

  if (node === "verifier" && a.verifier_report)
    return (
      <div>
        <Row label="result">
          <Chip tone={a.verifier_report.status === "pass" ? "good" : "bad"}>
            {a.verifier_report.status === "pass" ? "all claims check out" : "problems found"}
          </Chip>
        </Row>
        {(a.verifier_report.claims || []).map((c, i) => (
          <div key={i} className="text-[12px] py-0.5">
            <Chip tone={c.label === "supported" ? "good" : "bad"}>{c.label}</Chip>
            {c.claim}
          </div>
        ))}
        {(a.verifier_report.do_not_claim_hits || []).map((h, i) => (
          <div key={i} className="text-[12px] text-[#f87171] py-0.5">boundary hit: {h.text}</div>
        ))}
      </div>
    );

  if (node === "evaluation" && a.eval_record) {
    const e = a.eval_record;
    return (
      <div>
        {e.ats_score != null && <Row label="keyword coverage"><Pct value={e.ats_score} /></Row>}
        {e.fit_score != null && <Row label="fit score"><Pct value={e.fit_score} /></Row>}
        {e.retrieval_precision != null && <Row label="evidence precision"><Pct value={e.retrieval_precision} /></Row>}
        {e.generation_score != null && <Row label="writing quality"><Pct value={e.generation_score} /></Row>}
        <Row label="save as example">{e.exemplar_worthy ? "yes" : "no"}</Row>
      </div>
    );
  }

  // Fallback: readable key/value dump (still not raw JSON).
  return (
    <div>
      {Object.entries(a).map(([k, v]) => (
        <Row key={k} label={k}>{typeof v === "object" ? JSON.stringify(v) : String(v)}</Row>
      ))}
    </div>
  );
}

// Friendly card titles per agent output. The profile is the shared one, not the
// user's own yet (EVIDENCE_SHARED in copy.js).
const CARD_TITLES = {
  jd_analysis: "Job requirements",
  profile: "Evidence retrieved",
  profile_enrich: "Answers added to the shared profile",
  matching: "Fit report",
  cv_link: "Your CV, checked against the shared profile",
  document: "Draft document",
  critic: "Review",
  verifier: "Fact check",
  evaluation: "Scores",
};

// The live run state — one card per agent that has produced output so far.
// `stubs` is the backend's own per-node stub flag, keyed the same as artifacts.
export default function StatePanel({ artifacts, stubs = {}, onOpenDetail }) {
  const nodes = Object.keys(CARD_TITLES).filter((n) => artifacts[n]);
  if (!nodes.length)
    return (
      <div className="text-[#5c5f66] text-[12px] border border-[#26282e] rounded p-4">
        Run state appears here as each agent writes its result.
      </div>
    );
  return (
    <div className="space-y-2">
      {nodes.map((n) => (
        <div key={n} className="border border-[#26282e] bg-[#131518] rounded p-3">
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-[12px] text-[#85888f]">
              {CARD_TITLES[n]} <span className="text-[#5c5f66]">· {AGENT_TITLES[n]}</span>
            </span>
            <button
              onClick={() => onOpenDetail(n)}
              className="text-[11px] text-[#5c5f66] hover:text-[#d7d9de]"
            >
              detail →
            </button>
          </div>
          {stubs[n] && (
            <div className="text-[11px] text-[#e8b44c] mb-1.5">⚑ {STUB_NOTE}</div>
          )}
          {renderArtifact(n, artifacts[n])}
        </div>
      ))}
    </div>
  );
}
