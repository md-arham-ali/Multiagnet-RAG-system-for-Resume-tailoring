import React, { useState } from "react";
import { get } from "../api.js";
import { useFetch } from "../useFetch.js";
import RunLog from "./RunLog.jsx";
import FinalOutput, { extractFinalArtifacts } from "./FinalOutput.jsx";
import Failed from "./Failed.jsx";
import { RUNS_INTERRUPTED, RUNS_INTERRUPTED_HELP } from "../copy.js";

// The audit trail — every run is saved event-by-event, including your
// gate decisions and feedback.
// onResume(id, mode): hand an interrupted run to Pipeline, which resumes it.
export default function RunsView({ active, onResume }) {
  const { data, error, reload } = useFetch("/runs", { active, once: false });
  const [openLog, setOpenLog] = useState(null);
  const [logError, setLogError] = useState(null);

  const openRun = async (id) => {
    setOpenLog(null);
    setLogError(null);
    try {
      setOpenLog(await get(`/runs/${id}/log`));
    } catch (err) {
      setLogError({ id, error: err });
    }
  };

  if (error)
    return (
      <div className="p-6 max-w-5xl">
        <Failed error={error} onRetry={reload} what="load runs" />
      </div>
    );
  if (!data) return <div className="p-6 text-[#5c5f66] text-[12px]">loading runs…</div>;

  const runs = data.runs || [];
  // The open run's summary row: `interrupted` lives there, not in its log.
  const openRow = openLog ? runs.find((r) => r.id === openLog.id) : null;

  return (
    <div className="p-6 max-w-5xl space-y-4">
      <h1 className="text-[15px] text-[#d7d9de]">Runs</h1>

      <div className="border border-[#26282e] bg-[#131518] rounded">
        <div className="grid grid-cols-[80px_150px_70px_1fr_90px] gap-2 px-3 py-2 text-[11px] text-[#5c5f66] border-b border-[#26282e]">
          <span>id</span><span>started</span><span>mode</span><span>job description</span><span>outcome</span>
        </div>
        {runs.map((r) => (
          <button
            key={r.id}
            onClick={() => openRun(r.id)}
            className="w-full grid grid-cols-[80px_150px_70px_1fr_90px] gap-2 px-3 py-2 text-[12px] text-left hover:bg-[#17191d]"
          >
            <span className="text-[#85888f]">{r.id}</span>
            <span className="text-[#85888f]">{r.started?.slice(0, 16).replace("T", " ")}</span>
            <span className="text-[#85888f]">{r.mode}</span>
            <span className="text-[#d7d9de] truncate">
              {r.job_description}
              {r.cv?.filename && <span className="text-[#5c5f66]"> · {r.cv.filename}</span>}
            </span>
            {r.interrupted ? (
              <span className="text-[#e8b44c]">{RUNS_INTERRUPTED}</span>
            ) : (
              <span className={r.completed ? "text-[#4ade80]" : "text-[#f87171]"}>
                {r.completed ? "complete" : "stopped"}
              </span>
            )}
          </button>
        ))}
        {runs.length === 0 && (
          <div className="px-3 py-4 text-[12px] text-[#5c5f66]">no runs yet — start one from Pipeline</div>
        )}
      </div>

      {logError && (
        <Failed
          error={logError.error}
          onRetry={() => openRun(logError.id)}
          what={`open run ${logError.id}`}
        />
      )}

      {openLog && (
        <div className="space-y-4">
          {/* Not a button inside the row: the row is one already. */}
          {openRow?.interrupted && onResume && (
            <div className="flex items-center gap-3 border border-[#e8b44c]/40 bg-[#131518] rounded p-3">
              <span className="text-[12px] text-[#e8b44c] flex-1">{RUNS_INTERRUPTED_HELP}</span>
              <button
                onClick={() => onResume(openRow.id, openRow.mode)}
                className="px-3 py-1 rounded border border-[#6ca0f5]/40 text-[#6ca0f5] text-[12px] hover:bg-[#6ca0f5]/10 shrink-0"
              >
                Resume
              </button>
            </div>
          )}
          <FinalOutput {...extractFinalArtifacts(openLog.events)} runId={openLog.id} />

          <div className="flex justify-between items-center mb-2">
            <span className="text-[12px] text-[#85888f]">run {openLog.id} — full event trail</span>
            <button onClick={() => setOpenLog(null)} className="text-[11px] text-[#5c5f66] hover:text-[#d7d9de]">
              close ✕
            </button>
          </div>
          <RunLog events={openLog.events} />
        </div>
      )}
    </div>
  );
}
