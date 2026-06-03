# astro-archives-mcp

MCP server exposing IVOA-compliant astronomical archives (NOIRLab Astro Data Lab, NRAO/ALMA, etc.) to LLM clients.

Design: `docs/superpowers/specs/2026-06-02-stable-mcp-design.md`
Slice A plan: `docs/superpowers/plans/2026-06-02-slice-a-server-skeleton.md`

## Quickstart (Slice A)

```bash
uv sync
uv run pytest
uv run python -m astro_archives_mcp
# server on http://localhost:8000, MCP endpoint at /mcp
```

Smoke test with MCP Inspector:
```bash
npx -y @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/list
```
