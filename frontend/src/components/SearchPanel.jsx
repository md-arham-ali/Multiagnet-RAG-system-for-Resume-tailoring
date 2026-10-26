import React, { useState } from "react";
import { post } from "../api.js";

// Evidence search — a live query against the same knowledge index the agents
// use. Shows what comes back and how closely each result matches (0–100).
const COLLECTIONS = [
  ["profile", "profile"],
  ["documents", "documents"],
  ["learning", "agent memory"],
];

// score is 1 − cosine distance (vectordb/store.py `query`), so it runs from −1
// to 1. A hit more opposite than unrelated scores below 0. CSS ignores a negative
// width and "-40 match" means nothing to a reader, so both show 0.
const matchPct = (score) => Math.max(0, Math.min(100, Math.round(score * 100)));

export default function SearchPanel() {
  const [query, setQuery] = useState("");
  const [collection, setCollection] = useState("profile");
  const [hits, setHits] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const search = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await post("/search", { query, collection, k: 5 });
      setHits(res.hits);
    } catch (e) {
      setError(String(e.message || e));
    }
    setBusy(false);
  };

  return (
    <div className="border border-[#26282e] bg-[#131518] rounded p-4">
      <div className="text-[12px] text-[#85888f] mb-2">
        Evidence search — ask anything, see what the agents would find
      </div>
      <div className="flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && query.trim() && search()}
          placeholder="e.g. machine learning pipeline experience"
          className="flex-1 bg-[#0b0c0e] border border-[#26282e] rounded px-2 py-1.5 text-[13px] outline-none focus:border-[#3a3d44]"
        />
        <select
          value={collection}
          onChange={(e) => setCollection(e.target.value)}
          className="bg-[#0b0c0e] border border-[#26282e] rounded px-2 text-[12px] text-[#85888f]"
        >
          {COLLECTIONS.map(([id, label]) => (
            <option key={id} value={id}>{label}</option>
          ))}
        </select>
        <button
          onClick={search}
          disabled={busy || !query.trim()}
          className="px-3 py-1.5 rounded bg-[#d7d9de] text-[#0b0c0e] text-[13px] hover:bg-white disabled:opacity-40"
        >
          {busy ? "searching…" : "search"}
        </button>
      </div>
      {busy && hits === null && (
        <div className="text-[11px] text-[#5c5f66] mt-2">first search warms up the language model (~15s)</div>
      )}
      {error && <div className="text-[12px] text-[#f87171] mt-2">{error}</div>}
      {hits && (
        <div className="mt-3 space-y-1.5">
          {hits.map((h) => (
            <div key={h.id} className="border border-[#26282e] rounded p-2">
              <div className="flex items-center gap-2 mb-1">
                <span className="w-24 h-1 bg-[#26282e] rounded">
                  <span className="h-1 bg-[#6ca0f5] rounded block" style={{ width: `${matchPct(h.score)}%` }} />
                </span>
                <span className="text-[11px] text-[#6ca0f5]">{matchPct(h.score)} match</span>
                <span className="text-[11px] text-[#5c5f66]">{h.id}</span>
              </div>
              <div className="text-[12px] text-[#d7d9de]">{h.text}</div>
            </div>
          ))}
          {hits.length === 0 && <div className="text-[12px] text-[#5c5f66]">nothing found</div>}
        </div>
      )}
    </div>
  );
}
