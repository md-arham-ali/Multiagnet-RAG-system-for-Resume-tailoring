import React from "react";

// status: idle | running | waiting | complete | flagged | stopped | failed
// stopped / failed: where an ended run left off (PipelineView's settle()). No
// pulse, since nothing is happening; colours match the run's end line.
const STYLE = {
  idle:     { dot: "bg-[#3a3d44]",              text: "text-[#5c5f66]", label: "idle" },
  running:  { dot: "bg-[#e8b44c] animate-pulse", text: "text-[#e8b44c]", label: "working" },
  waiting:  { dot: "bg-[#6ca0f5] animate-pulse", text: "text-[#6ca0f5]", label: "waiting for input" },
  complete: { dot: "bg-[#4ade80]",              text: "text-[#4ade80]", label: "complete" },
  flagged:  { dot: "bg-[#f87171]",              text: "text-[#f87171]", label: "flagged" },
  stopped:  { dot: "bg-[#e8b44c]",              text: "text-[#e8b44c]", label: "stopped" },
  failed:   { dot: "bg-[#f87171]",              text: "text-[#f87171]", label: "failed" },
};

export default function AgentNode({ name, title, status, active, onClick }) {
  const s = STYLE[status] || STYLE.idle;
  return (
    <button
      onClick={onClick}
      className={`min-w-28 px-3 py-2.5 rounded border text-left transition-colors ${
        active ? "border-[#85888f] bg-[#17191d]" : "border-[#26282e] bg-[#131518] hover:border-[#3a3d44]"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${s.dot}`} />
        <span className="text-[12px] text-[#d7d9de]">{title || name}</span>
      </div>
      <div className={`text-[10px] mt-1 ${s.text}`}>{s.label}</div>
    </button>
  );
}
