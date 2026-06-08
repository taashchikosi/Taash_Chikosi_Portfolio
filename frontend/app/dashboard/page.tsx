import { MetricCard } from "@/components/metric-card";

// Phase 3 wires this to GET /api/metrics (Langfuse export).

export default function DashboardPage() {
  return (
    <div className="mx-auto max-w-5xl p-8">
      <h1 className="text-xl font-semibold text-white tracking-tight">
        Observability
      </h1>
      <p className="mt-1 text-sm text-zinc-500">
        Cost, latency and eval metrics per simulation run.
      </p>

      <div className="mt-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricCard label="Cost / run" value="—" sub="awaiting first run" />
        <MetricCard label="p95 latency" value="—" sub="per agent" />
        <MetricCard label="Eval pass rate" value="—" sub="last CI run" />
        <MetricCard label="Guardrail triggers" value="—" sub="LLM06 rejections" />
      </div>

      <div className="mt-6 rounded-xl border border-surface-border bg-surface-raised p-6 text-sm text-zinc-500">
        Model router breakdown chart (Recharts) lands in Phase 3 — data from{" "}
        <code className="text-zinc-400">/api/metrics</code>.
      </div>
    </div>
  );
}
