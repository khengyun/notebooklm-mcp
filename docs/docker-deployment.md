# 🐳 Docker Deployment Guide

This guide covers deploying NotebookLM MCP Server using Docker and Docker Compose.

## 🚀 Quick Start

### **Environment Setup**

Create a `.env` file:

```bash
# Required: Your NotebookLM notebook ID
NOTEBOOKLM_NOTEBOOK_ID=your-notebook-id-here

# Optional: Additional settings
NOTEBOOKLM_DEBUG=false
NOTEBOOKLM_TIMEOUT=60
```

### **Basic Docker Run**

```bash
# Build image
docker build -t notebooklm-mcp .

# Run container
docker run -d \
  --name notebooklm-mcp \
  -e NOTEBOOKLM_NOTEBOOK_ID="your-notebook-id" \
  -v notebooklm_profile:/app/chrome_profile \
  notebooklm-mcp:latest
```

### **Docker Compose (Recommended)**

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f notebooklm-mcp

# Stop services
docker-compose down
```

## 📊 **Monitoring Setup**

Enable monitoring stack with Prometheus and Grafana:

```bash
# Start with monitoring
docker-compose --profile monitoring up -d

# Access Grafana: http://localhost:3000
# Username: admin, Password: admin
```

## 🔧 **Configuration**

### **Environment Variables**

| Variable | Default | Description |
|----------|---------|-------------|
| `NOTEBOOKLM_NOTEBOOK_ID` | None | Target notebook ID (required) |
| `NOTEBOOKLM_HEADLESS` | true | Run browser in headless mode |
| `NOTEBOOKLM_DEBUG` | false | Enable debug logging |
| `NOTEBOOKLM_TIMEOUT` | 60 | Browser timeout in seconds |
| `NOTEBOOKLM_PROFILE_DIR` | /app/chrome_profile | Chrome profile directory |

### **Volume Mounts**

- `chrome_profile:/app/chrome_profile` - Persistent browser session
- `./config.json:/app/config.json:ro` - Configuration file (optional)
- `./scripts:/app/scripts:ro` - Custom scripts (optional)

## 🏭 **Production Deployment**

### **Kubernetes**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: notebooklm-mcp
  labels:
    app: notebooklm-mcp
spec:
  replicas: 1
  selector:
    matchLabels:
      app: notebooklm-mcp
  template:
    metadata:
      labels:
        app: notebooklm-mcp
    spec:
      containers:
      - name: notebooklm-mcp
        image: notebooklm-mcp:latest
        env:
        - name: NOTEBOOKLM_HEADLESS
          value: "true"
        - name: NOTEBOOKLM_NOTEBOOK_ID
          valueFrom:
            secretKeyRef:
              name: notebooklm-config
              key: notebook-id
        volumeMounts:
        - name: chrome-profile
          mountPath: /app/chrome_profile
        resources:
          limits:
            cpu: 2000m
            memory: 2Gi
          requests:
            cpu: 500m
            memory: 512Mi
        livenessProbe:
          exec:
            command:
            - python
            - -c
            - "from notebooklm_mcp.config import ServerConfig; ServerConfig().validate()"
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          exec:
            command:
            - python
            - -c
            - "from notebooklm_mcp.config import ServerConfig; ServerConfig().validate()"
          initialDelaySeconds: 5
          periodSeconds: 10
      volumes:
      - name: chrome-profile
        persistentVolumeClaim:
          claimName: chrome-profile-pvc
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: chrome-profile-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
```

### **Docker Swarm**

```yaml
version: '3.8'

services:
  notebooklm-mcp:
    image: notebooklm-mcp:latest
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
    environment:
      - NOTEBOOKLM_HEADLESS=true
      - NOTEBOOKLM_NOTEBOOK_ID=${NOTEBOOKLM_NOTEBOOK_ID}
    volumes:
      - chrome_profile:/app/chrome_profile
    networks:
      - notebooklm-network

volumes:
  chrome_profile:
    driver: local

networks:
  notebooklm-network:
    driver: overlay
```

## 🛠️ **Development**

### **Development Docker Compose**

```yaml
version: '3.8'

services:
  notebooklm-mcp-dev:
    build:
      context: .
      dockerfile: Dockerfile.dev  # Development dockerfile
    volumes:
      - .:/app
      - chrome_profile:/app/chrome_profile
    environment:
      - NOTEBOOKLM_HEADLESS=false  # Show browser for debugging
      - NOTEBOOKLM_DEBUG=true
      - NOTEBOOKLM_NOTEBOOK_ID=${NOTEBOOKLM_NOTEBOOK_ID}
    ports:
      - "8000:8000"  # For debugging
    command: ["notebooklm-mcp", "server", "--debug"]

volumes:
  chrome_profile:
```

### **Multi-stage Build**

```dockerfile
# Development stage
FROM python:3.11-slim as development
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["notebooklm-mcp", "server", "--debug"]

# Production stage
FROM python:3.11-slim as production
# ... production setup
CMD ["notebooklm-mcp", "server", "--headless"]
```

## 📊 **Monitoring & Logging**

### **Prometheus Metrics**

Access metrics at: http://localhost:9090

Key metrics to monitor:
- Container resource usage
- Browser startup time
- Authentication success rate
- Response times

### **Grafana Dashboards**

Access Grafana at: http://localhost:3000

Pre-configured dashboards:
- System metrics
- Application performance
- Error rates
- Browser session health

### **Log Aggregation**

```yaml
# Add to docker-compose.yml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

## 🔒 **Security**

### **Security Best Practices**

1. **Non-root user**: Container runs as `notebooklm` user
2. **Read-only filesystem**: Where possible
3. **Resource limits**: CPU and memory limits set
4. **No new privileges**: Security option enabled
5. **Secrets management**: Use Docker secrets or K8s secrets

### **Secrets Management**

```bash
# Docker secrets
echo "your-notebook-id" | docker secret create notebook_id -

# Use in compose
secrets:
  - notebook_id

environment:
  - NOTEBOOKLM_NOTEBOOK_ID_FILE=/run/secrets/notebook_id
```

## 🚨 **Troubleshooting**

### **Common Issues**

1. **Chrome crashes**:
   ```bash
   docker logs notebooklm-mcp
   # Check for memory limits
   ```

2. **Authentication fails**:
   ```bash
   # Clear chrome profile
   docker volume rm notebooklm-mcp_chrome_profile
   ```

3. **Container won't start**:
   ```bash
   # Check environment variables
   docker-compose config
   ```

### **Debug Mode**

```bash
# Run with debug enabled
docker run -it \
  -e NOTEBOOKLM_DEBUG=true \
  -e NOTEBOOKLM_HEADLESS=false \
  notebooklm-mcp:latest \
  notebooklm-mcp server --debug
```

---

**📝 For more deployment options, see the [main README](../README.md)**
