import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { get, post, setToken, setUnauthorizedHandler } from "./api.js";

const STORAGE_KEY = "agentic.token";
const AuthContext = createContext(null);

export function useAuth() {
  return useContext(AuthContext);
}

// Turn a failed boot probe into something a human can act on. A bare
// "404 Not Found" tells the user nothing about what is actually wrong.
function describe(err) {
  if (err.status === 0)
    return { status: 0, message: "Cannot reach the backend. Is the bridge running on :8000?" };
  if (err.status === 404)
    return {
      status: 404,
      message:
        "This backend has no auth endpoints — /api/auth/me returned 404. " +
        "The server-side auth work is not deployed yet.",
    };
  return { status: err.status, message: err.message };
}

export function AuthProvider({ children }) {
  const [identity, setIdentity] = useState(null);
  // "checking" until the boot probe resolves — otherwise a refresh would flash
  // the login screen before /auth/me comes back.
  const [ready, setReady] = useState(false);
  const [bootError, setBootError] = useState(null);
  const [sessionEnded, setSessionEnded] = useState(false);

  const apply = (token, who) => {
    setToken(token);
    if (token) localStorage.setItem(STORAGE_KEY, token);
    else localStorage.removeItem(STORAGE_KEY);
    setIdentity(who);
  };

  // Probe /auth/me on boot whether or not a token is stored. With no token a
  // live backend answers 401 (→ login screen); a backend without the auth
  // routes answers 404 (→ boot error). That difference is the whole point:
  // without it, a missing backend is indistinguishable from being logged out.
  const check = useCallback(async () => {
    setBootError(null);
    setReady(false);
    const stored = localStorage.getItem(STORAGE_KEY);
    setToken(stored || null);
    try {
      const who = await get("/auth/me");
      apply(stored, who);
    } catch (err) {
      if (err.status === 401) apply(null, null); // no token, or it was rejected
      else setBootError(describe(err));
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  // The token stopped working mid-session: sign out, and tell LoginScreen why.
  const endSession = () => {
    apply(null, null);
    setSessionEnded(true);
  };

  // A token revoked while the app is open makes the next call 401. Handle it
  // once here rather than at every call site.
  useEffect(() => {
    setUnauthorizedHandler(endSession);
    return () => setUnauthorizedHandler(null);
  }, []);

  const login = async (token) => {
    setToken(token);
    setSessionEnded(false);
    try {
      const who = await post("/auth/login", { token });
      apply(token, who);
      return who;
    } catch (err) {
      setToken(identity ? localStorage.getItem(STORAGE_KEY) : null);
      throw err;
    }
  };

  const logout = () => {
    setSessionEnded(false);
    apply(null, null);
  };

  // A new account: a signup under a typed name (the sign-in page).
  const requestAccess = (identifier, note) =>
    post("/auth/request-access", { identifier, note });

  // More runs on the account you're signed in as. The server takes the account
  // from the bearer token, never from a name; a signup under your own name
  // can't be approved, since that name already has an account.
  const requestMore = (note) => post("/auth/request-more", { note });

  // Re-read the identity so the runs-remaining counter stays honest after a
  // run consumes one. /auth/me is exempt from the central 401 handler (it's
  // also the boot probe, in check()), so a 401 here would otherwise vanish: a
  // token rotated or deleted mid-session just stopped the counter. The backend
  // answers 401 only for a missing or unknown token (backend/deps.py), so end
  // the session the same way. Anything else (unreachable, 5xx) leaves it alone.
  const refresh = () =>
    get("/auth/me")
      .then(setIdentity)
      .catch((err) => {
        if (err.status === 401) endSession();
      });

  return (
    <AuthContext.Provider
      value={{
        identity,
        ready,
        bootError,
        sessionEnded,
        login,
        logout,
        requestAccess,
        requestMore,
        refresh,
        retry: check,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
