import React from "react";
import { CV_PREVIEW_HEADING, CV_PREVIEW_HELP } from "../copy.js";

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

// "What we read": how the server parsed an uploaded CV, shown before the CV is
// accepted. A misread here would otherwise surface only at the final review, as
// edits to the wrong lines. Read-only on purpose — a wrong read is fixed in the
// PDF, not here.
export default function CvPreview({ filename, preview, busy, onUse, onCancel }) {
  const sections = preview?.sections || [];
  const warnings = preview?.warnings || [];

  return (
    <div className="mt-3 border border-[#26282e] rounded p-3 bg-[#0b0c0e]">
      <div className="text-[13px] text-[#d7d9de] mb-0.5">
        {CV_PREVIEW_HEADING} <span className="text-[#5c5f66]">· {filename}</span>
      </div>
      <div className="text-[12px] text-[#85888f] mb-3">{CV_PREVIEW_HELP}</div>

      {warnings.map((w, i) => (
        <div key={i} className="text-[12px] text-[#e8b44c] py-0.5">⚑ {w}</div>
      ))}

      {sections.length === 0 && <div className="text-[12px] text-[#5c5f66] py-1">no sections were read</div>}
      {sections.map((s, i) => {
        const entries = s.entries || [];
        const lines = entries.reduce((n, e) => n + (e.lines || []).length, 0);
        return (
          <details key={i} className="border-b border-[#26282e] last:border-b-0 py-1.5">
            <summary className="cursor-pointer select-none text-[12px] text-[#d7d9de]">
              {s.title || s.type}{" "}
              <span className="text-[#5c5f66]">
                · {plural(entries.length, "entry", "entries")} · {plural(lines, "line", "lines")}
              </span>
            </summary>
            <div className="mt-1.5 pl-3 space-y-2">
              {entries.map((e, j) => (
                <div key={j} className="border-l border-[#26282e] pl-2 text-[12px]">
                  {e.header && <div className="text-[#d7d9de]">{e.header}</div>}
                  {(e.lines || []).map((line, k) => (
                    <div key={k} className="text-[#85888f]">{line}</div>
                  ))}
                </div>
              ))}
            </div>
          </details>
        );
      })}

      <div className="flex gap-2 mt-3">
        <button
          disabled={busy}
          onClick={onUse}
          className="px-4 py-1.5 rounded border border-[#4ade80]/40 text-[#4ade80] text-[13px] hover:bg-[#4ade80]/10 disabled:opacity-40"
        >
          {busy ? "saving…" : "Use this CV"}
        </button>
        <button
          disabled={busy}
          onClick={onCancel}
          className="px-4 py-1.5 rounded border border-[#26282e] text-[#85888f] text-[13px] hover:text-[#d7d9de] disabled:opacity-40"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
