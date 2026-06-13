# syntax=docker/dockerfile:1
# EnergyPlus ships x86_64-only Linux binaries, so this image MUST be amd64.
# Platform is pinned in docker-compose.yml (platform: linux/amd64); on Apple
# Silicon it runs under emulation — slower, but it works.
FROM python:3.11-slim

# ── EnergyPlus install ───────────────────────────────────────────────
# Pin a known release; bump ENERGYPLUS_VERSION to upgrade.
# SHA must match the GitHub release asset EXACTLY (verified v24.2.0 = e7ecb2d53b).
ENV ENERGYPLUS_VERSION=24.2.0 \
    ENERGYPLUS_SHA=e7ecb2d53b
ENV ENERGYPLUS_TAG=v${ENERGYPLUS_VERSION}
ENV ENERGYPLUS_INSTALL_DIR=/usr/local/EnergyPlus

# Runtime deps for EnergyPlus (X11 + expat), plus curl/ca-certificates to fetch it.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates libx11-6 libexpat1 \
    && rm -rf /var/lib/apt/lists/*

# Download EnergyPlus into a BuildKit CACHE MOUNT so a partial download SURVIVES
# across build attempts: a dropped transfer resumes instead of restarting the
# 185 MB from zero — essential on a slow link. Works on CI/deploy too (an empty
# cache just downloads fresh). Hardened for flaky networks:
#   --http1.1   avoids the HTTP/2 "PROTOCOL_ERROR (err 92)" seen at 91%
#   -C - / --retry   resume + retry up to 5x
#   --speed-*   abandon a stalled (<1 KB/s for 60s) connection so retry fires
#   -f          fail loudly on a 404 (never save GitHub's HTML error page)
RUN --mount=type=cache,target=/opt/ep-cache <<'EOF'
set -e
EP=/opt/ep-cache/ep.tar.gz
if ! gzip -t "$EP" 2>/dev/null; then
  echo "Downloading EnergyPlus ${ENERGYPLUS_VERSION} (resumable)…"
  curl -fSL --http1.1 --retry 5 --retry-delay 5 --retry-all-errors -C - \
       --speed-limit 1024 --speed-time 60 \
       "https://github.com/NREL/EnergyPlus/releases/download/${ENERGYPLUS_TAG}/EnergyPlus-${ENERGYPLUS_VERSION}-${ENERGYPLUS_SHA}-Linux-Ubuntu22.04-x86_64.tar.gz" \
       -o "$EP"
else
  echo "Using cached EnergyPlus tarball (no re-download)."
fi
mkdir -p "${ENERGYPLUS_INSTALL_DIR}"
tar -xzf "$EP" -C "${ENERGYPLUS_INSTALL_DIR}" --strip-components=1
EOF

# pyenergyplus ships inside the EnergyPlus install
ENV PYTHONPATH="${ENERGYPLUS_INSTALL_DIR}:${PYTHONPATH}" \
    PATH="${ENERGYPLUS_INSTALL_DIR}:${PATH}"

# ── App ──────────────────────────────────────────────────────────────
WORKDIR /workspace
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# EnergyPlus is linked against the GNU OpenMP runtime (libgomp.so.1), which the
# slim base image doesn't ship. Installed in its OWN layer AFTER pip so adding
# it doesn't bust the slow pip-install cache layer above. (Could be folded into
# the first apt layer later, when network speed isn't the bottleneck.)
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY . .

EXPOSE 8000 8501 8080

# Phase 1: run the MCP server. Later phases switch to a supervisor entrypoint.
CMD ["python", "-m", "mcp_server.server"]
