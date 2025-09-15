FROM python:3.11-slim

# Install system dependencies for Chrome and UV
RUN apt-get update && apt-get install -y \
    wget \
    gnupg2 \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install UV Python manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# Install Google Chrome
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver
RUN CHROMEDRIVER_VERSION=`curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE` && \
    wget -O /tmp/chromedriver.zip http://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip && \
    unzip /tmp/chromedriver.zip chromedriver -d /usr/local/bin/ && \
    rm /tmp/chromedriver.zip && \
    chmod +x /usr/local/bin/chromedriver

# Set up working directory
WORKDIR /app

# Create non-root user for security
RUN groupadd -r notebooklm && useradd -r -g notebooklm notebooklm
RUN chown -R notebooklm:notebooklm /app

# Copy project files for UV
COPY pyproject.toml uv.lock ./

# Install dependencies with UV
RUN uv sync --all-groups

# Copy source code
COPY src/ ./src/
COPY examples/ ./examples/

# Install package with UV
RUN uv pip install -e .

# Create chrome profile directory with proper permissions
RUN mkdir -p /app/chrome_profile && chown -R notebooklm:notebooklm /app/chrome_profile

# Switch to non-root user
USER notebooklm

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV UV_PYTHON=python3.11
ENV NOTEBOOKLM_CONFIG_FILE=/app/notebooklm-config.json

# Expose MCP ports
EXPOSE 8001 8002

# Health check with UV
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD uv run python -c "from notebooklm_mcp.config import ServerConfig; print('Config valid') if ServerConfig.from_file('/app/notebooklm-config.json') else exit(1)" || exit 1

# Default command - STDIO mode for MCP
CMD ["uv", "run", "python", "-m", "notebooklm_mcp.cli", "--config", "/app/notebooklm-config.json", "server"]
