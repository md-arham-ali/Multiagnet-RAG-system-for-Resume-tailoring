import React, { useEffect, useState } from "react";
import { get, post } from "../api.js";
import { copyText } from "../clipboard.js";

export default function AdminPanel({ active }) {
  const [requests, setRequests] = useState(null);
  const [issued, setIssued] = useState({}); // request id -> raw token, shown once
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);

  const load = () => {
    setError(null); // otherwise one transient failure leaves a stale red line
    return get("/auth/requests")
      .then((r) => setRequests(r.requests || []))
      .catch((err) => setError(err.message));
  };

  useEffect(() => {
    if (active) load();
  }, [active]);

  const resolve = async (id, action) => {
    setBusy(id);
    setError(null);
    try {
      const res = await post(`/auth/requests/${id}/${action}`, {});
      if (res.token) setIssued((prev) => ({ ...prev, [id]: res.token }));
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  if (!requests && !error)
    return <div className="p-6 text-[#5c5f66] text-[12px]">loading requests…</div>;

  const pending = (requests || []).filter((r) => r.status === "pending");
  const resolved = (requests || []).filter((r) => r.status !== "pending");

  return (
    <div className="p-6 max-w-5xl space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-[15px] text-[#d7d9de]">Admin</h1>
        <span className="text-[11px] text-[#5c5f66]">approve access requests, issue tokens</span>
      </div>

      {error && <div className="text-[12px] text-[#f87171]">{error}</div>}

      <div className="border border-[#26282e] bg-[#131518] rounded">
        <div className="px-3 py-2 text-[11px] text-[#5c5f66] border-b border-[#26282e]">
          pending requests
        </div>
        {pending.map((r) => (
          <div key={r.id} className="px-3 py-2.5 border-b border-[#26282e] last:border-b-0">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <span className="text-[13px] text-[#d7d9de]">{r.identifier}</span>
                <span className="text-[11px] text-[#5c5f66] ml-2">
                  {r.created?.slice(0, 16).replace("T", " ")}
                </span>
                {r.note && <div className="text-[12px] text-[#85888f] mt-0.5">{r.note}</div>}
              </div>
              <div className="flex gap-2 shrink-0">
                <button
                  disabled={busy === r.id}
                  onClick={() => resolve(r.id, "approve")}
                  className="px-3 py-1 rounded border border-[#4ade80]/40 text-[#4ade80] text-[12px] hover:bg-[#4ade80]/10 disabled:opacity-40"
                >
                  Approve
                </button>
                <button
                  disabled={busy === r.id}
                  onClick={() => resolve(r.id, "reject")}
                  className="px-3 py-1 rounded border border-[#f87171]/40 text-[#f87171] text-[12px] hover:bg-[#f87171]/10 disabled:opacity-40"
                >
                  Reject
                </button>
              </div>
            </div>
          </div>
        ))}
        {pending.length === 0 && (
          <div className="px-3 py-4 text-[12px] text-[#5c5f66]">no requests waiting</div>
        )}
      </div>

      {Object.entries(issued).map(([id, token]) => (
        <IssuedToken key={id} token={token} />
      ))}

      {resolved.length > 0 && (
        <div className="border border-[#26282e] bg-[#131518] rounded">
          <div className="px-3 py-2 text-[11px] text-[#5c5f66] border-b border-[#26282e]">
            resolved
          </div>
          {resolved.map((r) => (
            <div key={r.id} className="grid grid-cols-[1fr_100px_150px] gap-2 px-3 py-2 text-[12px]">
              <span className="text-[#d7d9de] truncate">{r.identifier}</span>
              <span className={r.status === "approved" ? "text-[#4ade80]" : "text-[#f87171]"}>
                {r.status}
              </span>
              <span className="text-[#5c5f66]">
                {r.resolved?.slice(0, 16).replace("T", " ")}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// The raw token is returned exactly once — make that obvious and easy to copy.
function IssuedToken({ token }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    setCopied(await copyText(token));
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="border border-[#4ade80]/40 bg-[#131518] rounded p-4">
      <div className="text-[12px] text-[#4ade80] mb-1">token issued</div>
      <p className="text-[12px] text-[#85888f] mb-2">
        Shown once — copy it now and hand it over. It is not retrievable later.
      </p>
      <div className="flex gap-2">
        <code className="flex-1 min-w-0 truncate bg-[#0b0c0e] border border-[#26282e] rounded px-2 py-1.5 text-[12px] text-[#d7d9de]">
          {token}
        </code>
        <button
          onClick={copy}
          className="px-3 py-1 rounded border border-[#26282e] text-[#85888f] text-[12px] hover:text-[#d7d9de] hover:border-[#3a3d44]"
        >
          {copied ? "copied ✓" : "Copy"}
        </button>
      </div>
    </div>
  );
}
