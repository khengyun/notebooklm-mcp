# 🐳 Docker Deployment Guide# 🐳 Docker Deployment Guide



This guide covers deploying NotebookLM MCP Server using Docker with UV Python manager.This guide covers deploying NotebookLM MCP Server using Docker and Docker Compose.



## 📋 Prerequisites## 🚀 Quick Start



1. **Docker & Docker Compose** installed### **Environment Setup**

2. **notebooklm-config.json** file configured  

3. **NotebookLM URL** with your notebook IDCreate a `.env` file:



## 🚀 Quick Start```bash

# Required: Your NotebookLM notebook ID

### 1. Create ConfigurationNOTEBOOKLM_NOTEBOOK_ID=your-notebook-id-here



```bash# Optional: Additional settings

# Copy example configNOTEBOOKLM_DEBUG=false

cp notebooklm-config.example.json notebooklm-config.jsonNOTEBOOKLM_TIMEOUT=60

```

# Edit with your notebook ID

nano notebooklm-config.json### **Basic Docker Run**

```

```bash

Update `default_notebook_id`:# Build image

```jsondocker build -t notebooklm-mcp .

{

  "default_notebook_id": "your-actual-notebook-id",# Run container

  "headless": true,docker run -d \

  "profile_dir": "/app/chrome_profile",  --name notebooklm-mcp \

  "timeout": 60  -e NOTEBOOKLM_NOTEBOOK_ID="your-notebook-id" \

}  -v notebooklm_profile:/app/chrome_profile \

```  notebooklm-mcp:latest

```

### 2. Run with Docker Compose

### **Docker Compose (Recommended)**

```bash

# Start STDIO mode (for MCP clients)```bash

docker-compose up -d# Start services

docker-compose up -d

# Check logs

docker-compose logs -f notebooklm-mcp# View logs

docker-compose logs -f notebooklm-mcp

# Stop services

docker-compose down# Stop services

```docker-compose down

```

### 3. Different Transport Modes

## 📊 **Monitoring Setup**

**STDIO Mode (Default)**:

```bashEnable monitoring stack with Prometheus and Grafana:

# No ports exposed - for MCP protocol

docker-compose up -d```bash

```# Start with monitoring

docker-compose --profile monitoring up -d

**HTTP Mode**:

```bash# Access Grafana: http://localhost:3000

# Edit docker-compose.yml to uncomment:# Username: admin, Password: admin

ports:```

  - "8001:8001"

## 🔧 **Configuration**

# Restart services

docker-compose up -d### **Environment Variables**

```

| Variable | Default | Description |

**SSE Mode**:|----------|---------|-------------|

```bash| `NOTEBOOKLM_NOTEBOOK_ID` | None | Target notebook ID (required) |

# Edit docker-compose.yml ports:| `NOTEBOOKLM_HEADLESS` | true | Run browser in headless mode |

ports:| `NOTEBOOKLM_DEBUG` | false | Enable debug logging |

  - "8002:8002"| `NOTEBOOKLM_TIMEOUT` | 60 | Browser timeout in seconds |

| `NOTEBOOKLM_PROFILE_DIR` | /app/chrome_profile | Chrome profile directory |

# Restart services

docker-compose up -d### **Volume Mounts**

```

- `chrome_profile:/app/chrome_profile` - Persistent browser session

## 🔧 Configuration- `./config.json:/app/config.json:ro` - Configuration file (optional)

- `./scripts:/app/scripts:ro` - Custom scripts (optional)

### Volume Mounts (REQUIRED)

## 🏭 **Production Deployment**

| Volume | Purpose | Mount Point |

|--------|---------|-------------|### **Kubernetes**

| `notebooklm-config.json` | **Configuration file** | `/app/notebooklm-config.json` |

| `chrome_profile` | Session persistence | `/app/chrome_profile` |```yaml

apiVersion: apps/v1

### Environment Variableskind: Deployment

metadata:

```yaml  name: notebooklm-mcp

environment:  labels:

  - UV_PYTHON=python3.10    app: notebooklm-mcp

  - NOTEBOOKLM_CONFIG_FILE=/app/notebooklm-config.jsonspec:

```  replicas: 1

  selector:

## 🛠️ Development    matchLabels:

      app: notebooklm-mcp

### Build Custom Image  template:

    metadata:

```bash      labels:

# Build with UV        app: notebooklm-mcp

docker build -t notebooklm-mcp:dev .    spec:

      containers:

# Test locally      - name: notebooklm-mcp

docker run --rm \        image: notebooklm-mcp:latest

  -v $(pwd)/notebooklm-config.json:/app/notebooklm-config.json \        env:

  notebooklm-mcp:dev        - name: NOTEBOOKLM_HEADLESS

```          value: "true"

        - name: NOTEBOOKLM_NOTEBOOK_ID

### Debug Container          valueFrom:

            secretKeyRef:

```bash              name: notebooklm-config

