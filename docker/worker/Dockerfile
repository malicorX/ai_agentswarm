# Build from repo root:
#   docker build -f docker/worker/Dockerfile -t agentswarm-worker:dev .
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY platform /src/platform
COPY agents /src/agents

RUN pip install --no-cache-dir -q -U pip && \
    pip install --no-cache-dir -q -e /src/platform -e /src/agents && \
    pip install --no-cache-dir -q llama-cpp-python==0.3.4

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "agentswarm_agents.worker_runtime"]
