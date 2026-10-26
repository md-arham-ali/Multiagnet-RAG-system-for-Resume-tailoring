import React, { useState } from "react";
import { get } from "../api.js";
import { useFetch } from "../useFetch.js";
import SearchPanel from "./SearchPanel.jsx";
import RecordCard from "./RecordCard.jsx";
import Failed from "./Failed.jsx";

// Jargon-free store names. "claim boundaries" = the hard list of things the
// system must never say; it is checked in full, never searched.
const STORE_LABELS = {
  profile: "Profile",
  documents: "Documents",
  claim_boundaries: "Claim boundaries",
  agent_memory: "Agent memory",
};

export default function KnowledgeBase({ active }) {
  const { data: overview, error, reload } = useFetch("/kb", { active });
  const [store, setStore] = useState("profile");
  const [file, setFile] = useState(null);
  const [records, setRecords] = useState(null);
  const [fileError, setFileError] = useState(null);

  const openFile = async (name) => {
    setFile(name);
    setRecords(null);
    setFileError(null);
    try {
      const res = await get(`/kb/${store}/${name}?limit=25`);
      let recs = res.records || [];
      // claim boundaries file wraps its list — flatten it for display
      if (recs.length === 1 && recs[0]?.forbidden_claims) recs = recs[0].forbidden_claims;
      setRecords({ total: res.total ?? recs.length, list: recs });
    } catch (err) {
      setFileError(err);
    }
  };

  if (error)
    return (
      <div className="p-6 max-w-5xl">
        <Failed error={error} onRetry={reload} what="load the knowledge base" />
      </div>
    );
  if (!overview) return <div className="p-6 text-[#5c5f66] text-[12px]">loading knowledge base…</div>;

  const files = overview.stores[store] || [];
  const totalVectors = Object.values(overview.vectors || {}).reduce((a, b) => a + b, 0);

  return (
    <div className="p-6 max-w-5xl space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-[15px] text-[#d7d9de]">Knowledge Base</h1>
        <span className="text-[11px] text-[#5c5f66]">
          {totalVectors} entries searchable · claim boundaries always checked in full
        </span>
      </div>

      <SearchPanel />

      <div className="flex gap-4 items-start">
        {/* store + file navigation */}
        <div className="w-56 shrink-0 space-y-3">
          <div className="border border-[#26282e] bg-[#131518] rounded p-2">
            {Object.keys(STORE_LABELS).map((s) => (
              <button
                key={s}
                onClick={() => { setStore(s); setFile(null); setRecords(null); setFileError(null); }}
                className={`w-full text-left px-2 py-1.5 rounded text-[12px] ${
                  store === s ? "bg-[#17191d] text-[#d7d9de]" : "text-[#85888f] hover:text-[#d7d9de]"
                }`}
              >
                {STORE_LABELS[s]}
              </button>
            ))}
          </div>
          <div className="border border-[#26282e] bg-[#131518] rounded p-2">
            {files.map((f) => (
              <button
                key={f.file}
                onClick={() => openFile(f.file)}
                className={`w-full text-left px-2 py-1 rounded text-[12px] flex justify-between ${
                  file === f.file ? "bg-[#17191d] text-[#d7d9de]" : "text-[#85888f] hover:text-[#d7d9de]"
                }`}
              >
                <span>{f.file.replaceAll("_", " ")}</span>
                <span className="text-[#5c5f66]">{f.records}</span>
              </button>
            ))}
            {files.length === 0 && <div className="text-[12px] text-[#5c5f66] px-2 py-1">empty</div>}
          </div>
        </div>

        {/* records */}
        <div className="flex-1 space-y-2 min-w-0">
          {!file && (
            <div className="text-[12px] text-[#5c5f66] border border-[#26282e] rounded p-4">
              Pick a file on the left to browse its entries.
            </div>
          )}
          {fileError && (
            <Failed error={fileError} onRetry={() => openFile(file)} what={`open ${file}`} />
          )}
          {file && !records && !fileError && <div className="text-[12px] text-[#5c5f66]">loading…</div>}
          {records && (
            <>
              <div className="text-[11px] text-[#5c5f66]">
                showing {records.list.length} of {records.total}
              </div>
              {records.list.map((r, i) => <RecordCard key={i} record={r} />)}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
