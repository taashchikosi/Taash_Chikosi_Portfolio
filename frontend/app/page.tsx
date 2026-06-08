"use client";

import { UploadCloud } from "lucide-react";
import { AGENT_LABELS, type AgentName } from "@/lib/types";

// Phase 1 shell: layout + design language.
// Phase 2 wires assistant-ui chat + live SSE agent trace + HITL gate.

const AGENTS: AgentName[] = [
  "retriever",
  "modeler",
  "sim_runner",
  "analyzer",
  "reviewer",
];

export default function AnalysisPage() {
  return (
    <div className="mx-auto max-w-5xl p-8">
      <h1 className="text-xl font-semibold text-white tracking-tight">
        Retrofit Analysis
      </h1>
      <p className="mt-1 text-sm text-zinc-500">
        Upload a building energy model and 12 months of bills — get a
        physics-verified decarbonisation business case.
      </p>

      {/* Upload zone */}
      <div className="mt-8 rounded-xl border border-dashed border-surface-border bg-surface-raised/50 p-10 text-center hover:border-accent/50 transition-colors cursor-pointer">
        <UploadCloud className="mx-auto h-8 w-8 text-zinc-500" />
        <p className="mt-3 text-sm text-zinc-300">
          Drop your <span className="text-accent font-medium">.idf</span> file
          and utility data here
        </p>
        <p className="mt-1 text-xs text-zinc-600">
          or try the demo: Sydney small office (pre-cached)
        </p>
      </div>

      {/* Agent trace */}
      <h2 className="mt-10 text-sm font-medium uppercase tracking-wider text-zinc-500">
        Agent pipeline
      </h2>
      <div className="mt-3 space-y-2">
        {AGENTS.map((a) => (
          <div
            key={a}
            className="flex items-center justify-between rounded-lg border border-surface-border bg-surface-raised px-4 py-3"
          >
            <span className="text-sm text-zinc-300">
              {AGENT_LABELS[a].emoji} {AGENT_LABELS[a].label}
            </span>
            <span className="rounded-full bg-surface-border px-2.5 py-0.5 text-xs text-zinc-500">
              idle
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
