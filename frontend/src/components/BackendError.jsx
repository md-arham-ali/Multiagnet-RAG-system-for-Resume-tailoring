import React from "react";

// Shown instead of the login form when the boot probe could not even establish
// whether auth exists. Says which status came back, because "404" and
// "connection refused" need completely different fixes.
export default function BackendError({ error, onRetry }) {
  return (
    <div className="h-screen flex items-center justify-center bg-[#0b0c0e]">
      <div className="w-[420px]">
        <div className="mb-6">
          <div className="text-[#d7d9de] font-semibold tracking-wide">AGENTIC</div>
          <div className="text-[11px] text-[#5c5f66] mt-0.5">cv · cover letter pipeline</div>
        </div>

        <div className="border border-[#f87171]/40 bg-[#131518] rounded p-5">
          <div className="text-[12px] text-[#f87171] mb-1">
            backend unavailable{error.status ? ` · ${error.status}` : ""}
          </div>
          <p className="text-[12px] text-[#85888f]">{error.message}</p>
          <button
            onClick={onRetry}
            className="mt-4 px-4 py-1.5 rounded bg-[#d7d9de] text-[#0b0c0e] text-[13px] hover:bg-white"
          >
            Retry
          </button>
        </div>
      </div>
    </div>
  );
}
