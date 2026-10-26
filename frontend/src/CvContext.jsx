import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { get } from "./api.js";

// The caller's current CV — the PDF their runs tailor. Shared because two views
// show it and must agree: Pipeline gates Start on it, Account can replace or
// delete it.
//
// status:
//   loading     — first check in flight
//   ready       — `cv` is the current CV, or null when there is none
//   unavailable — this backend has no CV routes (GET 404s), so every run
//                 tailors the server's shared sample CV and nothing can be uploaded
//   failed      — the check itself failed (unreachable, 5xx); the server still
//                 decides at Start, so this never blocks a run on its own
const CvContext = createContext(null);

export function CvProvider({ children }) {
  const [state, setState] = useState({ status: "loading", cv: null, error: null });

  const reload = useCallback(async () => {
    try {
      const res = await get("/profile/cv");
      setState({ status: "ready", cv: res?.cv || null, error: null });
    } catch (err) {
      // Once the route exists it answers {cv: null} for "no CV", never 404 —
      // so a 404 (or 405) can only mean the route is not deployed.
      if (err.status === 404 || err.status === 405) setState({ status: "unavailable", cv: null, error: null });
      else setState((s) => ({ ...s, status: "failed", error: err }));
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const setCurrent = useCallback((cv) => setState({ status: "ready", cv, error: null }), []);

  return (
    <CvContext.Provider value={{ ...state, reload, setCurrent }}>{children}</CvContext.Provider>
  );
}

export const useCv = () => useContext(CvContext);
