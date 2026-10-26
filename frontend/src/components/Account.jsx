import React, { useEffect, useState } from "react";
import { useAuth } from "../AuthContext.jsx";
import { useFetch } from "../useFetch.js";
import { TOPUP_HELP, TOPUP_SENT } from "../copy.js";
import Failed from "./Failed.jsx";
import CvStrip from "./CvStrip.jsx";

const Row = ({ label, children }) => (
  <div className="flex gap-2 py-0.5 text-[12px]">
    <span className="text-[#5c5f66] w-32 shrink-0">{label}</span>
    <span className="text-[#d7d9de] min-w-0">{children}</span>
  </div>
);

// Your own page: who you are, what you have left, and what you have run.
// Named "Account" rather than "Profile" — "Build Profile" already means the
// career profile you feed the knowledge base, a different thing entirely.
export default function Account({ active }) {
  const { identity, requestMore, refresh } = useAuth();
  const { data, error, reload } = useFetch("/runs", { active, once: false });
  const [asking, setAsking] = useState(false);
  const [asked, setAsked] = useState(false);
  const [askError, setAskError] = useState(null);

  // An approved top-up lands on this same token, but nothing tells the page.
  // Re-read the identity each time Account opens, so the new runs show here
  // (and in the header).
  useEffect(() => {
    if (active) refresh();
  }, [active]);

  // The count moved (a top-up arrived, or a run was spent): an earlier "request
  // sent" no longer describes this account.
  const runsLeft = identity?.runs_remaining;
  useEffect(() => setAsked(false), [runsLeft]);

  if (!identity) return null;

  const left = identity.runs_remaining;
  const isAdmin = identity.role === "admin";
  const exhausted = !isAdmin && left === 0;

  const askForMore = async () => {
    setAsking(true);
    setAskError(null);
    try {
      await requestMore("Ran out of runs — requesting more.");
      setAsked(true);
    } catch (err) {
      // 400s carry a plain reason ("…already awaiting review"): show it as is.
      setAskError(err.detail || err.message || "could not send the request");
    } finally {
      setAsking(false);
    }
  };

  const runs = data?.runs || [];

  return (
    <div className="p-6 max-w-3xl space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-[15px] text-[#d7d9de]">Account</h1>
        <span className="text-[11px] text-[#5c5f66]">your access and your run history</span>
      </div>

      <div className="border border-[#26282e] bg-[#131518] rounded p-4">
        <Row label="signed in as">{identity.identifier}</Row>
        <Row label="role">{identity.role}</Row>
        <Row label="runs remaining">
          {isAdmin ? "unlimited" : left == null ? "—" : left}
        </Row>
      </div>

      <div>
        <div className="text-[12px] text-[#85888f] mb-2">Your CV</div>
        <div className="border border-[#26282e] bg-[#131518] rounded p-4">
          <CvStrip allowDelete />
        </div>
      </div>

      {exhausted && (
        <div className="border border-[#e8b44c]/40 bg-[#131518] rounded p-4">
          <div className="text-[12px] text-[#e8b44c] mb-1">no runs left on this token</div>
          {asked ? (
            <p className="text-[12px] text-[#85888f]">{TOPUP_SENT}</p>
          ) : (
            <>
              <p className="text-[12px] text-[#85888f]">{TOPUP_HELP}</p>
              <button
                onClick={askForMore}
                disabled={asking}
                className="mt-3 px-4 py-1.5 rounded border border-[#e8b44c]/40 text-[#e8b44c] text-[13px] hover:bg-[#e8b44c]/10 disabled:opacity-40"
              >
                {asking ? "sending…" : "Request more runs"}
              </button>
            </>
          )}
          {askError && <div className="text-[12px] text-[#f87171] mt-2">{askError}</div>}
        </div>
      )}

      <div>
        <div className="text-[12px] text-[#85888f] mb-2">Your runs</div>
        {error ? (
          <Failed error={error} onRetry={reload} what="load your runs" />
        ) : !data ? (
          <div className="text-[12px] text-[#5c5f66]">loading…</div>
        ) : runs.length === 0 ? (
          <div className="text-[12px] text-[#5c5f66] border border-[#26282e] rounded p-4">
            no runs yet — start one from Pipeline
          </div>
        ) : (
          <div className="border border-[#26282e] bg-[#131518] rounded">
            {runs.slice(0, 10).map((r) => (
              <div
                key={r.id}
                className="grid grid-cols-[80px_150px_70px_1fr] gap-2 px-3 py-2 text-[12px] border-b border-[#26282e] last:border-b-0"
              >
                <span className="text-[#85888f]">{r.id}</span>
                <span className="text-[#85888f]">
                  {r.started?.slice(0, 16).replace("T", " ")}
                </span>
                <span className="text-[#85888f]">{r.mode}</span>
                <span className={r.completed ? "text-[#4ade80]" : "text-[#f87171]"}>
                  {r.completed ? "complete" : "stopped"}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
