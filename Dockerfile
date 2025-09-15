FROM python:3.11-slim

# Install system dependencies for Chrome
RUN apt-get update && apt-get install -y \
    wget \
    gnupg2 \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

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

# Copy requirements first for better caching
COPY requirements.txt pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY examples/ ./examples/

# Install package in development mode
RUN pip install -e .

# Create chrome profile directory with proper permissions
RUN mkdir -p /app/chrome_profile && chown -R notebooklm:notebooklm /app/chrome_profile

# Switch to non-root user
USER notebooklm

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV NOTEBOOKLM_HEADLESS=true
ENV NOTEBOOKLM_PROFILE_DIR=/app/chrome_profile

# Expose MCP port (if needed for non-STDIO mode)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from notebooklm_mcp.config import ServerConfig; ServerConfig().validate()" || exit 1

# Default command
CMD ["notebooklm-mcp", "--config", "/app/config.json", "server", "--headless"]
