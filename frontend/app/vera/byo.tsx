"use client";

// Bring-your-own-bills — watch Vera EXTRACT the important fields straight off a bill you
// upload. No price-creep / quote checks here: those need months of history, which a one-off
// bill from a stranger doesn't have. This part is purely "can it read my bill?" — the
// answer is real (live DeepSeek), and nothing is stored (processed in memory, then dropped).
// Hits POST /demo/byo/upload · POST /demo/byo/reset.

import { useCallback, useRef, useState } from "react";
import { Upload, RotateCcw, Loader2, CheckCircle2 } from "lucide-react";
import { RunMetrics, type RunTelemetry } from "@/components/run-metrics";

const money = (n: number) =>
  "$" + Number(n ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 });

type Fields = {
  invoice_number: string | null;
  vendor_name: string | null;
  invoice_date: string | null;
  subtotal: number | null;
  tax: number | null;
  total: number | null;
};
type ByoResp = {
  session_id: string;
  run_telemetry?: RunTelemetry | null;
  fields: Fields;
  ocr_source: string;
  confidence: number;
};
type UploadResult = { name: string; fields: Fields; ocr_source: string; confidence: number };

// Sum each upload's measured telemetry so the Results reflect all bills uploaded this session.
function addTelemetry(prev: RunTelemetry | null, next: RunTelemetry | null | undefined): RunTelemetry | null {
  if (!next) return prev;
  return {
    model: next.model ?? prev?.model ?? null,
    tokens: ((prev?.tokens ?? 0) + (next.tokens ?? 0)) || null,
    llm_calls: ((prev?.llm_calls ?? 0) + (next.llm_calls ?? 0)) || null,
    cost_usd: ((prev?.cost_usd ?? 0) + (next.cost_usd ?? 0)) || null,
    latency_s: Number(((prev?.latency_s ?? 0) + (next.latency_s ?? 0)).toFixed(1)) || null,
  };
}

const FIELD_ROWS: { label: string; key: keyof Fields; money?: boolean }[] = [
  { label: "Invoice #", key: "invoice_number" },
  { label: "Vendor", key: "vendor_name" },
  { label: "Date", key: "invoice_date" },
  { label: "Subtotal", key: "subtotal", money: true },
  { label: "Tax", key: "tax", money: true },
  { label: "Total", key: "total", money: true },
];

