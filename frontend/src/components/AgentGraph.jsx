import React from "react";
import AgentNode from "./AgentNode.jsx";

// Friendly display names — internal agent ids never reach the screen.
export const AGENT_TITLES = {
  jd_analysis: "Job Analysis",
  profile: "Profile Search",
  // A real graph node since 2026-08-26, and relayed by the bridge since
  // 2026-08-31. It sits between the search and the fit report: it folds the
  // answers given at the second checkpoint back into the profile.
  profile_enrich: "Profile Update",
  matching: "Matching",
  // No model call: reads the CV PDF and links each line to the profile records
  // behind it, so the Writer edits the user's own CV rather than writing one.
  cv_link: "CV Reader",
  document: "Writer",
  critic: "Reviewer",
  verifier: "Fact Check",
  evaluation: "Scoring",
};
export const AGENTS = Object.keys(AGENT_TITLES);

// Hub-and-spoke: the supervisor bar routes every step; the agents hang
// beneath it in dispatch order, scrolling sideways if they do not fit.
export default function AgentGraph({ statuses, selected, onSelect, lastRoute }) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-2">
        <div className="flex-1 border border-[#26282e] bg-[#131518] rounded px-3 py-2 flex items-center justify-between">
          <span className="text-[12px] text-[#d7d9de]">Supervisor</span>
          <span className="text-[11px] text-[#85888f]">
            {lastRoute ? `routing: ${lastRoute}` : "routes every step through the hub"}
          </span>
        </div>
      </div>
      {/* One strip, one scroll. Each agent's spoke lives in the SAME column as
          its node rather than in a parallel row of fixed-width cells: a node is
          only min-w-28 and grows with its title, so two independent rows drift
          apart as soon as one label is long (and the 8th node made the strip
          wider than the panel, so the node row scrolled while the tick row
          stretched it). The arrow columns repeat the spoke's height so they
          centre on the nodes, not on the strip. */}
      <div className="overflow-x-auto pl-4 pb-1">
        <div className="flex gap-px w-max">
          {AGENTS.map((agent, i) => (
            <React.Fragment key={agent}>
              <div className="flex flex-col">
                <div className="flex justify-center h-3 mb-1">
                  <div className="w-px h-3 bg-[#26282e]" />
                </div>
                <AgentNode
                  name={agent}
                  title={AGENT_TITLES[agent]}
                  status={statuses[agent] || "idle"}
                  active={selected === agent}
                  onClick={() => onSelect(agent)}
                />
              </div>
              {i < AGENTS.length - 1 && (
                <div className="flex flex-col shrink-0">
                  <div className="h-3 mb-1" />
                  <div className="flex-1 flex items-center px-1 text-[#3a3d44] select-none">
                    →
                  </div>
                </div>
              )}
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}
