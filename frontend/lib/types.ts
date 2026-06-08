// Frontend ↔ backend contract (see project plan §8)

export type AgentName =
  | "retriever"
  | "modeler"
  | "sim_runner"
  | "analyzer"
  | "reviewer";

export type AgentStatus =
  | "queued"
  | "started"
  | "progress"
  | "awaiting_approval"
  | "completed"
  | "failed";

export type AgentEvent = {
  agent: AgentName;
  status: AgentStatus;
  payload: Record<string, unknown>; // validated upstream by Pydantic
};

export const AGENT_LABELS: Record<AgentName, { label: string; emoji: string }> = {
  retriever: { label: "Retriever", emoji: "🔍" },
  modeler: { label: "Modeler", emoji: "🏗️" },
  sim_runner: { label: "Sim Runner", emoji: "⚙️" },
  analyzer: { label: "Analyzer", emoji: "📊" },
  reviewer: { label: "Reviewer", emoji: "✅" },
};