export function Byo({ apiBase, accent }: { apiBase: string; accent?: string }) {
  const acc = accent ?? "var(--cyan)";
  const sessionId = useRef<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const [results, setResults] = useState<UploadResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [count, setCount] = useState(0);
  const [tel, setTel] = useState<RunTelemetry | null>(null);

  const headers = useCallback((): HeadersInit => {
    return sessionId.current ? { "X-Vera-Session": sessionId.current } : {};
  }, []);

  async function uploadFiles(files: FileList | null) {
    if (!files || files.length === 0 || busy) return;
    setBusy(true);
    setErr(null);
    try {
      for (const file of Array.from(files)) {
        const fd = new FormData();
        fd.append("file", file);
        // Abort a stalled extraction so the button can't stay disabled forever.
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 60_000);
        let r: Response;
        try {
          r = await fetch(`${apiBase}/demo/byo/upload`, { method: "POST", headers: headers(), body: fd, signal: ctrl.signal });
        } catch (netErr) {
          throw new Error(
            ctrl.signal.aborted
              ? "That upload timed out — try a smaller or clearer file."
              : "Couldn't reach the server — check your connection and try again.",
          );
        } finally {
          clearTimeout(timer);
        }
        if (!r.ok) {
          // The backend returns a clear reason (e.g. unreadable file, unsupported type) —
          // surface it instead of implying the backend was unreachable.
          let detail = "";
          try {
            detail = ((await r.json()) as { detail?: string }).detail ?? "";
          } catch {
            /* non-JSON error body */
          }
          throw new Error(detail || `The server couldn't process that upload (HTTP ${r.status}).`);
        }
        const data = (await r.json()) as ByoResp;
        sessionId.current = data.session_id;
        setTel((prev) => addTelemetry(prev, data.run_telemetry));
        setCount((c) => c + 1);
        setResults((prev) =>
          [{ name: file.name, fields: data.fields, ocr_source: data.ocr_source, confidence: data.confidence }, ...prev].slice(0, 6),
        );
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function reset() {
    if (sessionId.current) {
      try {
        await fetch(`${apiBase}/demo/byo/reset`, { method: "POST", headers: headers() });
      } catch {
        /* ignore */
      }
    }
    sessionId.current = null;
    setResults([]);
    setErr(null);
    setCount(0);
    setTel(null);
  }

  return (
    <div>
      <p className="text-sm leading-relaxed text-dim">
        Upload a supplier bill (PDF or photo) and watch Vera read the key fields straight off it — vendor,
        invoice number, date and totals — no typing, no templates. It&apos;s processed in memory and forgotten
        when you leave.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <label className="btn cursor-pointer" style={busy ? { opacity: 0.5, pointerEvents: "none" } : undefined}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Upload className="h-4 w-4" aria-hidden />}
          {busy ? "Reading…" : "Upload a bill"}
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg"
            multiple
            className="hidden"
            onChange={(e) => uploadFiles(e.target.files)}
          />
        </label>
        {count > 0 && (
          <button onClick={reset} className="btn" aria-label="Reset session">
            <RotateCcw className="h-4 w-4" aria-hidden />
            Reset
          </button>
        )}
        <span className="font-mono text-[11px] text-dim">
          {count > 0 ? `${count} read · in memory, never stored` : "PDF / PNG / JPG"}
        </span>
      </div>

      {err && (
        <div
          className="mt-4 rounded-xl border p-3 text-sm"
          style={{ borderColor: "rgba(241,135,155,0.4)", background: "rgba(241,135,155,0.08)" }}
          role="alert"
        >
          <span style={{ color: "#f1879b" }}>{err}</span>
        </div>
      )}

      {/* the extracted fields — what Vera read off each uploaded bill (white "paper" card
          so it reads like the bill itself; dark-on-white palette, independent of theme) */}
      {results.map((r, i) => (
        <div key={i} className="mt-4 rounded-2xl p-4" style={{ background: "#ffffff", border: "0.5px solid #e2e5ea" }}>
          <div className="flex flex-wrap items-center gap-2">
            <CheckCircle2 className="h-4 w-4 shrink-0" style={{ color: "#1a9c54" }} aria-hidden />
            <span className="truncate text-sm font-semibold" style={{ color: "#1f2430" }}>Read from {r.name}</span>
            <span className="ml-auto font-mono text-[11px]" style={{ color: "#6b7280" }}>{r.ocr_source} · conf {r.confidence.toFixed(2)}</span>
          </div>
          <table className="mt-3 w-full text-sm">
            <tbody>
              {FIELD_ROWS.map(({ label, key, money: isMoney }, ri) => {
                const v = r.fields?.[key];
                const disp = v == null ? "—" : isMoney ? money(v as number) : String(v);
                return (
                  <tr key={key} style={ri < FIELD_ROWS.length - 1 ? { borderBottom: "0.5px solid #eceef1" } : undefined}>
                    <td className="py-1.5" style={{ color: "#6b7280" }}>{label}</td>
                    <td className="py-1.5 text-right tabular-nums" style={{ color: "#1f2430" }}>{disp}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}

      {/* Results — measured cost · latency · tokens for the bills you uploaded */}
      {tel && (
        <div className="mt-6">
          <RunMetrics
            telemetry={tel}
            accent={acc}
            heading="Results"
            subtitle="cost · latency · tokens for your uploads"
            scope="your uploads"
          />
        </div>
      )}

      <p className="mt-3 font-mono text-[11px] text-dim">Processed in memory · never written to disk · forgotten when you leave.</p>
    </div>
  );
}
