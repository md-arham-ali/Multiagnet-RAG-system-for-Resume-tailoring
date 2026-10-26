import React, { useEffect, useRef, useState } from "react";
import { upload, post, del } from "../api.js";
import { useAuth } from "../AuthContext.jsx";
import { useCv } from "../CvContext.jsx";
import CvPreview from "./CvPreview.jsx";
import {
  CV_NONE,
  CV_SAMPLE,
  CV_UNAVAILABLE,
  CV_READING,
  CV_CHECK_FAILED,
  CV_DELETE_CONFIRM,
  CV_ERRORS,
} from "../copy.js";

const MAX_BYTES = 5 * 1024 * 1024;

// Checked before anything is sent; the server checks both again (413 / 415).
// By magic bytes, not extension: a renamed .docx is still not a PDF.
async function clientReject(file) {
  if (file.size > MAX_BYTES) return CV_ERRORS.tooLarge;
  const head = await file.slice(0, 5).text().catch(() => "");
  return head === "%PDF-" ? null : CV_ERRORS.notPdf;
}

// One specific sentence per failure. The 422 codes arrive in `detail`, which
// ApiError's message carries whether it was sent as a string or an object.
function errorText(err) {
  if (err.status === 413) return CV_ERRORS.tooLarge;
  if (err.status === 415) return CV_ERRORS.notPdf;
  if (err.status === 422) {
    const code = ["no_text", "no_sections", "too_many_pages"].find((c) => err.message.includes(c));
    if (code) return CV_ERRORS[code];
  }
  if (err.status === 0) return CV_ERRORS.unreachable;
  return err.message;
}

const pages = (n) => (n == null ? null : `${n} page${n === 1 ? "" : "s"}`);
const day = (iso) => {
  const d = new Date(iso);
  return isNaN(d) ? null : `uploaded ${d.toLocaleDateString(undefined, { day: "numeric", month: "short" })}`;
};

const smallButton =
  "text-[12px] px-2.5 py-1 rounded border border-[#26282e] text-[#85888f] hover:text-[#d7d9de] hover:border-[#3a3d44] disabled:opacity-40";

