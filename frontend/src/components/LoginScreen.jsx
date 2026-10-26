import React, { useState } from "react";
import { useAuth } from "../AuthContext.jsx";

// A bare "404 Not Found" under a login box tells nobody anything.
function describe(err) {
  if (err.status === 401) return "that token is not valid — check it with whoever issued it";
  if (err.status === 404)
    return "this backend has no auth endpoints yet — the server-side auth work is not deployed";
  if (err.status === 0) return "cannot reach the backend — is the bridge running on :8000?";
  return err.message || "something went wrong";
}

const INPUT =
  "w-full bg-[#0b0c0e] border border-[#26282e] rounded p-2 text-[13px] text-[#d7d9de] outline-none focus:border-[#3a3d44]";

export default function LoginScreen() {
  const { login, requestAccess, sessionEnded } = useAuth();
  const [mode, setMode] = useState("login"); // "login" | "request"
  const [token, setTokenValue] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [sent, setSent] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") {
        await login(token.trim());
      } else {
        await requestAccess(identifier.trim(), note.trim());
        setSent(true);
      }
    } catch (err) {
      setError(describe(err));
    } finally {
      setBusy(false);
    }
  };

  const switchTo = (next) => {
    setMode(next);
    setError(null);
    setSent(false);
  };

  return (
    <div className="h-screen flex items-center justify-center bg-[#0b0c0e]">
      <div className="w-[380px]">
        <div className="mb-6">
          <div className="text-[#d7d9de] font-semibold tracking-wide">AGENTIC</div>
          <div className="text-[11px] text-[#5c5f66] mt-0.5">cv · cover letter pipeline</div>
        </div>

        {sessionEnded && (
          <div className="border border-[#e8b44c]/40 bg-[#131518] rounded p-3 mb-3 text-[12px] text-[#e8b44c]">
            your session ended — ask an admin for a new token
          </div>
        )}

        <form onSubmit={submit} className="border border-[#26282e] bg-[#131518] rounded p-5">
          {mode === "login" ? (
            <>
              <label className="block text-[12px] text-[#85888f] mb-1">Access token</label>
              <input
                type="password"
                value={token}
                onChange={(e) => setTokenValue(e.target.value)}
                placeholder="paste the token you were issued"
                autoFocus
                className={INPUT}
              />
              <button
                type="submit"
                disabled={busy || !token.trim()}
                className="mt-3 w-full px-4 py-1.5 rounded bg-[#d7d9de] text-[#0b0c0e] text-[13px] hover:bg-white disabled:opacity-40"
              >
                {busy ? "checking…" : "Sign in"}
              </button>
              <button
                type="button"
                onClick={() => switchTo("request")}
                className="mt-3 w-full text-[12px] text-[#5c5f66] hover:text-[#d7d9de]"
              >
                no token yet? request access
              </button>
            </>
          ) : sent ? (
            <>
              <div className="text-[12px] text-[#4ade80] mb-1">request sent</div>
              <p className="text-[12px] text-[#85888f]">
                An admin will review it and hand you a token. Come back here and sign in
                with it.
              </p>
              <button
                type="button"
                onClick={() => switchTo("login")}
                className="mt-4 w-full text-[12px] text-[#5c5f66] hover:text-[#d7d9de]"
              >
                ← back to sign in
              </button>
            </>
          ) : (
            <>
              <label className="block text-[12px] text-[#85888f] mb-1">Your name</label>
              <input
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder="how the admin will recognise you"
                autoFocus
                className={INPUT}
              />
              <label className="block text-[12px] text-[#85888f] mt-3 mb-1">
                Why you need access
              </label>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={3}
                className={INPUT}
              />
              <button
                type="submit"
                disabled={busy || !identifier.trim()}
                className="mt-3 w-full px-4 py-1.5 rounded bg-[#d7d9de] text-[#0b0c0e] text-[13px] hover:bg-white disabled:opacity-40"
              >
                {busy ? "sending…" : "Request access"}
              </button>
              <button
                type="button"
                onClick={() => switchTo("login")}
                className="mt-3 w-full text-[12px] text-[#5c5f66] hover:text-[#d7d9de]"
              >
                ← back to sign in
              </button>
            </>
          )}

          {error && <div className="text-[12px] text-[#f87171] mt-3">{error}</div>}
        </form>
      </div>
    </div>
  );
}
