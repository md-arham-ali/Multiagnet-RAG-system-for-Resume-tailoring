import React from "react";
import { BUILD_PROFILE_SAVES_TO, BUILD_PROFILE_COUNT, BUILD_PROFILE_COUNT_ADMIN } from "../copy.js";

// Live preview of the entry being built — exactly what will be stored,
// visible before the user confirms it. savedCount is what the list holds: the
// caller's own entries, or every account's for the admin (isAdmin).
export default function PreviewPanel({ section, record, savedCount, isAdmin }) {
  const entries = Object.entries(record);
  return (
    <div className="border border-[#26282e] bg-[#131518] rounded p-3 sticky top-6">
      <div className="text-[12px] text-[#85888f] mb-2">This will be saved</div>
      {entries.length === 0 && (
        <div className="text-[12px] text-[#5c5f66]">answers appear here as you type</div>
      )}
      {entries.map(([k, v]) => (
        <div key={k} className="flex gap-2 py-0.5 text-[12px]">
          <span className="text-[#5c5f66] w-28 shrink-0">{k.replaceAll("_", " ")}</span>
          <span className="text-[#d7d9de] min-w-0">{Array.isArray(v) ? v.join(", ") : v}</span>
        </div>
      ))}
      <div className="mt-3 pt-2 border-t border-[#26282e] text-[11px] text-[#5c5f66]">
        {BUILD_PROFILE_SAVES_TO} · {section} <br />
        {isAdmin ? BUILD_PROFILE_COUNT_ADMIN : BUILD_PROFILE_COUNT} {savedCount}
      </div>
    </div>
  );
}
