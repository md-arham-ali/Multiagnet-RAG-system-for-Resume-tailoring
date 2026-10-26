import React, { useState } from "react";
import { renderArtifact } from "./StatePanel.jsx";
import { AGENT_TITLES } from "./AgentGraph.jsx";
import ChangeList from "./ChangeList.jsx";
import MarkdownPreview from "./MarkdownPreview.jsx";
import { useUnsavedEdit } from "../unsavedEdit.js";
import {
  GAP_HEADING, GAP_HELP, GAP_REJECT_NOTE, GAP_DEMO_NOTE,
  FINAL_CHANGES_HEADING, FINAL_NO_CHANGES, FINAL_EDIT_HELP, FINAL_EDIT_HELP_DEMO, FACT_CHECK_PENDING,
  FINAL_DISCARD_CONFIRM, FINAL_REJECT_NOTE, FINAL_EVIDENCE_SHARED, FINAL_RESET_CONFIRM, FINAL_PREVIEW_NOTE,
  GATE_STATUS_SENT, GATE_STATUS_CLOSED, GATE_SENT, GATE_CLOSED, GATE_GONE, GATE_CLOSED_EDIT_KEPT,
  GATE_UNREACHABLE, GATE_EDIT_NOT_SAVED, gateReopened,
  GATE_APPROVE_WITH_NOTE, GATE_NOTE_NEEDED, GATE_REJECT_NOTE,
  FEEDBACK_LABEL_RUN, FEEDBACK_LABEL_KEPT, FEEDBACK_LABEL_DEMO, charCount,
} from "../copy.js";

// The backend refuses a longer note with a 422 (GateAnswer.feedback,
// max_length=2000). maxLength counts UTF-16 units and Python counts characters,
// so the browser's limit is never looser than the server's.
const FEEDBACK_MAX = 2000;
// The same for each gate-2 answer (GateAnswer.gap_answers values, GapText
// max_length=2000), with the same count near the limit.
const GAP_ANSWER_MAX = 2000;
// The same for the edited CV (GateAnswer.edited_content, max_length=50_000).
// The editor's count turns amber from FINAL_EDIT_WARN, well before typing stops.
const FINAL_EDIT_MAX = 50000;
const FINAL_EDIT_WARN = 45000;

// What happened to a refused answer, in words. A 409 or 404 never reaches this:
// the form retires instead. Everything typed stays on screen in every case here.
function refusalText(err, editing) {
  if (err.status === 0) return GATE_UNREACHABLE;
  if (err.status === 422 && editing) return `${GATE_EDIT_NOT_SAVED} ${err.detail || err.message}`;
  return err.message || "could not submit your decision";
}

