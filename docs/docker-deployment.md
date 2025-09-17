# 🐳 Docker Deployment Guide

This guide walks through running the NotebookLM MCP server in Docker. The
container already knows how to locate its configuration at
`/app/notebooklm-config.json`, so the recommended approach is to mount the
generated config file and Chrome profile into the container instead of passing
dozens of environment variables.

## Prerequisites

- Docker Engine 24+ and Docker Compose v2
- NotebookLM MCP CLI installed locally (`uv add notebooklm-mcp` or `pip install
  notebooklm-mcp`) so you can run the guided `init` workflow
- A Google account with access to the NotebookLM notebook you plan to
  automate

## 1. Generate the config and Chrome profile

```bash
# Creates notebooklm-config.json and chrome_profile_notebooklm/
uv run notebooklm-mcp init https://notebooklm.google.com/notebook/YOUR_NOTEBOOK_ID

# If you installed via pip, drop the `uv run` prefix:
# notebooklm-mcp init https://notebooklm.google.com/notebook/YOUR_NOTEBOOK_ID
```

The guided setup launches Chrome, walks you through the Google login flow and
produces:

- `notebooklm-config.json` containing your notebook ID and runtime settings
- `chrome_profile_notebooklm/` populated with the authenticated Chrome profile

Keep both artifacts—they are required for Docker deployments.

Key fields inside the JSON file:

- `default_notebook_id`: the NotebookLM notebook to open by default
- `auth.profile_dir`: where the Chrome profile will live inside the container
  (defaults to `/app/chrome_profile_notebooklm` when mounted)
- `headless`, `timeout`, `debug`: behaviour of the automated browser session

## 2. Run with plain Docker

With the artifacts from the `init` command available in your working directory,
build the image and start the container. The example below assumes you built the
image locally with `docker build -t notebooklm-mcp .`.

```bash
# Start the container (STDIO transport by default)
docker run -d \
  --name notebooklm-mcp \
  --restart unless-stopped \
  -v $(pwd)/notebooklm-config.json:/app/notebooklm-config.json:ro \
  -v $(pwd)/chrome_profile_notebooklm:/app/chrome_profile_notebooklm \
  notebooklm-mcp:latest
```

The container executes `uv run python -m notebooklm_mcp.cli --config
/app/notebooklm-config.json server`, so any changes to the mounted config file
are picked up on the next restart.

## 3. Run with Docker Compose (recommended)

The Compose file included in the repository is already configured to mount both
artifacts. Ensure `notebooklm-config.json` and `chrome_profile_notebooklm/`
exist (created by the `init` command), then run:

```bash
docker compose up -d
```

The relevant section of `docker-compose.yml` looks like this:

```yaml
services:
  notebooklm-mcp:
    build: .
    image: notebooklm-mcp:latest
    restart: unless-stopped
    volumes:
      - ./notebooklm-config.json:/app/notebooklm-config.json:ro
      - ./chrome_profile_notebooklm:/app/chrome_profile_notebooklm
```

No additional environment variables are required. The mounted config controls
all NotebookLM and browser behaviour. To stop the stack, run `docker-compose down`.

## 4. Choosing a transport

The server runs in STDIO mode by default. To expose HTTP or SSE transports,
uncomment the relevant ports in `docker-compose.yml`:

```yaml
    # ports:
    #   - "8001:8001"  # HTTP transport
    #   - "8002:8002"  # SSE transport
```

Then restart the services:

```bash
docker-compose up -d
```

## 5. Optional environment overrides

Mounting the JSON file should cover most scenarios. If you need to override a
single setting temporarily, you can still use environment variables. They follow
the same names as the CLI flags:

| Variable | Description |
|----------|-------------|
| `NOTEBOOKLM_NOTEBOOK_ID` | Override the default notebook at runtime |
| `NOTEBOOKLM_HEADLESS` | Set to `false` to open a visible Chrome window |
| `NOTEBOOKLM_TIMEOUT` | Browser wait timeout in seconds |
| `NOTEBOOKLM_PROFILE_DIR` | Custom path for the Chrome profile inside the container |

Add them under the `environment:` block in Compose or pass `-e` flags to
`docker run` when needed.

## 6. Monitoring stack (optional)

A Prometheus and Grafana profile is included. Launch everything with:

```bash
docker-compose --profile monitoring up -d
```

Grafana becomes available at <http://localhost:3000> (default credentials
`admin` / `admin`).

## 7. Troubleshooting tips

- **Chrome login prompts**: make sure the `chrome_profile_notebooklm` directory
  is writable by the container user (UID/GID 1001). On Linux hosts you may need
  to `chown` the folder.
- **Config not found**: verify the mount path matches `/app/notebooklm-config.json`
  and that the file contains valid JSON.
- **Transport connection issues**: if using HTTP/SSE mode, confirm the ports are
  exposed and not blocked by firewalls.

With the config file and profile mounted, your container runs with the exact
settings you maintain locally—no long lists of environment variables required.
