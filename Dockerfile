FROM python:3.11-slim

# ── EnergyPlus install ───────────────────────────────────────────────
# Pin a known release; bump ENERGYPLUS_VERSION to upgrade.
ENV ENERGYPLUS_VERSION=24.2.0 \
    ENERGYPLUS_SHA=94a887817b
ENV ENERGYPLUS_TAG=v${ENERGYPLUS_VERSION}
ENV ENERGYPLUS_INSTALL_DIR=/usr/local/EnergyPlus

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates libx11-6 libexpat1 \
    && rm -rf /var/lib/apt/lists/* \
    && curl -SL "https://github.com/NREL/EnergyPlus/releases/download/${ENERGYPLUS_TAG}/EnergyPlus-${ENERGYPLUS_VERSION}-${ENERGYPLUS_SHA}-Linux-Ubuntu22.04-x86_64.tar.gz" \
       -o /tmp/ep.tar.gz \
    && mkdir -p ${ENERGYPLUS_INSTALL_DIR} \
    && tar -xzf /tmp/ep.tar.gz -C ${ENERGYPLUS_INSTALL_DIR} --strip-components=1 \
    && rm /tmp/ep.tar.gz

# pyenergyplus ships inside the EnergyPlus install
ENV PYTHONPATH="${ENERGYPLUS_INSTALL_DIR}:${PYTHONPATH}" \
    PATH="${ENERGYPLUS_INSTALL_DIR}:${PATH}"

# ── App ──────────────────────────────────────────────────────────────
WORKDIR /workspace
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000 8501 8080

# Phase 1: run the MCP server. Later phases switch to a supervisor entrypoint.
CMD ["python", "-m", "mcp_server.server"]
