import React from "react";
import { useFetch } from "../useFetch.js";
import { AGENT_TITLES } from "./AgentGraph.jsx";
import Failed from "./Failed.jsx";

// Which model serves which agent, and which providers are connected.
export default function SettingsView({ active }) {
  const { data: cfg, error, reload } = useFetch("/config", { active });

  if (error)
    return (
      <div className="p-6 max-w-3xl">
        <Failed error={error} onRetry={reload} what="load settings" />
      </div>
    );
  if (!cfg) return <div className="p-6 text-[#5c5f66] text-[12px]">loading settings…</div>;

  return (
    <div className="p-6 max-w-3xl space-y-4">
      <h1 className="text-[15px] text-[#d7d9de]">Settings</h1>

      <div className="border border-[#26282e] bg-[#131518] rounded p-4">
        <div className="text-[12px] text-[#85888f] mb-2">Cost mode</div>
        <div className="text-[13px] text-[#d7d9de]">{cfg.test_mode}</div>
        <div className="text-[11px] text-[#5c5f66] mt-1">
          dev = fast, low-cost model everywhere (for testing the flow) ·
          eval = the writer and reviewer use the higher-quality model
        </div>
      </div>

      <div className="border border-[#26282e] bg-[#131518] rounded p-4">
        <div className="text-[12px] text-[#85888f] mb-2">Model per agent</div>
        {Object.entries(cfg.models || {}).map(([agent, model]) => (
          <div key={agent} className="flex gap-2 py-0.5 text-[12px]">
            <span className="text-[#5c5f66] w-36">{AGENT_TITLES[agent] || agent}</span>
            <span className="text-[#d7d9de]">{model}</span>
          </div>
        ))}
      </div>

      <div className="border border-[#26282e] bg-[#131518] rounded p-4">
        <div className="text-[12px] text-[#85888f] mb-2">Connected providers</div>
        {Object.entries(cfg.keys_present || {}).map(([name, present]) => (
          <div key={name} className="flex gap-2 py-0.5 text-[12px]">
            <span className="text-[#5c5f66] w-36">{name}</span>
            <span className={present ? "text-[#4ade80]" : "text-[#5c5f66]"}>
              {present ? "connected" : "not set"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
