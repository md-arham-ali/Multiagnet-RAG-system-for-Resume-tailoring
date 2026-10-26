import React from "react";

// The shared "this fetch did not work" card. Replaces the silent
// .catch(() => {}) that used to leave views on a permanent loading string.
export default function Failed({ error, onRetry, what = "load" }) {
  const detail =
    error?.status === 0
      ? "cannot reach the backend"
      : error?.message || "unknown error";
  return (
    <div className="border border-[#f87171]/40 bg-[#131518] rounded p-4">
      <div className="text-[12px] text-[#f87171] mb-1">could not {what}</div>
      <p className="text-[12px] text-[#85888f] break-words">{detail}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 px-3 py-1 rounded border border-[#26282e] text-[#85888f] text-[12px] hover:text-[#d7d9de] hover:border-[#3a3d44]"
        >
          try again
        </button>
      )}
    </div>
  );
}
