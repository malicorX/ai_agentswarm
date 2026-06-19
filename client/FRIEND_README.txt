AgentSwarm Volunteer — quick start (Windows)
============================================

You received this to run engineering/creative tasks for a shared AgentSwarm platform.
You are a WORKER, not the operator who dispatches goals.

What to install first
---------------------
1. Docker Desktop (required for git/sandbox engineering tasks)
   https://www.docker.com/products/docker-desktop/

2. Pull the worker image once (ask whoever sent you this for the exact command).
   Typical:
     docker pull agentswarm-worker:dev
   Or they may send a build script from the main repo.

Run the volunteer
-----------------
1. Unzip the whole folder (if you received a zip). Run AgentSwarmVolunteer.exe
   from inside dist\AgentSwarmVolunteer\ — do not copy only the .exe alone.

2. Windows SmartScreen may warn on first run — choose "More info" → Run anyway.

2. In the GUI:
   - Platform URL: https://theebie.de/agentswarm/api  (or URL your friend gave you)
   - Owner: pick a unique id, e.g. volunteer-yourname  (operator must use this for resume/dispatch)
   - Preset: "Engineering git (full pipeline)" for coding tasks
   - Model: docker/qwen2.5-coder-3b (or what your platform allowlist shows)
   - Click Prepare model (downloads ~2 GB once to %LOCALAPPDATA%\AgentSwarm)
   - Click Start

3. Leave it running while tasks are queued. It polls the platform and runs work in Docker.

What this does NOT include
--------------------------
- Task console (dispatch / watch UI) — needs the full AgentSwarm repo on the operator PC.
- Platform server — goals are posted to a shared URL, not your PC.
- Git credentials — private repos need setup on the operator side.

Troubleshooting
---------------
- "Docker not available" → start Docker Desktop.
- No tasks → operator must dispatch a goal; check Platform URL and owner id.
- Model download fails → check disk space (~2 GB) and internet.
