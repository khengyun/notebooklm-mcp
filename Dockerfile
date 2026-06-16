FROM python:3.11-slim

# Install system dependencies (Chrome is installed below; Patchright manages
# its own browser driver, so no chromedriver download is needed).
RUN apt-get update && apt-get install -y \
    wget \
    gnupg2 \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install UV Python manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:/root/.cargo/bin:$PATH"

# Install Google Chrome (drives the app via Patchright channel="chrome").
# Uses the modern signed-by keyring method (apt-key is deprecated/removed).
RUN wget -q -O /usr/share/keyrings/google-chrome.gpg.key https://dl.google.com/linux/linux_signing_key.pub \
    && gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg /usr/share/keyrings/google-chrome.gpg.key \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Create non-root user for security
RUN groupadd -r notebooklm && useradd -r -g notebooklm notebooklm
RUN chown -R notebooklm:notebooklm /app

# Copy project files for UV
COPY pyproject.toml uv.lock ./

# Install dependencies with UV
RUN uv sync --all-groups

# Ensure Patchright's browser system libraries are present (Chrome already
# pulls most of them; this covers any gaps for headless Chromium fallback).
RUN uv run patchright install-deps chromium || true

# Copy source code
COPY src/ ./src/
COPY examples/ ./examples/

# Install package with UV
RUN uv pip install -e .

# Create chrome profile directory with proper permissions
RUN mkdir -p /app/chrome_profile_notebooklm \
    && chown -R notebooklm:notebooklm /app/chrome_profile_notebooklm

# Switch to non-root user
USER notebooklm

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV UV_PYTHON=python3.11
ENV NOTEBOOKLM_CONFIG_FILE=/app/notebooklm-config.json

# Expose the HTTP MCP port
EXPOSE 8001

# Health check — validates the config file parses.
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD uv run python -c "from notebooklm_mcp.config import ServerConfig; ServerConfig.from_file('/app/notebooklm-config.json')" || exit 1

# Default command: HTTP transport. A detached container has no stdin, so STDIO
# would idle with no client — HTTP is the correct transport for `docker run -d`.
CMD ["uv", "run", "python", "-m", "notebooklm_mcp.cli", "--config", "/app/notebooklm-config.json", \
     "server", "--transport", "http", "--host", "0.0.0.0", "--port", "8001"]
