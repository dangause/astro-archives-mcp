# Slice A — Staging Deployment Runbook

This is a manual deploy procedure for the first hosted Slice-A server.
Automation (k8s manifests, OIDC, OTel exporters) lands in later slices once
ADL/TACC ops have weighed in.

## Prereqs

- Access to whichever container host we land on for early staging
  (a small VM or a container PaaS will do for Slice A)
- Container registry credentials
- A public hostname terminating TLS in front of the container

## Build & push

```bash
docker build -t <registry>/astro-archives-mcp:0.1.0 .
docker push <registry>/astro-archives-mcp:0.1.0
```

## Run

```bash
docker run -d --restart=unless-stopped \
  -p 8000:8000 \
  -e STABLE_DEPLOYMENT=local \
  -e STABLE_LOG_LEVEL=INFO \
  --name astro-archives-mcp \
  <registry>/astro-archives-mcp:0.1.0
```

## Reverse-proxy notes (nginx example)

The MCP Streamable HTTP transport keeps a long-lived GET stream open. The
default 60–75s idle timeouts of nginx/ALB/CDN will silently kill the stream.

```nginx
location /mcp {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header MCP-Protocol-Version $http_mcp_protocol_version;
    proxy_read_timeout 3600s;
    proxy_buffering off;
    chunked_transfer_encoding on;
}
```

Per MCP spec 2025-11-25, return HTTP 403 on invalid `Origin`. Most reverse
proxies pass `Origin` through; do not strip it. Do not gzip the MCP stream.

Note: Starlette's `Mount("/mcp", ...)` issues a 307 redirect from `POST /mcp`
to `POST /mcp/`. Most MCP clients (including the Inspector CLI) follow
redirects automatically. If your reverse proxy strips trailing slashes
aggressively, configure it to preserve them on the `/mcp` path.

## Verify

From a machine that can reach the public hostname:

```bash
curl -fsS https://<host>/health
curl -fsS https://<host>/ready
npx -y @modelcontextprotocol/inspector --cli https://<host>/mcp --method tools/list
```

Expected: `vo_tap_query` listed.

## Rollback

`docker stop astro-archives-mcp && docker run … <registry>/astro-archives-mcp:<previous-tag>`
