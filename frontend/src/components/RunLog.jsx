import React from "react";
import { AGENT_TITLES } from "./AgentGraph.jsx";

// Which gate a gate_wait is. A rejected gate reopens under the same name with
// the redone version, and gate_wait carries no round number yet, so repeats
// are counted by this key. Logs before 2026-10-09 have no name: node + title
// tell the four gates apart within one run.
export function gateKey(ev) {
  return ev.gate || `${ev.node}|${ev.title}`;
}

// One line per pipeline event, newest first. Routing decisions are shown
// as they happen — this is the supervisor's decision trail.
// Every field read here is optional on purpose: a malformed event should
// produce a dull line, not throw and take the panel down.
function line(ev, round) {
  const t = AGENT_TITLES[ev.node] || ev.node || "pipeline";
  switch (ev.type) {
    case "node_start": return { text: `${t} started`, tone: "text-[#e8b44c]" };
    case "node_done": return { text: `${t} finished`, tone: "text-[#4ade80]" };
    case "routing": return { text: (ev.decision || "routing").replace("supervisor ->", "supervisor →"), tone: "text-[#85888f]" };
    case "gate_wait": {
      const again = round > 1 ? ` · round ${round}, redone version` : "";
      return { text: `paused — ${(ev.title || "waiting for your decision").toLowerCase()}${again}`, tone: "text-[#6ca0f5]" };
    }
    case "document_edited": return { text: "your edited CV replaced the draft", tone: "text-[#6ca0f5]" };
    case "run_started": {
      const cv = ev.cv?.filename || (ev.sample ? "the sample CV (not yours)" : null);
      return { text: cv ? `run started — tailoring ${cv}` : "run started", tone: "text-[#85888f]" };
    }
    case "gate_done": {
      const word = ev.edited
        ? "edited the CV"
        // A gate-4 edit of the CV carries edited (above). Every other "edit",
        // including gate-4 ones logged before 2026-10-09, meant Approve plus a note.
        : { approve: "approved", edit: "approved with a note", reject: "rejected" }[ev.decision] || ev.decision || "answered";
      const n = Object.keys(ev.gap_answers || {}).length;
      const answered = n ? ` · answered ${n} question${n === 1 ? "" : "s"}` : "";
      return { text: `you ${word}${answered}${ev.feedback ? `: "${ev.feedback}"` : ""}`, tone: "text-[#6ca0f5]" };
    }
    case "run_done": {
      const review = ev.final?.review;
      const end = !review ? "" : review.approved ? " · CV saved" : " · last draft not approved, not saved";
      return { text: `run complete${end}`, tone: "text-[#4ade80]" };
    }
    case "run_stopped": return { text: `run stopped — ${ev.reason || "no reason given"}`, tone: "text-[#f87171]" };
    case "run_error": return { text: ev.error || "run failed", tone: "text-[#f87171]" };
    default: return { text: ev.type, tone: "text-[#5c5f66]" };
  }
}

export default function RunLog({ events }) {
  const list = events || [];
  // Round of each gate_wait, by index, counted oldest first. Without it a
  // reopened gate logs a second, identical "paused" line.
  const rounds = {};
  const seen = {};
  list.forEach((ev, i) => {
    if (ev?.type !== "gate_wait") return;
    const key = gateKey(ev);
    seen[key] = (seen[key] || 0) + 1;
    rounds[i] = seen[key];
  });
  return (
    <div className="border border-[#26282e] bg-[#131518] rounded p-3 max-h-[420px] overflow-y-auto">
      <div className="text-[12px] text-[#85888f] mb-2">Activity</div>
      {list.length === 0 && <div className="text-[12px] text-[#5c5f66]">no activity yet</div>}
      {[...list].reverse().map((ev, i) => {
        const l = line(ev, rounds[list.length - 1 - i]);
        return (
          <div key={list.length - i} className="flex gap-2 py-0.5 text-[12px]">
            <span className="text-[#3a3d44] shrink-0">{ev.ts?.slice(11, 19)}</span>
            <span className={l.tone}>{l.text}</span>
          </div>
        );
      })}
    </div>
  );
}
