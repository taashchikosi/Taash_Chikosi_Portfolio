// Frontend ↔ RetrofitGPT backend contract (mirrors the API's SSE event shape).

export type AgentName =
  | "retriever"
  | "modeler"
  | "sim_runner"
  | "analyzer"
  | "reviewer";

export const AGENT_LABELS: Record<AgentName, { label: string; emoji: string }> = {
  retriever: { label: "Retriever", emoji: "🔍" },
  modeler: { label: "Modeler", emoji: "🏗️" },
  sim_runner: { label: "Sim Runner", emoji: "⚙️" },
  analyzer: { label: "Analyzer", emoji: "📊" },
  reviewer: { label: "Reviewer", emoji: "✅" },
};
