# 🚀 RetrofitGPT — VPS deploy runbook

Follow top to bottom. Replace every `<PLACEHOLDER>` with your value. The backend runs
on your VPS in Docker; the frontend on Vercel. The two are linked by ONE matched pair:
`NEXT_PUBLIC_API_BASE` (frontend → backend URL) ↔ `ALLOWED_ORIGINS` (backend allows
frontend origin). If those don't match, the browser blocks every call.

```
Recruiter → Vercel (Next.js)  ──HTTPS──►  Caddy (TLS) ──► docker: app :8080 + db
            NEXT_PUBLIC_API_BASE            api.<domain>      (ALLOWED_ORIGINS lets it in)
```

---

## ✅ Phase 0 — Prerequisites (one-time)

- [ ] VPS reachable over SSH, Docker + `docker compose` v2 installed
      (`docker --version && docker compose version`).
- [ ] A domain you control. Add a DNS **A record**: `api.<yourdomain>` → `<VPS_IP>`.
- [ ] VPS firewall allows ports **80 + 443** (Caddy). Port 8080 stays *internal*.
- [ ] Your `ANTHROPIC_API_KEY` and `DEEPSEEK_API_KEY` handy (do NOT paste them in chat).
- [ ] VPS has ≥ **2 GB RAM** free (EnergyPlus needs headroom).

---

## ⚙️ Phase 1 — Backend on the VPS

```bash
# 1. SSH in and get the code
ssh <user>@<VPS_IP>
git clone <YOUR_REPO_URL> retrofitgpt        # or scp the folder up
cd retrofitgpt

# 2. Create the PRODUCTION .env  (nano .env, paste the block below)
```

```ini
# --- .env on the VPS ---
ANTHROPIC_API_KEY=<your-key>
DEEPSEEK_API_KEY=<your-key>

# ⚠️ DO NOT set LLM_PROVIDER here. Leaving it UNSET = the cost-tiered, eval-gated
# default (classify+reviewer→Claude, bulk→DeepSeek). Setting =anthropic is DEV ONLY
# and would route everything to Claude (expensive).

# CORS — fill in AFTER you have the Vercel URL (Phase 4). For now a placeholder:
ALLOWED_ORIGINS=https://<your-project>.vercel.app

# Abuse / cost guards (optional — these are the defaults)
LLM_MAX_TOKENS_PER_DAY=500000
RATE_LIMIT_PER_MIN=30
```

```bash
# 3. Fetch the Sydney weather file (needed for the live EnergyPlus run)
docker compose run --rm app python scripts/download_reference_data.py

# 4. Build + start (FIRST build ~50 min — EnergyPlus image, slow on home networks.
#    Rebuilds are cached. Run in tmux/screen so an SSH drop doesn't kill it.)
docker compose up -d --build

# 5. Verify the API is alive ON THE BOX
curl -s http://localhost:8080/health | python3 -m json.tool
#    Expect: "status": "ok"  and a "token_budget" block.
```

If `/health` shows `"status": "ok"` → backend is up. ✅

---

## 🔒 Phase 2 — Caddy reverse proxy + TLS

If Caddy is already running on the VPS, just add the block. If not, install it
(`https://caddyserver.com/docs/install`), then edit `/etc/caddy/Caddyfile`:

```caddy
api.<yourdomain> {
    reverse_proxy localhost:8080
}
```

```bash
sudo systemctl reload caddy        # Caddy fetches a TLS cert automatically
curl -s https://api.<yourdomain>/health | python3 -m json.tool   # now over HTTPS
```

HTTPS `/health` returns ok → backend is public. ✅

---

## 🖥️ Phase 3 — Frontend on Vercel

1. Push the repo to GitHub (if not already).
2. Vercel → **Add New Project** → import the repo.
3. **Root Directory = `frontend`** (important — the Next app lives there).
4. Environment Variables → add:
   `NEXT_PUBLIC_API_BASE = https://api.<yourdomain>`
5. **Deploy.** Note the URL, e.g. `https://<your-project>.vercel.app`.

---

## 🔗 Phase 4 — Close the CORS loop (the step everyone forgets)

```bash
# Back on the VPS: set ALLOWED_ORIGINS to the EXACT Vercel URL from Phase 3
cd retrofitgpt
nano .env          # ALLOWED_ORIGINS=https://<your-project>.vercel.app
docker compose up -d --force-recreate app    # reloads env
```

Add your custom domain too if you have one (comma-separated, no trailing slash):
`ALLOWED_ORIGINS=https://<your-project>.vercel.app,https://www.<yourdomain>`

---

## 🧪 Phase 5 — Smoke test (the moment of truth)

1. Open `https://<your-project>.vercel.app/retrofitgpt` → the status dot should be 🟢 **live**.
2. Open `https://<your-project>.vercel.app/` → click **Run the demo**.
3. Watch the five agents go idle → running → done, the HITL line auto-approve, and the
   **Business case** card appear with a green **Reviewer approved** + **Demo calibration** badge.

If that renders, you are deployed. 🎉

---

## 🆘 Troubleshooting (most-likely first)

| Symptom | Cause → fix |
|---|---|
| Browser console: **CORS blocked** | `ALLOWED_ORIGINS` ≠ the Vercel URL. Match it exactly (scheme, no trailing slash), `--force-recreate app`. |
| Status dot **offline** / demo can't start | `NEXT_PUBLIC_API_BASE` wrong, Caddy not proxying, or backend down. `curl https://api.<yourdomain>/health`. |
| Run returns **503 budget** | Daily token cap hit. Raise `LLM_MAX_TOKENS_PER_DAY` and `--force-recreate app`. |
| Run returns **429** | Per-IP rate limit. Expected under hammering; raise `RATE_LIMIT_PER_MIN` if needed. |
| `/health` shows `live_simulation_available: false` | EPW/EnergyPlus missing — re-run Phase 1 step 3. |
| First build times out | Run inside `tmux`; it's the EnergyPlus image. Rebuilds are cached. |
| Container killed mid-run | Out of RAM — EnergyPlus is heavy. Size the box ≥ 2 GB. |

---

## 🔁 Day-2 ops

```bash
docker compose logs -f app          # tail logs
docker compose pull && docker compose up -d --build   # deploy new code
curl https://api.<yourdomain>/health                  # health + token budget
```

> Reminder: `NEXT_PUBLIC_API_BASE` is baked at Vercel **build** time — if you change it,
> redeploy the frontend.
