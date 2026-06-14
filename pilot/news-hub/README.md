# AI News Hub (Phase 0 pilot)

Minimal static site scaffold. Codewriter agents patch files here; the tester runs `pytest tests/`.

## Build / verify

```powershell
python -m pytest tests -q
```

Open `index.html` in a browser after a codewriter task applies a patch.

## Sample codewriter payload

```json
{
  "file": "index.html",
  "insert": "<p id=\"swarm-demo\">Patched by AgentSwarm.</p>"
}
```
