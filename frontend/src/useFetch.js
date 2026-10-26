import { useCallback, useEffect, useRef, useState } from "react";
import { get } from "./api.js";

// One GET-and-hold-it hook, so every view fails the same visible way instead
// of each one swallowing its error into a permanent "loading…" string.
//
//   once: true  — fetch the first time the view becomes active, then keep it
//   once: false — refetch every time the view becomes active (volatile lists)
export function useFetch(path, { active = true, once = true } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: false });
  const [nonce, setNonce] = useState(0);
  const fetched = useRef(false);

  const reload = useCallback(() => {
    fetched.current = false;
    setNonce((n) => n + 1);
  }, []);

  useEffect(() => {
    if (!active) return;
    if (once && fetched.current) return;
    fetched.current = true;

    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    get(path)
      .then((data) => {
        if (!cancelled) setState({ data, error: null, loading: false });
      })
      .catch((error) => {
        if (cancelled) return;
        fetched.current = false; // a failure must not count as "already fetched"
        setState({ data: null, error, loading: false });
      });
    return () => {
      cancelled = true;
    };
  }, [path, active, once, nonce]);

  return { ...state, reload };
}
