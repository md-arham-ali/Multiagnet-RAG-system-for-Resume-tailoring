import React, { useState } from "react";
import { renderArtifact } from "./StatePanel.jsx";
import { copyText } from "../clipboard.js";
import { download as downloadFromApi } from "../api.js";
import {
  STUB_NOTE, FACT_CHECK_PENDING, FINAL_APPROVED, FINAL_APPROVED_EDITED, FINAL_NOT_APPROVED,
  FINAL_LABEL_EARLY, FINAL_ENDED_EARLY, FINAL_LABEL_NOT_APPROVED, finalSavedAs, finalDownloadFallback,
} from "../copy.js";

// Fold a saved event trail back into the two artifacts that make up the
// deliverable. Used for finished live runs and for past runs opened from Runs.
export function extractFinalArtifacts(events) {
  let document = null;
  let verifier = null;
  let stub = false;
  let verifierStub = false;
  let final = null;
  let outcome = null; // how the run ended; null only if the trail has no end event
  for (const ev of events || []) {
    // Your own edit at the final review replaces the Writer's last draft.
    if (ev.type === "document_edited") {
      document = ev.artifact;
      stub = false;
    }
    if (ev.type === "run_done") {
      final = ev.final || null;
      outcome = "done";
    }
    // final on run_error: a CV saved before a later step failed, once the backend sends it.
    if (ev.type === "run_error") {
      final = ev.final || null;
      outcome = "error";
    }
    if (ev.type === "run_stopped") outcome = "stopped";
    if (ev.type !== "node_done") continue;
    if (ev.node === "document") {
      document = ev.artifact;
      stub = !!ev.stub; // absent in logs written before the backend sent it
    }
    if (ev.node === "verifier") {
      verifier = ev.artifact;
      verifierStub = !!ev.stub;
    }
  }
  return { document, verifier, stub, verifierStub, final, outcome };
}

const FILE_NAMES = { cv: "cv.txt", cover_letter: "cover-letter.txt" };

// A saved file's own name: final.export holds paths relative to the outputs
// folder ("<owner>/<date>_<run>_<role>.md").
const baseName = (path) => path.split("/").pop();

// How the final review ended. Null for runs logged before it was recorded.
function reviewStatus(review) {
  if (!review) return null;
  if (!review.approved) return { text: FINAL_NOT_APPROVED, tone: "text-[#e8b44c]", mark: "⚑" };
  return { text: review.edited ? FINAL_APPROVED_EDITED : FINAL_APPROVED, tone: "text-[#4ade80]", mark: "✓" };
}

// The thing the whole pipeline exists to produce. Deliberately not
// renderArtifact("document", …) — that one caps the body at max-h-64 because it
// is a summary card. Here you get the whole document, copyable and downloadable.
export default function FinalOutput({ document: documentArtifact, verifier, verifierStub, stub, final, runId, outcome }) {
  const [copied, setCopied] = useState(false);
  const [downloadError, setDownloadError] = useState(null);
  const doc = documentArtifact?.document;
  if (!doc) return null;

  const content = doc.content || "";
  const flags = doc.unsupported_flags || [];
  const status = reviewStatus(final?.review);
  // The approved CV was saved on the server as .md and .txt; download those
  // copies, so what you get is exactly what was kept. Otherwise (not approved,
  // older runs) the text on this page.
  const exported = runId && final?.export ? final.export : null;
  // A draft nobody approved isn't the deliverable. Either the run stopped or
  // failed before anything was saved, or it finished with the final review not
  // approving (a reject at the revision limit). Logs from before the review was
  // recorded have no review, so they keep "final output".
  const endedEarly = (outcome === "stopped" || outcome === "error") && !final?.export;
  const notApproved = !endedEarly && final?.review && !final.review.approved;
  const draftOnly = endedEarly || notApproved;

  const copy = async () => {
    setCopied(await copyText(content));
    setTimeout(() => setCopied(false), 1500);
  };

  // fmt: "md" or "txt" for a saved copy, null for this page's text.
  const download = async (fmt) => {
    setDownloadError(null);
    const path = fmt ? exported?.[fmt] : null;
    if (path) {
      try {
        await downloadFromApi(`/runs/${runId}/document?fmt=${fmt}`, baseName(path));
        return;
      } catch (err) {
        setDownloadError(finalDownloadFallback(err.detail || err.message || "download failed"));
      }
    }
    const url = URL.createObjectURL(new Blob([content], { type: "text/plain" }));
    const a = window.document.createElement("a");
    a.href = url;
    a.download = path ? baseName(path) : FILE_NAMES[doc.kind] || "document.txt";
    a.click();
    URL.revokeObjectURL(url);
  };

  const buttonClass =
    "px-3 py-1 rounded border border-[#26282e] text-[#85888f] text-[12px] hover:text-[#d7d9de] hover:border-[#3a3d44]";

  return (
    <div className={`border ${draftOnly ? "border-[#e8b44c]/40" : "border-[#4ade80]/40"} bg-[#131518] rounded p-5`}>
      <div className="flex items-center justify-between mb-3">
        <div>
          {draftOnly ? (
            <span className="text-[#e8b44c] text-[12px]">{notApproved ? FINAL_LABEL_NOT_APPROVED : FINAL_LABEL_EARLY}</span>
          ) : (
            <span className="text-[#4ade80] text-[12px]">final output</span>
          )}
          <span className="text-[#5c5f66] text-[12px]"> · {doc.kind || "document"}</span>
        </div>
        <div className="flex gap-2">
          <button onClick={copy} className={buttonClass}>
            {copied ? "copied ✓" : "Copy"}
          </button>
          {exported ? (
            <>
              <button onClick={() => download("md")} className={buttonClass}>
                Download .md
              </button>
              <button onClick={() => download("txt")} className={buttonClass}>
                Download .txt
              </button>
            </>
          ) : (
            <button onClick={() => download(null)} className={buttonClass}>
              Download
            </button>
          )}
        </div>
      </div>

      {status && (
        <div className={`text-[12px] mb-2 ${status.tone}`}>{status.mark} {status.text}</div>
      )}
      {exported?.md && (
        <div className="text-[12px] text-[#5c5f66] mb-2">{finalSavedAs(baseName(exported.md).replace(/\.md$/, ""))}</div>
      )}
      {endedEarly && <div className="text-[12px] text-[#e8b44c] mb-2">⚑ {FINAL_ENDED_EARLY}</div>}
      {downloadError && <div className="text-[12px] text-[#f87171] mb-2">{downloadError}</div>}

      {stub && (
        <div className="text-[12px] text-[#e8b44c] mb-2">⚑ {STUB_NOTE}</div>
      )}

      <pre className="text-[13px] text-[#d7d9de] whitespace-pre-wrap bg-[#0b0c0e] border border-[#26282e] rounded p-3">
        {content || "(empty document)"}
      </pre>

      {flags.map((f, i) => (
        <div key={i} className="text-[12px] text-[#f87171] mt-1">⚑ {f}</div>
      ))}

      {verifier && (
        <div className="mt-4 pt-4 border-t border-[#26282e]">
          <div className="text-[12px] text-[#85888f] mb-2">Fact check</div>
          {verifierStub ? (
            <div className="text-[12px] text-[#e8b44c]">⚑ {FACT_CHECK_PENDING}</div>
          ) : (
            renderArtifact("verifier", verifier)
          )}
        </div>
      )}
    </div>
  );
}
