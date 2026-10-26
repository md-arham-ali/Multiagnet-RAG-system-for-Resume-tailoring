import { useEffect } from "react";

// The text of an edit of the CV that is on screen and not saved, or null.
// GateScreen holds one while you edit at the final review. Pipeline holds one
// after a run ends mid-edit, kept on screen so it can be copied (Round 32).
// The logout item and "new run" read it before throwing it away; the browser's
// leave-page prompt can't catch those, because it fires only on a reload or a
// closed tab. Module scope, like api.js's token: one is on screen at a time, and
// readers only need it at the moment of a click, so nothing re-renders on it.
let unsaved = null;

export function hasUnsavedEdit() {
  return unsaved !== null;
}

export function unsavedEditText() {
  return unsaved;
}

// Holds `text` as the unsaved edit while it isn't null, and asks before a
// reload or a closed tab drops it. null releases both. When one holder unmounts
// as another mounts (the review closing as a run ends), React runs the old
// cleanup before the new effect, so the new text is what stays.
export function useUnsavedEdit(text) {
  const holding = text != null;
  useEffect(() => {
    if (!holding) return;
    const warn = (e) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [holding]);
  useEffect(() => {
    if (!holding) return;
    unsaved = text;
    return () => {
      unsaved = null;
    };
  }, [holding, text]);
}
