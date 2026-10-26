import React, { useEffect, useState } from "react";
import { get } from "../api.js";

const NAV = [
  ["pipeline", "Pipeline"],
  ["kb", "Knowledge Base"],
  ["build", "Build Profile"],
  ["runs", "Runs"],
  ["account", "Account"],
  ["settings", "Settings"],
];

export default function Sidebar({ view, onNavigate, isAdmin }) {
  const [health, setHealth] = useState(null);
  const nav = isAdmin ? [...NAV, ["admin", "Admin"]] : NAV;

  useEffect(() => {
    const check = () => get("/health").then(setHealth).catch(() => setHealth(null));
    check();
    const timer = setInterval(check, 15000);
    return () => clearInterval(timer);
  }, []);

  return (
    <aside className="w-52 shrink-0 border-r border-[#26282e] flex flex-col bg-[#0b0c0e]">
      <div className="px-4 py-5 border-b border-[#26282e]">
        <div className="text-[#d7d9de] font-semibold tracking-wide">AGENTIC</div>
        <div className="text-[11px] text-[#5c5f66] mt-0.5">cv · cover letter pipeline</div>
      </div>

      <nav className="flex-1 py-3">
        {nav.map(([id, label]) => (
          <button
            key={id}
            onClick={() => onNavigate(id)}
            className={`w-full text-left px-4 py-2 text-[13px] transition-colors ${
              view === id
                ? "text-[#d7d9de] bg-[#17191d] border-l-2 border-[#d7d9de]"
                : "text-[#85888f] hover:text-[#d7d9de] border-l-2 border-transparent"
            }`}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="px-4 py-3 border-t border-[#26282e] text-[11px]">
        <span className={`inline-block w-1.5 h-1.5 rounded-full mr-2 ${health ? "bg-[#4ade80]" : "bg-[#f87171]"}`} />
        <span className="text-[#85888f]">{health ? "backend connected" : "backend offline"}</span>
      </div>
    </aside>
  );
}
