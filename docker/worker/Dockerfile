# Build from repo root:
#   docker build -f docker/worker/Dockerfile -t agentswarm-worker:dev .
FROM python:3.12-slim

WORKDIR /app

COPY agents/src/agentswarm_agents/capsule_executor.py /app/capsule_executor.py
COPY docker/worker/entrypoint.py /app/entrypoint.py

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "/app/entrypoint.py"]
