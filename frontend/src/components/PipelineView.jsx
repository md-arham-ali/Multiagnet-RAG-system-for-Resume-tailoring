import React, { useEffect, useMemo, useRef, useState } from "react";
import { get, post, openEvents } from "../api.js";
import { useAuth } from "../AuthContext.jsx";
import { useCv } from "../CvContext.jsx";
import {
  CV_NEEDED, CV_SAMPLE, RUN_DONE, RUN_STOPPED, RUN_FAILED, RUN_END_SAVED,
  EVIDENCE_SHARED, EVIDENCE_SHARED_HELP, UNSAVED_EDIT_NEW_RUN, STREAM_LOST, RUN_GONE,
  LOST_EDIT_HEADING, LOST_EDIT_HELP, NO_RUNS_LEFT, RESUME_FAILED, RESUME_UNSAVED_EDIT,
} from "../copy.js";
import { hasUnsavedEdit, unsavedEditText, useUnsavedEdit } from "../unsavedEdit.js";
import { copyText } from "../clipboard.js";
import CvStrip from "./CvStrip.jsx";
import AgentGraph, { AGENTS, AGENT_TITLES } from "./AgentGraph.jsx";
import StatePanel, { renderArtifact } from "./StatePanel.jsx";
import RunLog, { gateKey } from "./RunLog.jsx";
import GateScreen from "./GateScreen.jsx";
import FinalOutput from "./FinalOutput.jsx";
import Drawer from "./Drawer.jsx";

const SAMPLE_JD =
  "We need a Python data engineer with strong MLOps experience. " +
  "Must have: Python, SQL, ETL pipelines. Nice to have: DeFi or blockchain analytics background.";

const IDLE = {
  statuses: {},
  artifacts: {},
  stubs: {},
  events: [],
  gate: null,
  lastRoute: null,
  final: null,
  done: false,
  outcome: null, // "done" | "stopped" | "error" once the run has ended
  endReason: null,
};

// The line under a run that has ended. Only run_done is "finished".
function endLine(run) {
  const why = run.endReason ? ` — ${run.endReason}` : "";
  if (run.outcome === "error") return { text: `${RUN_FAILED}${why}. ${RUN_END_SAVED}`, tone: "text-[#f87171]" };
  if (run.outcome === "stopped") return { text: `${RUN_STOPPED}${why}. ${RUN_END_SAVED}`, tone: "text-[#e8b44c]" };
  return { text: RUN_DONE, tone: "text-[#4ade80]" };
}

// Nothing is in progress on a run that has ended or that the server lost. A step
// still "working" was cut off (`cutOff`: "failed" on run_error, else "stopped"),
// and a review still "waiting" will never be answered. Without this their dots
// keep pulsing over a dead run. run_error names no step, so the one left
// "working" is the only clue to where it failed.
function settle(statuses, cutOff) {
  const out = { ...statuses };
  for (const [node, status] of Object.entries(out)) {
    if (status === "running") out[node] = cutOff;
    else if (status === "waiting") out[node] = "stopped";
  }
  return out;
}

