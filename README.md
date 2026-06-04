# astro-archives-mcp

MCP server exposing IVOA-compliant astronomical archives (NOIRLab Astro Data Lab, NRAO/ALMA, CADC, ESO, Gaia, …) to LLM clients.

Five sync IVOA tools shipping today: `vo_tap_query`, `vo_cone_search`, `vo_sia_search`, `vo_registry_search`, `vo_registry_describe`. Architecture notes in `CLAUDE.md`.

## Quickstart

```bash
uv sync
uv run pytest --record-mode=none
uv run python -m astro_archives_mcp
# server on http://localhost:8000, MCP endpoint at /mcp
```

Smoke test with MCP Inspector:
```bash
npx -y @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/list
```

## Refreshing recorded cassettes

Tests replay archive HTTP traffic from YAML cassettes in `tests/<area>/cassettes/`. When an upstream archive changes its response format, a cassette will eventually need re-recording. To refresh one:

```bash
# requires network access to the archive endpoint
rm tests/<area>/cassettes/<test_module>/<test_name>.yaml
uv run pytest tests/<area>/<test_module>.py::<test_name> --record-mode=once
```

Inspect the new cassette's diff before committing — large changes in the VOTable namespace URI or response headers may indicate an upstream breaking change worth a quick code-side review.