# Interactive shell              key: notebook-id

docker-compose run --rm notebooklm-mcp bash        volumeMounts:

        - name: chrome-profile

# Check UV          mountPath: /app/chrome_profile

docker-compose exec notebooklm-mcp uv --version        resources:

          limits:

# Test config            cpu: 2000m

docker-compose exec notebooklm-mcp uv run python -c "            memory: 2Gi

from notebooklm_mcp.config import ServerConfig          requests:

print(ServerConfig.from_file('/app/notebooklm-config.json'))            cpu: 500m

"            memory: 512Mi

```        livenessProbe:

          exec:

## 🔍 Troubleshooting            command:

            - python

### Common Issues            - -c

            - "from notebooklm_mcp.config import ServerConfig; ServerConfig().validate()"

**1. Config file not found:**          initialDelaySeconds: 30

```bash          periodSeconds: 30

# Check mount        readinessProbe:

docker-compose exec notebooklm-mcp ls -la /app/notebooklm-config.json          exec:

            command:

# Verify content              - python

docker-compose exec notebooklm-mcp cat /app/notebooklm-config.json            - -c

```            - "from notebooklm_mcp.config import ServerConfig; ServerConfig().validate()"

          initialDelaySeconds: 5

**2. Chrome issues:**          periodSeconds: 10

```bash      volumes:

# Check Chrome      - name: chrome-profile

docker-compose exec notebooklm-mcp google-chrome --version        persistentVolumeClaim:

          claimName: chrome-profile-pvc

# Test ChromeDriver---

docker-compose exec notebooklm-mcp chromedriver --versionapiVersion: v1

```kind: PersistentVolumeClaim

metadata:

**3. Permission issues:**  name: chrome-profile-pvc

```bashspec:

# Check profile directory  accessModes:

docker-compose exec notebooklm-mcp ls -la /app/chrome_profile/    - ReadWriteOnce

```  resources:

    requests:

### Health Checks      storage: 1Gi

```

```bash

# Check status### **Docker Swarm**

docker-compose ps

```yaml

# Manual health checkversion: '3.8'

docker-compose exec notebooklm-mcp uv run python -c "

from notebooklm_mcp.config import ServerConfigservices:

ServerConfig.from_file('/app/notebooklm-config.json').validate()  notebooklm-mcp:

print('✅ Config valid')    image: notebooklm-mcp:latest

"    deploy:

```      replicas: 1

      restart_policy:

## 📈 Performance Benefits        condition: on-failure

        delay: 5s

### UV vs pip in Docker        max_attempts: 3

      resources:

| Metric | pip | UV | Improvement |        limits:

|--------|-----|----|-----------|           cpus: '2.0'

| **Build time** | 3-5 min | 1-2 min | **2-3x faster** |          memory: 2G

| **Install time** | 45-90s | 5-15s | **5-10x faster** |        reservations:

| **Startup time** | 15-30s | 5-10s | **2-3x faster** |          cpus: '0.5'

          memory: 512M

### Caching Strategy    environment:

      - NOTEBOOKLM_HEADLESS=true

```dockerfile      - NOTEBOOKLM_NOTEBOOK_ID=${NOTEBOOKLM_NOTEBOOK_ID}

# UV lockfile for better caching    volumes:

COPY pyproject.toml uv.lock ./      - chrome_profile:/app/chrome_profile

RUN uv sync --all-groups    networks:

      - notebooklm-network

# Source code after dependencies

COPY src/ ./src/volumes:

```  chrome_profile:

    driver: local

## 🚀 Production Ready

networks:

### Resource Limits  notebooklm-network:

    driver: overlay

```yaml```

deploy:

  resources:## 🛠️ **Development**

    limits:

      cpus: '2.0'### **Development Docker Compose**

      memory: 2G

    reservations:```yaml

      cpus: '0.5'version: '3.8'

      memory: 512M

```services:

  notebooklm-mcp-dev:

### Security    build:

      context: .

```yaml      dockerfile: Dockerfile.dev  # Development dockerfile

security_opt:    volumes:

  - no-new-privileges:true      - .:/app

      - chrome_profile:/app/chrome_profile

# Non-root user    environment:

USER notebooklm      - NOTEBOOKLM_HEADLESS=false  # Show browser for debugging

```      - NOTEBOOKLM_DEBUG=true

      - NOTEBOOKLM_NOTEBOOK_ID=${NOTEBOOKLM_NOTEBOOK_ID}

### Monitoring    ports:

      - "8000:8000"  # For debugging

```bash    command: ["notebooklm-mcp", "server", "--debug"]

# Enable monitoring stack

docker-compose --profile monitoring up -dvolumes:

  chrome_profile:

# Access Grafana: http://localhost:3000```

# Default: admin/admin

```### **Multi-stage Build**



---```dockerfile

# Development stage

**🐳 Ready for production deployment with UV-powered Docker containers!**FROM python:3.11-slim as development
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