// Fold one backend event into the view of the run.
function applyEvent(run, ev) {
  const next = {
    ...run,
    statuses: { ...run.statuses },
    artifacts: { ...run.artifacts },
    stubs: { ...run.stubs },
    events: [...run.events, ev],
  };
  switch (ev.type) {
    case "node_start":
      next.statuses[ev.node] = "running";
      break;
    case "node_done": {
      // A rejected fit review re-runs cv_link, which skips re-reading the same
      // CV and returns only its stage. The earlier read is still this run's.
      const rereadSkipped = ev.node === "cv_link" && !ev.artifact?.line_links && run.artifacts.cv_link;
      if (!rereadSkipped) next.artifacts[ev.node] = ev.artifact;
      // The backend says outright which agents are still placeholders. Run logs
      // written before the flag existed simply have no stub field, so those
      // artifacts go unlabelled rather than mislabelled.
      next.stubs[ev.node] = !!ev.stub;
      const flagged =
        (ev.node === "critic" && ev.artifact?.critique?.verdict === "revise") ||
        (ev.node === "verifier" && ev.artifact?.verifier_report?.status === "fail");
      next.statuses[ev.node] = flagged ? "flagged" : "complete";
      break;
    }
    case "gate_wait":
      // artifact_node is the node whose output this gate reviews — for the final
      // gate that is "document", not the verifier the gate sits after. Older run
      // logs predate the field, so fall back to the gate's own node.
      // `ts` keys the review screen so a reopened gate starts with an empty form.
      // gap_questions is gate 2 only, and absent from logs before 2026-08-31.
      next.gate = {
        node: ev.node,
        title: ev.title,
        artifactNode: ev.artifact_node || ev.node,
        ts: ev.ts,
        gapQuestions: ev.gap_questions || [],
        // gate (the gate's own name) and changes (the final review's line diff)
        // arrive from 2026-10-09 on; older logs have neither.
        name: ev.gate || null,
        changes: ev.changes || [],
        // How many times this gate has opened in this run, this one included.
        // A reject reopens the same gate with the redone version; gate_wait has
        // no round number yet, so count it from the trail (ev is already in it).
        round: next.events.filter((e) => e?.type === "gate_wait" && gateKey(e) === gateKey(ev)).length,
      };
      next.statuses[ev.node] = "waiting";
      break;
    case "gate_done":
      next.gate = null;
      next.statuses[ev.node] = "complete";
      break;
    case "document_edited":
      // Your own edit at the final review replaced the Writer's draft.
      next.artifacts.document = ev.artifact;
      break;
    case "run_started":
      // Which CV the server resolved for this run: {id, filename}, never its text.
      // sample: the server fell back to its shared sample CV.
      if (ev.cv) next.cv = ev.cv;
      if (ev.sample) next.sampleCv = true;
      break;
    case "routing":
      next.lastRoute = ev.decision.replace("->", "→");
      break;
    case "run_done":
      // final: how the final review ended and where the CV was saved (null on older logs).
      next.final = ev.final || null;
      next.outcome = "done";
      next.done = true;
      break;
    // A stopped or failed run sends no gate_done, so close any open review here.
    // Otherwise its screen stays up over a run that is over, and hides the log
    // line that says why.
    case "run_stopped":
      next.outcome = "stopped";
      next.endReason = ev.reason || null;
      next.gate = null;
      next.statuses = settle(next.statuses, "stopped");
      next.done = true;
      break;
    case "run_error":
      // final: a CV saved before a later step failed, once the backend sends it.
      next.final = ev.final || null;
      next.outcome = "error";
      next.endReason = ev.error || null;
      next.gate = null;
      next.statuses = settle(next.statuses, "failed");
      next.done = true;
      break;
  }
  return next;
}

// An id for one Start, sent as client_request_id (8-64 characters). randomUUID
// exists only in a secure context (https or localhost), like navigator.clipboard
// (clipboard.js); getRandomValues works everywhere.
function newRequestId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
}

// Your unsaved edit of the CV, kept after a stop or failure closed the final
// review under it. Laid out like FinalOutput's box, amber because nothing saved it.
function LostEdit({ text }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    setCopied(await copyText(text));
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="border border-[#e8b44c]/40 bg-[#131518] rounded p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[#e8b44c] text-[12px]">{LOST_EDIT_HEADING}</span>
        <button
          onClick={copy}
          className="px-3 py-1 rounded border border-[#26282e] text-[#85888f] text-[12px] hover:text-[#d7d9de] hover:border-[#3a3d44]"
        >
          {copied ? "copied ✓" : "Copy"}
        </button>
      </div>
      <div className="text-[12px] text-[#e8b44c] mb-2">⚑ {LOST_EDIT_HELP}</div>
      <pre className="text-[13px] text-[#d7d9de] whitespace-pre-wrap bg-[#0b0c0e] border border-[#26282e] rounded p-3">
        {text}
      </pre>
    </div>
  );
}

