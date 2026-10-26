import React from "react";

// "Projects → Skills → …" progress strip: done / current / remaining.
export default function SectionTracker({ sections, currentIdx, doneIds }) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {sections.map((s, i) => {
        const state = doneIds.includes(s.id) ? "done" : i === currentIdx ? "current" : "todo";
        return (
          <React.Fragment key={s.id}>
            <span
              className={`text-[12px] px-2 py-0.5 rounded border ${
                state === "done"
                  ? "border-[#4ade80]/40 text-[#4ade80]"
                  : state === "current"
                  ? "border-[#d7d9de] text-[#d7d9de]"
                  : "border-[#26282e] text-[#5c5f66]"
              }`}
            >
              {s.label}
            </span>
            {i < sections.length - 1 && <span className="text-[#3a3d44]">→</span>}
          </React.Fragment>
        );
      })}
    </div>
  );
}
