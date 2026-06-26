# Reference single-user image for gp12: a Jupyter AI notebook server with the
# astro-archives MCP server colocated on loopback (Topology A in
# ../../deploy/gp12-runbook.md).
#
# BUILD FROM THIS DIRECTORY as the context — NOT the repo root:
#     docker build -t astro-archives-singleuser docs/examples/gp12/
# The repo-root .dockerignore excludes docs/ (and deploy/, tests/), so a
# repo-root context can't see the hook or config. Using this subdir as the
# context sidesteps that and picks up before-notebook.d/ + mcp_settings.json.
#
# Validated locally (2026-06-26) against minimal-notebook: package install, the
# before-notebook.d hook launching the server on loopback, writable astropy
# cache, and tools returning real data. NOT yet validated: node + the Claude ACP
# adapter / persona LLM call, and gp12's actual base image — confirm both.

ARG BASE_IMAGE=quay.io/jupyter/minimal-notebook:latest
FROM ${BASE_IMAGE}

# --- Python deps: this MCP server + Jupyter AI ---
USER ${NB_UID}
RUN pip install --no-cache-dir \
      "astro-archives-mcp @ git+https://github.com/dangause/astro-archives-mcp.git@v0.3.0" \
      "jupyter-ai>=3" jupyterlab

# --- Node + the Claude ACP adapter (the persona's agent binary) ---
# Skip if backing the persona with a local model instead (see docs/local-model-backend.md).
USER root
RUN mamba install -y -c conda-forge nodejs && mamba clean -afy \
    && npm install -g @zed-industries/claude-agent-acp

# --- Colocated MCP server: startup hook (loopback, writable cache) ---
COPY before-notebook.d/10-astro-archives-mcp.sh \
     /usr/local/bin/before-notebook.d/10-astro-archives-mcp.sh
RUN chmod +x /usr/local/bin/before-notebook.d/10-astro-archives-mcp.sh

# --- Seed the MCP config where Jupyter AI resolves it (home/.jupyter) ---
USER ${NB_UID}
COPY --chown=${NB_UID}:${NB_GID} mcp_settings.json /home/${NB_USER}/.jupyter/mcp_settings.json
