#!/usr/bin/env bash
# jupyter/docker-stacks start hook: launch the colocated astro-archives MCP
# server on loopback before the single-user JupyterLab starts.
#
# Install: copy to /usr/local/bin/before-notebook.d/ in the single-user image.
# docker-stacks *sources* these files, so we background the server (never block
# startup) and make the launch idempotent (safe if the hook runs more than once).
#
# Pairs with ~/.jupyter/mcp_settings.json (see ../mcp_settings.json), which points
# the Jupyter AI persona at http://127.0.0.1:8000/mcp/.

ASTRO_MCP_PORT="${ASTRO_MCP_PORT:-8000}"

# Astropy/pyvo MUST have writable scratch for their caches, or every
# vo_target_resolve / vo_registry_search returns archive_error. Keep these on the
# user's (writable) home volume.
export TMPDIR="${TMPDIR:-$HOME/.cache/tmp}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
mkdir -p "$TMPDIR" "$XDG_CACHE_HOME"

if curl -sf "http://127.0.0.1:${ASTRO_MCP_PORT}/health" >/dev/null 2>&1; then
    echo "[astro-archives-mcp] already running on :${ASTRO_MCP_PORT}"
else
    echo "[astro-archives-mcp] starting on 127.0.0.1:${ASTRO_MCP_PORT}"
    STABLE_HOST=127.0.0.1 STABLE_PORT="${ASTRO_MCP_PORT}" STABLE_DEPLOYMENT=adl \
        nohup python -m astro_archives_mcp \
        >"$HOME/.astro-archives-mcp.log" 2>&1 &
fi
