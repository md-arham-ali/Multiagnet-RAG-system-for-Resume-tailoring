import React from "react";

// A read-only view of the CV editor's Markdown. It handles only what
// render_markdown (utils/cv_handling/cv_edit.py) writes: "# " the name, "## " a
// section, "### " an entry, "- " a line, and **bold** for a skills label. A
// trailing double space (its header line break) is dropped. Anything else shows
// as plain text. It builds elements, never innerHTML, so typed markup can't
// inject anything.

// **bold** inside a line; every other character stays as typed.
function inline(text) {
  return text.split(/(\*\*[^*]+\*\*)/).map((part, k) =>
    part.length > 4 && part.startsWith("**") && part.endsWith("**") ? (
      <strong key={k} className="font-semibold">
        {part.slice(2, -2)}
      </strong>
    ) : (
      <React.Fragment key={k}>{part}</React.Fragment>
    )
  );
}

function Line({ line }) {
  if (!line) return <div className="h-2" />;
  if (line.startsWith("### ")) return <div className="font-semibold pt-1">{inline(line.slice(4))}</div>;
  if (line.startsWith("## "))
    return (
      <div className="text-[12px] uppercase tracking-wide text-[#85888f] pt-2 pb-0.5 border-b border-[#26282e]">
        {inline(line.slice(3))}
      </div>
    );
  if (line.startsWith("# ")) return <div className="text-[15px] font-semibold">{inline(line.slice(2))}</div>;
  if (line.startsWith("- "))
    return (
      <div className="flex gap-2 pl-2">
        <span className="text-[#5c5f66]">•</span>
        <span className="min-w-0">{inline(line.slice(2))}</span>
      </div>
    );
  return <div>{inline(line)}</div>;
}

export default function MarkdownPreview({ text }) {
  if (!text.trim()) return <div className="text-[12px] text-[#5c5f66]">(empty document)</div>;
  return (
    <div className="border border-[#26282e] rounded p-3 bg-[#0b0c0e] text-[13px] text-[#d7d9de] max-h-[28rem] overflow-auto">
      {text.split("\n").map((raw, i) => (
        <Line key={i} line={raw.replace(/\s+$/, "")} />
      ))}
    </div>
  );
}