// resumeRequest: {id, mode} from Runs' Resume (App.jsx), a new object per click.
export default function PipelineView({ resumeRequest }) {
  const [jd, setJd] = useState(SAMPLE_JD);
  const [mode, setMode] = useState("offline");
  const [run, setRun] = useState(null); // null = idle screen
  const [selected, setSelected] = useState(null); // agent whose detail drawer is open
  const [startError, setStartError] = useState(null);
  const [starting, setStarting] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false); // "new run" over an unsaved CV edit
  const [resuming, setResuming] = useState(false);
  const [resumeError, setResumeError] = useState(null);
  const { refresh, identity } = useAuth();
  const cvState = useCv();
  const runIdRef = useRef(null);
  const closeRef = useRef(null);
  const startingRef = useRef(false);
  // {id, jd, mode} of a Start not yet known to have started a run.
  const startRequestRef = useRef(null);
  // An edit kept from a review that a stop or failure closed is still unsaved:
  // log out, "new run" and a reload ask before dropping it, as they did while
  // the review was open.
  useUnsavedEdit(run?.lostEdit || null);

  // source_id → text of every record this run's steps put on the stream, every
  // round included (a redo replaces a step's artifact, not the records it cited).
  // Profile Search, Profile Update and the Writer each send theirs as `evidence`.
  // The final review's change cards look up the ids each change cites.
  const evidenceText = useMemo(() => {
    const byId = {};
    for (const ev of run?.events || []) {
      if (ev?.type !== "node_done" || !Array.isArray(ev.artifact?.evidence)) continue;
      for (const block of ev.artifact.evidence) {
        if (block?.source_id && block.content != null) byId[block.source_id] = block.content;
      }
    }
    return byId;
  }, [run?.events]);

  // A user with no CV can't start: there is nothing to tailor. The admin may run
  // on the shared sample instead (design.md D-CV2), and while this server has no
  // CV routes at all, every run uses the sample, so nobody is blocked.
  const needsCv = cvState.status === "ready" && !cvState.cv && identity?.role !== "admin";

  // Every POST /runs spends one of the user's runs, so only one request may be
  // in flight. client_request_id covers what that can't: a request that reached
  // the server but whose answer was lost (unreachable, a proxy error). The next
  // Start with the same job description and mode resends the same id, and the
  // backend hands back the run it already started instead of spending another
  // (backend/routes/runs.py; it remembers only runs that started, for 10
  // minutes). A changed job description or mode gets a new id, because on a
  // repeated id the backend ignores the body and returns the earlier run.
  const start = async () => {
    if (startingRef.current) return;
    startingRef.current = true;
    setStarting(true);
    setStartError(null);
    setResumeError(null);
    setSelected(null);
    const pending = startRequestRef.current;
    const client_request_id = pending && pending.jd === jd && pending.mode === mode ? pending.id : newRequestId();
    startRequestRef.current = { id: client_request_id, jd, mode };
    let run_id, runCv, runSample;
    try {
      ({ run_id, cv: runCv, sample: runSample } = await post("/runs", { job_description: jd, mode, client_request_id }));
    } catch (err) {
      // Stay on the idle screen and say why, rather than hanging on an empty run.
      // 409: the server found no current CV (checked before any run is spent) —
      // this screen's view of the CV was stale, so re-check it.
      if (err.status === 409) cvState.reload();
      setStartError(
        err.status === 403
          ? NO_RUNS_LEFT
          : err.status === 409
          ? CV_NEEDED
          : err.message || "could not start the run"
      );
      return;
    } finally {
      startingRef.current = false;
      setStarting(false);
    }
    // Started. The next Start is a new run, so it must not resend this id: for
    // ten minutes the backend would hand this run back instead.
    startRequestRef.current = null;
    // sampleCv: the server says it used its shared sample, or it has no CV routes
    // at all, in which case the worker always tailors the sample.
    setRun({ ...IDLE, mode, cv: runCv || null, sampleCv: !!runSample || cvState.status === "unavailable" });
    openStream(run_id);
    refresh(); // the run just consumed one — update the header counter
  };

  // Follow one run's events into this view. The server replays the run's whole
  // trail on every connect, so the caller sets a fresh fold (IDLE) first.
  const openStream = (run_id) => {
    runIdRef.current = run_id;
    // A stream left open would keep folding another run's events into this view.
    if (closeRef.current) closeRef.current();
    closeRef.current = openEvents(
      run_id,
      (ev) => {
        // A stop or failure closes an open review (applyEvent clears run.gate),
        // which would take an unsaved edit of the CV with it. Read its text now,
        // while the review is still mounted, and keep it on the ended run.
        const lostEdit = ev.type === "run_stopped" || ev.type === "run_error" ? unsavedEditText() : null;
        setRun((r) => {
          const next = applyEvent(r, ev);
          return lostEdit ? { ...next, lostEdit } : next;
        });
      },
      () => {
        setRun((r) => (r && !r.done ? { ...r, streamLost: true } : r));
        // EventSource can't see a status, so a dead token reads as a dropped
        // stream. One identity probe tells them apart: a 401 there ends the
        // session (AuthContext.refresh); anything else leaves "lost the
        // connection" standing.
        refresh();
      }
    );
  };

  // Pick a run back up: after the stream dropped, after the server lost it (a
  // gate answer's 404), or from Runs. GET /runs says which: `interrupted` means
  // it waits at a review with no worker (a restart), so POST .../resume rebuilds
  // it there, never spending a run; otherwise the server still holds it (or it
  // ended meanwhile) and reconnecting is enough. Either way the stream replays
  // the whole trail into a fresh fold, which reopens the same review.
  const resumeRun = async (run_id, fallbackMode) => {
    if (resuming) return;
    const sameRun = run_id === runIdRef.current;
    // A different run would replace this screen, and an unsaved edit with it.
    if (!sameRun && hasUnsavedEdit()) {
      setResumeError(RESUME_UNSAVED_EDIT);
      return;
    }
    // The same run's open review is about to unmount and reopen from the replay.
    // Keep an unsaved edit for that review (same ts) and hand it back.
    const keep = sameRun && run?.gate && hasUnsavedEdit() ? { ts: run.gate.ts, text: unsavedEditText() } : null;
    setResuming(true);
    setResumeError(null);
    let resumedMode = fallbackMode;
    try {
      const row = ((await get("/runs")).runs || []).find((r) => r.id === run_id);
      if (row?.mode) resumedMode = row.mode;
      if (row?.interrupted) await post(`/runs/${run_id}/resume`);
    } catch (err) {
      setResumeError(`${RESUME_FAILED} ${err.detail || err.message}`);
      return;
    } finally {
      setResuming(false);
    }
    setSelected(null);
    setConfirmReset(false);
    // cv and sampleCv come back with the replayed run_started.
    setRun({ ...IDLE, mode: resumedMode || run?.mode || "offline", restoredEdit: keep });
    openStream(run_id);
  };

  // Runs' Resume. A new object per click, so the same run can be asked twice.
  useEffect(() => {
    if (resumeRequest) resumeRun(resumeRequest.id, resumeRequest.mode);
  }, [resumeRequest]); // eslint-disable-line react-hooks/exhaustive-deps

  // Answers never go out with a reject: the graph keeps whatever it is sent,
  // so a rejected round's answers would otherwise be saved by the next round.
  // `gate` names the review being answered, so a late click on an old form is
  // refused (409) instead of landing on the next gate. editedContent is the
  // final review's own edit of the CV, sent only with an "edit".
  const answerGate = async (decision, feedback, gapAnswers, { gate, editedContent } = {}) => {
    try {
      await post(`/runs/${runIdRef.current}/gate`, {
        decision,
        feedback,
        gap_answers: decision === "reject" ? {} : gapAnswers || {},
        ...(gate ? { gate } : {}),
        ...(decision === "edit" && editedContent != null ? { edited_content: editedContent } : {}),
      });
    } catch (err) {
      // 404: the server no longer holds this run (it restarted). Only an answer
      // can tell; the stream can't. GateScreen retires its form on the same
      // error, and the line under the run offers Resume (resumeRun).
      if (err.status === 404) setRun((r) => (r ? { ...r, gone: true, statuses: settle(r.statuses, "stopped") } : r));
      throw err;
    }
  };

  const reset = () => {
    if (closeRef.current) closeRef.current();
    setConfirmReset(false);
    setResumeError(null);
    setRun(null);
  };

  // "new run" asks first while an unsaved edit of the CV is on screen: the open
  // final review after the stream drops or the server loses the run, or the
  // edit an ended run kept (LostEdit).
  const askReset = () => (hasUnsavedEdit() ? setConfirmReset(true) : reset());
  const resetConfirm = (
    <div className="flex items-center gap-2">
      <span className="text-[12px] text-[#e8b44c] mr-1">{UNSAVED_EDIT_NEW_RUN}</span>
      <button
        onClick={reset}
        className="px-3 py-1 rounded border border-[#f87171]/40 text-[#f87171] text-[12px] hover:bg-[#f87171]/10"
      >
        Discard and start over
      </button>
      <button
        onClick={() => setConfirmReset(false)}
        className="px-3 py-1 rounded border border-[#26282e] text-[#85888f] text-[12px] hover:text-[#d7d9de]"
      >
        Stay
      </button>
    </div>
  );

  return (
    <div className="p-6 max-w-5xl">
      <div className="flex items-baseline justify-between mb-5">
        <h1 className="text-[15px] text-[#d7d9de]">Pipeline</h1>
        <span className="text-[11px] text-[#5c5f66]">
          {/* counted, not spelled out — the list grew from seven to eight once
              profile_enrich became a real step */}
          {AGENTS.length} agents, one supervisor, four human checkpoints
        </span>
      </div>

      {/* Above both screens: a Resume from Runs can fail on either. */}
      {resumeError && <div className="text-[12px] text-[#f87171] mb-3">{resumeError}</div>}

      {/* idle: paste a job description, choose mode, start */}
      {!run && (
        <div className="border border-[#26282e] bg-[#131518] rounded p-4">
          <div className="mb-4 pb-3 border-b border-[#26282e]">
            <CvStrip />
            {/* Laid out like the CV strip above it. Your CV is yours; the records
                it is checked and rewritten against are not (copy.js). */}
            <div className="flex items-center gap-3 text-[12px] min-w-0 mt-2">
              <span className="text-[#5c5f66] shrink-0">Evidence</span>
              <span className="text-[#3a3d44] shrink-0">·</span>
              <span className="text-[#e8b44c]/80 shrink-0">{EVIDENCE_SHARED}</span>
              <span className="text-[#5c5f66] min-w-0">— {EVIDENCE_SHARED_HELP}</span>
            </div>
          </div>
          <label className="block text-[12px] text-[#85888f] mb-1">Job description</label>
          <textarea
            value={jd}
            onChange={(e) => setJd(e.target.value)}
            rows={5}
            className="w-full bg-[#0b0c0e] border border-[#26282e] rounded p-2 text-[13px] outline-none focus:border-[#3a3d44]"
          />
          <div className="flex items-center gap-4 mt-3">
            <button
              onClick={start}
              disabled={!jd.trim() || starting || needsCv}
              className="px-4 py-1.5 rounded bg-[#d7d9de] text-[#0b0c0e] text-[13px] hover:bg-white disabled:opacity-40"
            >
              {starting ? "starting…" : "Start run"}
            </button>
            {needsCv && <span className="text-[12px] text-[#85888f]">{CV_NEEDED}</span>}
            <div className="flex gap-1 text-[12px]">
              {["offline", "live"].map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`px-2.5 py-1 rounded border ${
                    mode === m
                      ? "border-[#85888f] text-[#d7d9de]"
                      : "border-[#26282e] text-[#5c5f66] hover:text-[#85888f]"
                  }`}
                >
                  {m === "offline" ? "demo mode (no model calls)" : "live model"}
                </button>
              ))}
            </div>
          </div>
          {startError && <div className="text-[12px] text-[#f87171] mt-3">{startError}</div>}
        </div>
      )}

      {/* active / finished run */}
      {run && (
        <div className="space-y-4">
          <div className="text-[12px] text-[#5c5f66]">
            {(run.cv || run.sampleCv) && (
              <>
                tailoring:{" "}
                {run.cv ? (
                  <span className="text-[#d7d9de]">{run.cv.filename}</span>
                ) : (
                  <span className="text-[#e8b44c]/80">{CV_SAMPLE}</span>
                )}
                {" · "}
              </>
            )}
            evidence: <span className="text-[#e8b44c]/80">{EVIDENCE_SHARED}</span>
          </div>
          <AgentGraph
            statuses={run.statuses}
            selected={selected}
            onSelect={setSelected}
            lastRoute={run.lastRoute}
          />

          {run.gate ? (
            <GateScreen
              key={run.gate.ts}
              gate={run.gate}
              demo={run.mode === "offline"}
              artifact={run.artifacts[run.gate.artifactNode]}
              verifierArtifact={run.artifacts.verifier}
              verifierStub={!!run.stubs.verifier}
              evidenceText={evidenceText}
              onAnswer={answerGate}
              restoredEdit={run.restoredEdit?.ts === run.gate.ts ? run.restoredEdit.text : null}
            />
          ) : (
            <div className="grid grid-cols-[1fr_280px] gap-4 items-start">
              <StatePanel artifacts={run.artifacts} stubs={run.stubs} onOpenDetail={setSelected} />
              <RunLog events={run.events} />
            </div>
          )}

          {/* The final review stays open after the stream drops (saving still
              works) and after the server loses the run (the text stays, to
              copy), so "new run" asks before throwing an unsaved edit away. */}
          {(run.streamLost || run.gone) && !run.done && (
            confirmReset ? (
              resetConfirm
            ) : (
              <div className="flex items-center gap-4">
                <span className="text-[12px] text-[#f87171]">{run.gone ? RUN_GONE : STREAM_LOST}</span>
                <button
                  onClick={() => resumeRun(runIdRef.current, run.mode)}
                  disabled={resuming}
                  className="px-3 py-1 rounded border border-[#6ca0f5]/40 text-[#6ca0f5] text-[12px] hover:bg-[#6ca0f5]/10 disabled:opacity-40"
                >
                  {resuming ? "resuming…" : "Resume"}
                </button>
                <button onClick={askReset} className="text-[12px] text-[#85888f] hover:text-[#d7d9de] underline">
                  new run
                </button>
              </div>
            )
          )}

          {run.done && run.lostEdit && <LostEdit text={run.lostEdit} />}

          {run.done && (
            <FinalOutput
              document={run.artifacts.document}
              verifier={run.artifacts.verifier}
              verifierStub={!!run.stubs.verifier}
              stub={run.stubs.document}
              final={run.final}
              runId={runIdRef.current}
              outcome={run.outcome}
            />
          )}

          {run.done &&
            (confirmReset ? (
              resetConfirm
            ) : (
              <div className="flex items-center gap-4">
                <span className={`text-[12px] ${endLine(run).tone}`}>{endLine(run).text}</span>
                <button onClick={askReset} className="text-[12px] text-[#85888f] hover:text-[#d7d9de] underline">
                  new run
                </button>
              </div>
            ))}
        </div>
      )}

      {selected && (
        <Drawer title={AGENT_TITLES[selected]} onClose={() => setSelected(null)}>
          {renderArtifact(selected, run?.artifacts[selected], { detail: true })}
        </Drawer>
      )}
    </div>
  );
}