// The one-line "CV · file · pages · date [Replace]" strip, with picker and
// drag-and-drop, the upload → read → preview → use flow, and (in Account) delete.
// The current CV only changes on "Use this CV", so a failed or cancelled upload
// leaves the previous one in place.
export default function CvStrip({ allowDelete = false }) {
  const { identity } = useAuth();
  const { status, cv, error: checkError, reload, setCurrent } = useCv();
  const inputRef = useRef(null);
  const pendingRef = useRef(null);
  const [phase, setPhase] = useState("idle"); // idle | uploading | reading | preview | saving
  const [progress, setProgress] = useState(0);
  const [pending, setPendingState] = useState(null); // {cv, preview}: uploaded, not yet current
  const [error, setError] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const setPending = (p) => {
    pendingRef.current = p;
    setPendingState(p);
  };

  // The current CV's id, for discard() — read from the unmount cleanup below,
  // which would otherwise only ever see the first render's value.
  const currentIdRef = useRef(null);
  useEffect(() => {
    currentIdRef.current = cv?.id || null;
  }, [cv]);

  // An upload nobody confirmed is thrown away server-side, so files don't pile up.
  // Never the current CV: ids are content hashes, so re-uploading the same PDF
  // comes back under the current CV's own id (the server keeps it as it is), and
  // deleting that "upload" would delete the CV every run uses.
  const discard = (p) => {
    const id = p?.cv?.id;
    if (id && id !== currentIdRef.current) del(`/profile/cv/${encodeURIComponent(id)}`).catch(() => {});
  };

  // Starting a run unmounts the Pipeline strip; don't leave its upload behind.
  useEffect(() => () => discard(pendingRef.current), []);

  const canUpload = status === "ready" && (phase === "idle" || phase === "preview");

  const pick = async (file) => {
    if (!file || !canUpload) return;
    setError(null);
    setConfirmDelete(false);
    const reject = await clientReject(file);
    if (reject) {
      setError(reject);
      return;
    }
    discard(pendingRef.current);
    setPending(null);
    setProgress(0);
    setPhase("uploading");
    try {
      const res = await upload("/profile/cv", file, (p) => {
        setProgress(p);
        if (p >= 1) setPhase("reading");
      });
      if (!res?.cv?.id) throw new Error("the server did not return the uploaded CV");
      setPending(res);
      setPhase("preview");
    } catch (err) {
      setError(errorText(err));
      setPhase("idle");
    }
  };

  const useThis = async () => {
    setPhase("saving");
    setError(null);
    try {
      const res = await post(`/profile/cv/${encodeURIComponent(pending.cv.id)}/confirm`);
      setCurrent(res?.cv || pending.cv);
      setPending(null);
      setPhase("idle");
    } catch (err) {
      setError(errorText(err));
      setPhase("preview");
    }
  };

  const cancel = () => {
    discard(pending);
    setPending(null);
    setPhase("idle");
  };

  const remove = async () => {
    setDeleting(true);
    setError(null);
    try {
      await del(`/profile/cv/${encodeURIComponent(cv.id)}`);
      setCurrent(null);
      setConfirmDelete(false);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setDeleting(false);
    }
  };

  // Always swallow drops on the strip: an unhandled PDF drop makes the browser
  // open the file in this tab, which navigates away from a live run.
  const dropProps = {
    onDragOver: (e) => {
      e.preventDefault();
      if (canUpload) setDragging(true);
    },
    onDragLeave: () => setDragging(false),
    onDrop: (e) => {
      e.preventDefault();
      setDragging(false);
      pick(e.dataTransfer.files?.[0]);
    },
  };

  let what;
  if (status === "loading") what = <span className="text-[#5c5f66]">checking…</span>;
  else if (status === "unavailable") what = <span className="text-[#e8b44c]/80">{CV_UNAVAILABLE}</span>;
  else if (status === "failed")
    what = (
      <span className="text-[#f87171]">
        {CV_CHECK_FAILED} — {checkError?.message}{" "}
        <button onClick={reload} className="underline text-[#85888f] hover:text-[#d7d9de]">
          retry
        </button>
      </span>
    );
  else if (cv)
    what = (
      <span className="text-[#d7d9de] min-w-0 truncate">
        {[cv.filename, pages(cv.pages), day(cv.uploaded_at)].filter(Boolean).join(" · ")}
      </span>
    );
  else if (identity?.role === "admin") what = <span className="text-[#e8b44c]/80">{CV_SAMPLE}</span>;
  else what = <span className="text-[#85888f]">{CV_NONE}</span>;

  return (
    <div {...dropProps} className={`rounded ${dragging ? "outline outline-1 outline-[#85888f]" : ""}`}>
      <div className="flex items-center gap-3 text-[12px] min-w-0">
        <span className="text-[#5c5f66] shrink-0">CV</span>
        <span className="text-[#3a3d44] shrink-0">·</span>
        {what}
        <span className="flex-1" />
        {phase === "uploading" && <span className="text-[#85888f] shrink-0">uploading… {Math.round(progress * 100)}%</span>}
        {phase === "reading" && <span className="text-[#85888f] shrink-0">{CV_READING}</span>}
        {status === "ready" && (phase === "idle" || phase === "preview") && (
          <span className="flex gap-1.5 shrink-0">
            <button onClick={() => inputRef.current?.click()} className={smallButton}>
              {cv ? "Replace" : "Upload PDF"}
            </button>
            {allowDelete && cv && (
              <button onClick={() => setConfirmDelete(true)} className={smallButton}>
                Delete
              </button>
            )}
          </span>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = ""; // so choosing the same file again still fires
          pick(file);
        }}
      />

      {phase === "uploading" && (
        <div className="h-0.5 bg-[#26282e] rounded mt-2">
          <div className="h-0.5 bg-[#d7d9de] rounded" style={{ width: `${Math.round(progress * 100)}%` }} />
        </div>
      )}

      {confirmDelete && (
        <div className="flex items-center gap-3 mt-2 text-[12px]">
          <span className="text-[#e8b44c]">{CV_DELETE_CONFIRM}</span>
          <button
            disabled={deleting}
            onClick={remove}
            className="px-2.5 py-1 rounded border border-[#f87171]/40 text-[#f87171] hover:bg-[#f87171]/10 disabled:opacity-40"
          >
            {deleting ? "deleting…" : "Delete"}
          </button>
          <button disabled={deleting} onClick={() => setConfirmDelete(false)} className={smallButton}>
            Keep
          </button>
        </div>
      )}

      {error && <div className="text-[12px] text-[#f87171] mt-2">{error}</div>}

      {pending && (phase === "preview" || phase === "saving") && (
        <CvPreview
          filename={pending.cv.filename}
          preview={pending.preview}
          busy={phase === "saving"}
          onUse={useThis}
          onCancel={cancel}
        />
      )}
    </div>
  );
}
