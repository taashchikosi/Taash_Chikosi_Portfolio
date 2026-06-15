"use client";
// Live demo route per SHARED_SITE_CONTRACT.md → /doc-intelligence/demo
// Calls the backend (real DeepSeek model in prod) via NEXT_PUBLIC_DOCINTEL_API_BASE.
// Drop this file at: frontend/app/doc-intelligence/demo/page.tsx
import { useEffect, useState, useRef } from "react";

const API = process.env.NEXT_PUBLIC_DOCINTEL_API_BASE ?? "";
const money = (n: number) =>
  "$" + Number(n ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 });

type Stage = { step: string; ok: boolean; detail: string };
type Result = {
  fields: Record<string, string | number | null>;
  decision: string; latency_ms: number; ocr_source: string;
  fraud_amount: number; injection_flags: string[]; trace: Stage[];
};
type Stats = { processed: number; dollars_saved: number; fraud_caught: number; queue_depth: number };
type Sample = { id: string; label: string; blurb: string };

export default function Demo() {
  const [samples, setSamples] = useState<Sample[]>([]);
  const [stats, setStats] = useState<Stats>({ processed: 0, dollars_saved: 0, fraud_caught: 0, queue_depth: 0 });
  const [queue, setQueue] = useState<any[]>([]);
  const [res, setRes] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState<boolean | null>(null);
  const [mode, setMode] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = async () => {
    setStats(await (await fetch(`${API}/stats`)).json());
    setQueue(await (await fetch(`${API}/review/queue`)).json());
  };
  useEffect(() => {
    fetch(`${API}/health`).then(r => r.json()).then(h => {
      setLive(true);
      setMode(h.extractor === "llm" ? "LLM extractor live" : "regex baseline (dev only)");
    }).catch(() => setLive(false));
    fetch(`${API}/demo/samples`).then(r => r.json()).then(setSamples).catch(() => {});
    refresh();
  }, []);

  const run = async (url: string, opts?: RequestInit) => {
    if (busy) return;
    setBusy(true); setRes(null);
    try {
      const r: Result = await (await fetch(url, { method: "POST", ...opts })).json();
      setRes(r); await refresh();
    } catch { /* surfaced via res === null */ }
    setBusy(false);
  };
  const runAll = async () => {
    for (const id of ["hero", "ugly", "injection", "duplicate"]) {
      await run(`${API}/demo/run/${id}`); await new Promise(r => setTimeout(r, 900));
    }
  };
  const upload = async (f?: File) => {
    if (!f) return;
    const fd = new FormData(); fd.append("file", f);
    await run(`${API}/extract`, { body: fd });
  };

  const Stat = ({ k, v, cls }: { k: string; v: string; cls?: string }) => (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <div className="text-xs uppercase tracking-wider text-slate-400">{k}</div>
      <div className={`mt-1 text-3xl font-bold tabular-nums ${cls ?? ""}`}>{v}</div>
    </div>
  );

  return (
    <main className="mx-auto max-w-5xl px-5 py-8 text-slate-100">
      <div className="mb-1 flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${live ? "bg-emerald-400" : "bg-slate-500"}`} />
        <h1 className="text-xl font-semibold">Invoice Intelligence — live demo</h1>
      </div>
      <p className="mb-6 text-sm text-slate-400">
        Reads any vendor invoice, checks the maths, catches duplicates & fraud, escalates what it
        isn’t sure of — on a CPU box, no GPU. <span className="text-slate-500">· {mode}</span>
      </p>

      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Stat k="Invoices processed" v={String(stats.processed)} />
        <Stat k="$ saved vs manual" v={money(stats.dollars_saved)} cls="text-emerald-400" />
        <Stat k="Fraud $ caught" v={money(stats.fraud_caught)} cls="text-amber-300" />
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        {samples.map(s => (
          <button key={s.id} onClick={() => run(`${API}/demo/run/${s.id}`)} title={s.blurb}
            className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm hover:border-indigo-400">
            {s.label}
          </button>
        ))}
        <button onClick={runAll}
          className="rounded-lg bg-indigo-500 px-3 py-2 text-sm font-semibold text-white hover:bg-indigo-400">
          ▶ Run all 4
        </button>
      </div>

      <div onClick={() => fileRef.current?.click()}
        onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); upload(e.dataTransfer.files[0]); }}
        className="mb-5 cursor-pointer rounded-xl border border-dashed border-white/15 p-4 text-center text-sm text-slate-400 hover:border-indigo-400">
        Drag in your own invoice (PDF) — processed in memory, never stored
      </div>
      <input ref={fileRef} type="file" accept="application/pdf" hidden
        onChange={e => upload(e.target.files?.[0])} />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
          <p className="mb-3 text-xs uppercase tracking-wider text-slate-400">Result</p>
          {res && res.fraud_amount > 0 && (
            <div className="mb-3 rounded-xl border border-amber-300/60 bg-amber-300/10 p-3 text-sm">
              🛡️ <b>Fraud caught</b> — {money(res.fraud_amount)} double-payment prevented (near-duplicate).
            </div>
          )}
          {res && res.injection_flags?.length > 0 && (
            <div className="mb-3 rounded-xl border border-rose-400/60 bg-rose-400/10 p-3 text-sm">
              🛡️ <b>Prompt-injection blocked</b> — escalated, not obeyed.
            </div>
          )}
          {res ? (
            <>
              <div className="mb-3 flex items-center gap-3 text-xl font-bold">
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${res.decision === "approve" ? "bg-emerald-400/15 text-emerald-300" : "bg-rose-400/15 text-rose-300"}`}>
                  {res.decision.toUpperCase()}
                </span>
                <span className="text-sm font-normal text-slate-400">{res.latency_ms} ms · {res.ocr_source}</span>
              </div>
              <table className="w-full text-sm">
                <tbody>
                  {["invoice_number", "vendor_name", "invoice_date", "subtotal", "tax", "total"].map(f => (
                    <tr key={f} className="border-b border-white/10">
                      <td className="py-1.5 text-slate-400">{f.replace("_", " ")}</td>
                      <td className="py-1.5 text-right tabular-nums">{String(res.fields[f] ?? "—")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : <p className="text-sm text-slate-500">{busy ? "Processing…" : "Pick a sample or drop an invoice →"}</p>}
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
          <p className="mb-3 text-xs uppercase tracking-wider text-slate-400">Reasoning trace</p>
          <ul className="space-y-1.5">
            {res?.trace.map((s, i) => (
              <li key={i} className="flex items-center gap-2.5 border-b border-white/10 py-1.5 text-sm">
                <span className={`grid h-[18px] w-[18px] place-items-center rounded-full text-[11px] text-white ${s.ok ? "bg-emerald-500" : "bg-rose-500"}`}>{s.ok ? "✓" : "✕"}</span>
                <span className="min-w-[84px] font-medium">{s.step}</span>
                <span className="text-slate-400">{s.detail}</span>
              </li>
            ))}
          </ul>
          <p className="mb-2 mt-4 text-xs uppercase tracking-wider text-slate-400">
            Escalation queue {stats.queue_depth ? `(${stats.queue_depth})` : ""}
          </p>
          <ul className="space-y-1.5 text-sm">
            {queue.length ? queue.map((i, n) => (
              <li key={n} className="border-b border-white/10 py-1.5">
                <b>{i.fields.invoice_number || "—"}</b> · {i.fields.vendor_name} · {money(i.fields.total || 0)}
                <div className="text-xs text-amber-300">{(i.reasons || []).join(" · ")}</div>
              </li>
            )) : <li className="py-1.5 text-slate-500">Nothing escalated yet.</li>}
          </ul>
        </div>
      </div>

      <p className="mt-6 text-xs leading-relaxed text-slate-500">
        Numbers are real and computed: “$ saved” uses the Ardent Partners 2025 manual benchmark
        ($12.88/invoice); “fraud $ caught” is the total of any invoice flagged as a near-duplicate.
        Extraction accuracy is reported separately on FATURA + a real-invoice holdout — a live demo
        isn’t an accuracy claim. Uploads are processed ephemerally and never stored.
      </p>
    </main>
  );
}