// A human gate — a dedicated full-width review screen, not a popup.
// The run is genuinely paused on the backend until you answer.
// evidenceText: source_id → record text, for the final review's change cards.
// restoredEdit: your unsaved edit of this same review, kept across a Resume
// (PipelineView.resumeRun), which reopens it in the editor; null otherwise.
export default function GateScreen({
  gate, artifact, verifierArtifact, verifierStub, demo, evidenceText, onAnswer, restoredEdit = null,
}) {
  const [feedback, setFeedback] = useState("");
  const [gapAnswers, setGapAnswers] = useState({});
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  // null while the form is live. "sent": the answer was accepted, and the
  // stream's gate_done will close this screen — until it arrives, a second
  // click would be a second answer. "movedOn": the server refused it with 409,
  // because the run is past this review. "gone": a 404, because the server no
  // longer holds the run at all (it restarted). Either way nothing more is sent.
  const [closed, setClosed] = useState(null);

  const artifactNode = gate.artifactNode || gate.node;

  // The final review is the one gate where "edit" means editing the artifact
  // itself: your text becomes the final CV. Older logs carry no gate name.
  const isFinal = gate.name ? gate.name === "gate4_document" : artifactNode === "document";

  // Only the final review shows the fact check under the CV. Keyed on the gate's
  // name, not on node !== artifact_node: gate 3 also differs (it opens after
  // cv_link but reviews matching), which put an empty fact check on the fit review.
  const showsVerifierToo = isFinal;
  const draft = artifact?.document?.content || "";
  const [editing, setEditing] = useState(isFinal && restoredEdit != null);
  const [editedText, setEditedText] = useState(isFinal && restoredEdit != null ? restoredEdit : draft);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const editChanged = editedText.trim() !== "" && editedText.trim() !== draft.trim();

  // A CV-length edit is the most expensive thing typed into this app. Reloading
  // or closing the tab would drop it silently, so ask first — the browser's own
  // leave-page prompt is the one dialog this UI allows.
  // A sent edit is saved, so no prompt; a refused one is still only on screen.
  // The in-app ways out (log out, "new run") ask through the same hold, and a
  // run that ends mid-edit takes the text from it (unsavedEdit.js).
  const unsavedEdit = isFinal && editing && editChanged && closed !== "sent";
  useUnsavedEdit(unsavedEdit ? editedText : null);

  const discardEdit = () => {
    setConfirmDiscard(false);
    setConfirmReset(false);
    setPreviewing(false);
    setEditing(false);
    setEditedText(draft);
  };

  // Back to the Writer's draft, editor still open. Enabled by any difference,
  // not only editChanged, so a cleared editor can be refilled too.
  const resetToDraft = () => {
    setConfirmReset(false);
    setEditedText(draft);
  };

  // Answers are keyed by `requirement` exactly as received: the backend pairs an
  // answer with its question by that string, and uses only the first question
  // per requirement — so one box per requirement, first question wins.
  const questions = (gate.gapQuestions || []).filter(
    (q, i, all) => q?.requirement && all.findIndex((o) => o?.requirement === q.requirement) === i
  );

  const answer = async (decision) => {
    setSending(true);
    setError(null);
    const answered = Object.fromEntries(
      Object.entries(gapAnswers)
        .map(([requirement, text]) => [requirement, text.trim()])
        .filter(([, text]) => text)
    );
    const extra = { gate: gate.name };
    if (isFinal && decision === "edit") extra.editedContent = editedText;
    try {
      await onAnswer(decision, feedback, answered, extra);
      setClosed("sent");
    } catch (err) {
      if (err.status === 409) setClosed("movedOn");
      else if (err.status === 404) setClosed("gone");
      else setError(refusalText(err, editing));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="border border-[#6ca0f5]/40 bg-[#131518] rounded p-5">
      <div className="flex items-center gap-2 mb-1">
        <span className={`w-1.5 h-1.5 rounded-full bg-[#6ca0f5] ${closed ? "" : "animate-pulse"}`} />
        <span className="text-[#6ca0f5] text-[12px]">
          {closed === "sent"
            ? GATE_STATUS_SENT
            : closed
            ? GATE_STATUS_CLOSED
            : "run paused — waiting for your decision"}
        </span>
      </div>
      <h2 className="text-[15px] text-[#d7d9de] mb-4">
        {gate.title} <span className="text-[#5c5f66]">· output of {AGENT_TITLES[artifactNode]}</span>
        {/* From the second time this review opens: without it, a redone
            version looks exactly like the one you just rejected. */}
        {gate.round > 1 && (
          <span className="ml-2 px-1.5 py-0.5 rounded border border-[#e8b44c]/40 text-[11px] text-[#e8b44c] align-middle">
            {gateReopened(gate.round)}
          </span>
        )}
      </h2>

      {isFinal && editing ? (
        <div className="mb-4">
          <div className="text-[12px] text-[#85888f] mb-1">{demo ? FINAL_EDIT_HELP_DEMO : FINAL_EDIT_HELP}</div>
          <div className="flex items-center gap-2 mb-1 text-[12px]">
            <button
              onClick={() => setPreviewing((p) => !p)}
              className="px-2.5 py-0.5 rounded border border-[#26282e] text-[#85888f] hover:text-[#d7d9de]"
            >
              {previewing ? "Edit" : "Preview"}
            </button>
            {/* Inline, not a modal, like Cancel's confirm below. */}
            {confirmReset ? (
              <>
                <span className="text-[#e8b44c]">{FINAL_RESET_CONFIRM}</span>
                <button
                  onClick={resetToDraft}
                  className="px-2.5 py-0.5 rounded border border-[#f87171]/40 text-[#f87171] hover:bg-[#f87171]/10"
                >
                  Reset
                </button>
                <button
                  onClick={() => setConfirmReset(false)}
                  className="px-2.5 py-0.5 rounded border border-[#26282e] text-[#85888f] hover:text-[#d7d9de]"
                >
                  Keep my edits
                </button>
              </>
            ) : (
              <button
                disabled={editedText === draft}
                onClick={() => setConfirmReset(true)}
                className="px-2.5 py-0.5 rounded border border-[#26282e] text-[#85888f] hover:text-[#d7d9de] disabled:opacity-40"
              >
                Reset to the draft
              </button>
            )}
            <span className="flex-1" />
            <span className={editedText.length >= FINAL_EDIT_WARN ? "text-[#e8b44c]" : "text-[#5c5f66]"}>
              {charCount(editedText.length, FINAL_EDIT_MAX)}
            </span>
          </div>
          {previewing ? (
            <>
              <div className="text-[11px] text-[#5c5f66] mb-1">{FINAL_PREVIEW_NOTE}</div>
              <MarkdownPreview text={editedText} />
            </>
          ) : (
            <textarea
              value={editedText}
              onChange={(e) => setEditedText(e.target.value)}
              rows={22}
              maxLength={FINAL_EDIT_MAX}
              spellCheck
              className="w-full bg-[#0b0c0e] border border-[#26282e] rounded p-3 text-[13px] text-[#d7d9de] font-mono outline-none focus:border-[#3a3d44]"
            />
          )}
        </div>
      ) : (
        <div className="border border-[#26282e] rounded p-3 mb-4 bg-[#0b0c0e]">
          {renderArtifact(artifactNode, artifact)}
        </div>
      )}

      {isFinal && !editing && (
        <div className="mb-4">
          <div className="text-[12px] text-[#85888f] mb-1">{FINAL_CHANGES_HEADING}</div>
          {(gate.changes || []).length === 0 ? (
            <div className="text-[12px] text-[#5c5f66]">{FINAL_NO_CHANGES}</div>
          ) : (
            <div className="space-y-2">
              <ChangeList changes={gate.changes} evidenceText={evidenceText} />
              {/* Each "why" cites records that aren't the user's own yet (copy.js). */}
              <div className="text-[12px] text-[#e8b44c]">⚑ {FINAL_EVIDENCE_SHARED}</div>
            </div>
          )}
        </div>
      )}

      {showsVerifierToo && !editing && (
        <div className="mb-4">
          <div className="text-[12px] text-[#85888f] mb-1">
            Fact check <span className="text-[#5c5f66]">· output of {AGENT_TITLES.verifier}</span>
          </div>
          <div className="border border-[#26282e] rounded p-3 bg-[#0b0c0e]">
            {verifierStub ? (
              <div className="text-[12px] text-[#e8b44c]">⚑ {FACT_CHECK_PENDING}</div>
            ) : (
              renderArtifact("verifier", verifierArtifact)
            )}
          </div>
        </div>
      )}

      {questions.length > 0 && (
        <div className="mb-4">
          <div className="text-[13px] text-[#6ca0f5] mb-0.5">{GAP_HEADING}</div>
          <div className="text-[12px] text-[#85888f] mb-3">{GAP_HELP}</div>
          {demo && <div className="text-[12px] text-[#e8b44c] mb-3">⚑ {GAP_DEMO_NOTE}</div>}
          {questions.map((q, i) => {
            const length = (gapAnswers[q.requirement] || "").length;
            return (
              <div key={q.requirement} className="mb-3">
                <label htmlFor={`gap-answer-${i}`} className="flex items-baseline gap-2 text-[12px] text-[#d7d9de] mb-1">
                  <span>{q.question}</span>
                  <span className="shrink-0 px-1.5 py-0.5 rounded border border-[#26282e] text-[11px] text-[#5c5f66]">
                    {q.requirement}
                  </span>
                </label>
                <textarea
                  id={`gap-answer-${i}`}
                  value={gapAnswers[q.requirement] || ""}
                  onChange={(e) => setGapAnswers((prev) => ({ ...prev, [q.requirement]: e.target.value }))}
                  rows={2}
                  maxLength={GAP_ANSWER_MAX}
                  className="w-full bg-[#0b0c0e] border border-[#26282e] rounded p-2 text-[13px] text-[#d7d9de] outline-none focus:border-[#3a3d44]"
                />
                {/* Only near the limit, like the feedback box: a paste the browser
                    cut to fit shouldn't go unnoticed. */}
                {length >= GAP_ANSWER_MAX - 200 && (
                  <div className={`text-[11px] ${length >= GAP_ANSWER_MAX ? "text-[#e8b44c]" : "text-[#5c5f66]"}`}>
                    {charCount(length, GAP_ANSWER_MAX)}
                  </div>
                )}
              </div>
            );
          })}
          <div className="text-[11px] text-[#5c5f66]">{GAP_REJECT_NOTE}</div>
        </div>
      )}

      <label className="block text-[12px] text-[#85888f] mb-1">
        {!isFinal ? FEEDBACK_LABEL_RUN : demo ? FEEDBACK_LABEL_DEMO : FEEDBACK_LABEL_KEPT}
      </label>
      <textarea
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        rows={3}
        maxLength={FEEDBACK_MAX}
        placeholder="what is right, what should change…"
        className="w-full bg-[#0b0c0e] border border-[#26282e] rounded p-2 text-[13px] text-[#d7d9de] outline-none focus:border-[#3a3d44] mb-3"
      />
      {/* Only near the limit, so a paste that got cut short doesn't go unnoticed. */}
      {feedback.length >= FEEDBACK_MAX - 200 && (
        <div className={`text-[11px] -mt-2 mb-3 ${feedback.length >= FEEDBACK_MAX ? "text-[#e8b44c]" : "text-[#5c5f66]"}`}>
          {charCount(feedback.length, FEEDBACK_MAX)}
        </div>
      )}

      {closed ? (
        // Retired: no buttons, so nothing more can be sent from this form. The
        // stream brings the next gate_wait (a new ts, so a fresh screen) or the end.
        closed === "sent" ? (
          <div className="text-[12px] text-[#85888f]">{GATE_SENT}</div>
        ) : (
          <div className="text-[12px] text-[#e8b44c]">
            {closed === "gone" ? GATE_GONE : GATE_CLOSED}
            {isFinal && editing && editChanged && ` ${GATE_CLOSED_EDIT_KEPT}`}
          </div>
        )
      ) : isFinal && editing && confirmDiscard ? (
        // Inline, not a modal: Cancel with changes asks once before throwing them away.
        <div className="flex items-center gap-2">
          <span className="text-[12px] text-[#e8b44c] mr-1">{FINAL_DISCARD_CONFIRM}</span>
          <button
            onClick={discardEdit}
            className="px-4 py-1.5 rounded border border-[#f87171]/40 text-[#f87171] text-[13px] hover:bg-[#f87171]/10"
          >
            Discard
          </button>
          <button
            onClick={() => setConfirmDiscard(false)}
            className="px-4 py-1.5 rounded border border-[#26282e] text-[#85888f] text-[13px] hover:text-[#d7d9de]"
          >
            Keep editing
          </button>
        </div>
      ) : isFinal && editing ? (
        <div className="flex gap-2">
          <button
            disabled={sending || !editChanged}
            onClick={() => answer("edit")}
            className="px-4 py-1.5 rounded border border-[#4ade80]/40 text-[#4ade80] text-[13px] hover:bg-[#4ade80]/10 disabled:opacity-40"
          >
            Save my edits and finish
          </button>
          <button
            disabled={sending}
            onClick={() => (editChanged ? setConfirmDiscard(true) : discardEdit())}
            className="px-4 py-1.5 rounded border border-[#26282e] text-[#85888f] text-[13px] hover:text-[#d7d9de] disabled:opacity-40"
          >
            Cancel
          </button>
        </div>
      ) : (
        <div className="flex gap-2">
          <button
            disabled={sending}
            onClick={() => answer("approve")}
            className="px-4 py-1.5 rounded border border-[#4ade80]/40 text-[#4ade80] text-[13px] hover:bg-[#4ade80]/10 disabled:opacity-40"
          >
            Approve
          </button>
          {/* Gates 1-3: "edit" is Approve plus your note, so it needs a note. */}
          <button
            disabled={sending || (isFinal ? !draft : !feedback.trim())}
            title={!isFinal && !feedback.trim() ? GATE_NOTE_NEEDED : undefined}
            onClick={() => (isFinal ? setEditing(true) : answer("edit"))}
            className="px-4 py-1.5 rounded border border-[#e8b44c]/40 text-[#e8b44c] text-[13px] hover:bg-[#e8b44c]/10 disabled:opacity-40"
          >
            {isFinal ? "Edit the CV" : GATE_APPROVE_WITH_NOTE}
          </button>
          <button
            disabled={sending}
            onClick={() => answer("reject")}
            className="px-4 py-1.5 rounded border border-[#f87171]/40 text-[#f87171] text-[13px] hover:bg-[#f87171]/10 disabled:opacity-40"
          >
            Reject
          </button>
        </div>
      )}

      {/* Under the buttons, only while Reject is one of them. */}
      {!editing && !closed && (
        <div className="text-[11px] text-[#5c5f66] mt-2">{isFinal ? FINAL_REJECT_NOTE : GATE_REJECT_NOTE}</div>
      )}

      {error && <div className="text-[12px] text-[#f87171] mt-3">{error}</div>}
    </div>
  );
}
