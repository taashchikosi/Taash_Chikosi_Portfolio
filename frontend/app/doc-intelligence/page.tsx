// Case-study route per SHARED_SITE_CONTRACT.md → /doc-intelligence
// Drop this file at: frontend/app/doc-intelligence/page.tsx
// Server component (static). The live demo lives at /doc-intelligence/demo.
import Link from "next/link";

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section className="mb-10">
    <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">{title}</h2>
    <div className="text-slate-200">{children}</div>
  </section>
);

export default function DocIntelligenceCaseStudy() {
  return (
    <main className="mx-auto max-w-3xl px-5 py-12 text-slate-100">
      {/* 1. Hero */}
      <p className="mb-2 text-sm font-medium text-indigo-300">Document AI · back-office automation</p>
      <h1 className="text-3xl font-bold tracking-tight">Invoice Document Intelligence</h1>
      <p className="mt-3 text-lg text-slate-300">
        Reads any vendor invoice, checks the maths, <b>catches duplicate-payment fraud</b>, and
        escalates what it isn’t sure of — under 2 minutes vs the industry-average 9.2 days, on a
        CPU box with no GPU.
      </p>
      <div className="mt-5 flex gap-3">
        <Link href="/doc-intelligence/demo"
          className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-400">
          ▶ Try the live demo
        </Link>
        <a href="https://github.com/taashchikosi/doc-intelligence"
          className="rounded-lg border border-white/15 px-4 py-2 text-sm hover:border-indigo-400">
          GitHub repo
        </a>
      </div>

      <div className="my-10 h-px bg-white/10" />

      {/* 2. Problem */}
      <Section title="The problem">
        Manual invoice processing is slow and error-prone — the Ardent Partners 2025 benchmark puts
        the average invoice at <b>$12.88 and 9.2 days</b>, and duplicate or fraudulent payments are a
        costly, under-caught failure mode. AP teams in finance, insurance and RPA shops want this
        automated <i>and</i> trustworthy: a wrong number posted silently is worse than a slow one.
      </Section>

      {/* 3. Architecture */}
      <Section title="How it works">
        <p className="mb-3">
          Digital-first text (skips OCR when a PDF has a text layer) → OCR fallback for scans
          (RapidOCR, CPU) → field extraction (DeepSeek) → deterministic validation (maths · date ·
          fuzzy-duplicate) → a confidence gate that <b>approves or escalates to a human</b>.
        </p>
        <pre className="overflow-x-auto rounded-xl border border-white/10 bg-black/30 p-4 text-xs text-slate-300">
{`upload → security guard → digital-first text / OCR
      → extract fields → validate (maths·date·dupe)
      → confidence gate → approve  ·  escalate → human queue`}
        </pre>
      </Section>

      {/* 4. Live demo */}
      <Section title="See it live">
        The <Link href="/doc-intelligence/demo" className="text-indigo-300 underline">live demo</Link> runs
        four invoices: a clean one approves, a messy layout still reads, a prompt-injection attempt is
        blocked, and a near-duplicate is <b>caught as fraud</b> — with a running tally of dollars saved
        and fraud prevented. You can also drag in your own invoice.
      </Section>

      {/* 5. Eval metrics */}
      <Section title="The numbers (measured, honest)">
        <ul className="list-inside list-disc space-y-1 text-slate-300">
          <li><b>94.3% fair field-F1</b> (95% CI 91.1–97.4) vs a <b>30.8% regex baseline</b>, measured on <b>28 real invoices across 19 vendors</b> (AUD/USD/CAD).</li>
          <li><b>77.4% strict exact-match</b> on the same set — disclosed alongside the fair score, not instead of it. “Fair” accepts the full legal vendor name and ignores invoice-number spacing/punctuation; “strict” demands a character-exact match.</li>
          <li>Per field: date <b>100%</b>, total <b>100%</b>, vendor 96.4%, invoice # 96.4%, tax 85.7%, subtotal 75%.</li>
          <li><b>$0.00022 / invoice</b> (DeepSeek tokens) vs the <b>$12.88</b> manual benchmark (Ardent Partners 2025).</li>
        </ul>
        <div className="mt-4 rounded-xl border border-amber-300/30 bg-amber-300/[0.06] p-3 text-sm text-slate-300">
          <b>About the numbers:</b> N is small (28 invoices), so the confidence interval is wide — and shown,
          not hidden. The live demo isn’t an accuracy claim; the real-invoice F1 above is the anchor (synthetic
          FATURA layouts only validate the harness and can overstate real-scan accuracy). Residual misses
          cluster on <b>subtotal extraction for GST-inclusive invoices</b> — the deterministic maths-check
          catches those and escalates them to a human rather than posting a wrong number.
        </div>
      </Section>

      {/* 6. Technical decisions */}
      <Section title="Why these choices">
        <ul className="list-inside list-disc space-y-1 text-slate-300">
          <li><b>FastAPI, not n8n</b> — per-field confidence, the audit trail and the fraud logic hit a no-code ceiling. This is the code-based demo of the portfolio.</li>
          <li><b>CPU OCR (RapidOCR), not a GPU vision model</b> — invoices read well without a GPU; the parser is pluggable, so a high-volume client could swap in a layout-aware VLM on GPU.</li>
          <li><b>Confidence ≠ a model logprob</b> — it’s validation pass/fail + whether each value is verifiable in the source text, with the escalate threshold calibrated to a business-cost target.</li>
          <li><b>Security</b> — invoices are untrusted input: a prompt-injection guard, file-type/size limits, rate limiting, server-side keys.</li>
        </ul>
      </Section>

      {/* 7. Links */}
      <Section title="Links">
        <div className="flex flex-wrap gap-3 text-sm">
          <Link href="/doc-intelligence/demo" className="text-indigo-300 underline">Live demo</Link>
          <a href="https://github.com/taashchikosi/doc-intelligence" className="text-indigo-300 underline">GitHub</a>
          <span className="text-slate-500">Reproduce the number: <code>python eval/run_eval.py --extractor llm</code></span>
        </div>
      </Section>
    </main>
  );
}
