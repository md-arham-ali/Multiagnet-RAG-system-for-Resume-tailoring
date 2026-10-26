import React from "react";

// Generic, readable renderer for one knowledge-base record. Never raw JSON:
// scalars as rows, arrays as chips or lines, nested objects indented one level.
function Value({ v }) {
  if (Array.isArray(v)) {
    if (v.every((x) => typeof x !== "object"))
      return (
        <span>
          {v.map((x, i) => (
            <span key={i} className="inline-block px-1.5 py-0.5 mr-1 mb-1 rounded text-[11px] border border-[#26282e] text-[#85888f]">
              {String(x)}
            </span>
          ))}
        </span>
      );
    return (
      <div className="space-y-1">
        {v.map((x, i) => (
          <div key={i} className="border-l border-[#26282e] pl-2"><Value v={x} /></div>
        ))}
      </div>
    );
  }
  if (v && typeof v === "object")
    return (
      <div>
        {Object.entries(v).map(([k, x]) => (
          <div key={k} className="flex gap-2">
            <span className="text-[#5c5f66] shrink-0">{k}:</span>
            <Value v={x} />
          </div>
        ))}
      </div>
    );
  return <span className="text-[#d7d9de]">{String(v)}</span>;
}

export default function RecordCard({ record }) {
  const entries = Object.entries(record).filter(
    ([, v]) => v !== null && v !== "" && !(Array.isArray(v) && v.length === 0)
  );
  return (
    <div className="border border-[#26282e] bg-[#131518] rounded p-3 text-[12px]">
      {entries.map(([k, v]) => (
        <div key={k} className="flex gap-2 py-0.5">
          <span className="text-[#5c5f66] w-40 shrink-0">{k}</span>
          <div className="min-w-0"><Value v={v} /></div>
        </div>
      ))}
    </div>
  );
}
