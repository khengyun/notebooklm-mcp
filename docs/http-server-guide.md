# 🌐 HTTP Server & Web Testing Guide

## Overview

FastMCP v2 NotebookLM server có thể chạy với **HTTP transport** thay vì STDIO, cho phép:

- 🌐 **Web-based testing** của MCP tools
- 🔗 **Multiple client connections** 
- 📊 **HTTP API access** để integrate với web apps
- 🧪 **Easy debugging** qua browser/Postman

## 🚀 Cách chạy HTTP Server

### 1. STDIO Mode (Default)
```bash
# Traditional STDIO transport
notebooklm-mcp --config notebooklm-config.json server --fastmcp
```

### 2. HTTP Mode 
```bash
# HTTP transport on port 8001
notebooklm-mcp --config notebooklm-config.json server --fastmcp --transport http --port 8001 --headless
```

### 3. SSE Mode
```bash
# Server-Sent Events transport
notebooklm-mcp --config notebooklm-config.json server --fastmcp --transport sse --port 8002 --headless
```

## 🔗 Endpoints & Access

### HTTP Server URLs

| Transport | URL | Description |
|-----------|-----|-------------|
| **HTTP** | `http://localhost:8001/mcp` | MCP protocol endpoint |
| **SSE** | `http://localhost:8002/` | Server-Sent Events |
| **Custom** | `http://localhost:PORT/health` | Health check (if implemented) |

### MCP Protocol via HTTP

**URL**: `http://localhost:8001/mcp`  
**Method**: `POST`  
**Headers**: `Content-Type: application/json`

## 📋 Available MCP Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `healthcheck` | Server health status | None |
| `send_chat_message` | Send message to NotebookLM | `message: str`, `wait_for_response: bool` |
| `get_chat_response` | Get streaming response | `timeout: int` |
| `chat_with_notebook` | Complete chat interaction | `message: str`, `notebook_id?: str` |
| `navigate_to_notebook` | Switch notebooks | `notebook_id: str` |
| `get_default_notebook` | Get current notebook | None |
| `set_default_notebook` | Set default notebook | `notebook_id: str` |
| `get_quick_response` | Get current response | None |

## 🧪 Testing với HTTP Clients

### 1. List Available Tools

```bash
curl -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0", 
    "id": 1, 
    "method": "tools/list",
    "params": {}
  }'
```

### 2. Call Healthcheck Tool

```bash
curl -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0", 
    "id": 2, 
    "method": "tools/call",
    "params": {
      "name": "healthcheck",
      "arguments": {}
    }
  }'
```

### 3. Send Chat Message

```bash
curl -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0", 
    "id": 3, 
    "method": "tools/call",
    "params": {
      "name": "send_chat_message",
      "arguments": {
        "message": "Hello from HTTP client!",
        "wait_for_response": false
      }
    }
  }'
```

## 🐍 Python Client Example

```python
import httpx
import asyncio

async def test_mcp_http():
    async with httpx.AsyncClient() as client:
        # List tools
        response = await client.post(
            "http://localhost:8001/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {}
            }
        )
        tools = response.json()
        print(f"Available tools: {len(tools['result']['tools'])}")
        
        # Call healthcheck
        response = await client.post(
            "http://localhost:8001/mcp",
            json={
                "jsonrpc": "2.0", 
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "healthcheck",
                    "arguments": {}
                }
            }
        )
        health = response.json()
        print(f"Health status: {health['result']}")

# Run test
asyncio.run(test_mcp_http())
```

## 🌐 Web Interface Testing

### Simple HTML Test Page

```html
<!DOCTYPE html>
<html>
<head>
    <title>MCP Tool Tester</title>
</head>
<body>
    <h1>NotebookLM MCP Tools</h1>
    <button onclick="testHealthcheck()">Test Healthcheck</button>
    <div id="result"></div>
    
    <script>
        async function testHealthcheck() {
            try {
                const response = await fetch('http://localhost:8001/mcp', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        jsonrpc: "2.0",
                        id: 1,
                        method: "tools/call",
                        params: {
                            name: "healthcheck",
                            arguments: {}
                        }
                    })
                });
                
                const result = await response.json();
                document.getElementById('result').innerHTML = 
                    '<pre>' + JSON.stringify(result, null, 2) + '</pre>';
            } catch (error) {
                document.getElementById('result').innerHTML = 
                    '<p style="color: red;">Error: ' + error.message + '</p>';
            }
        }
    </script>
</body>
</html>
```

## 🔧 Client Integration Examples

### LangGraph HTTP Client

```python
from langchain_mcp_adapters.client import HttpMCPClient

client = HttpMCPClient(
    url="http://localhost:8001/mcp",
    transport="http"
)

tools = await client.get_tools()
model_with_tools = model.bind_tools(tools)
```

### CrewAI HTTP Integration

```python
from crewai_tools import BaseTool
import httpx

class NotebookLMHttpTool(BaseTool):
    name = "notebooklm_http"
    description = "Chat with NotebookLM via HTTP"
    
    async def _arun(self, message: str):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8001/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call", 
                    "params": {
                        "name": "chat_with_notebook",
                        "arguments": {"message": message}
                    }
                }
            )
            result = response.json()
            return result["result"]["response"]
```

## 📊 Monitoring & Debugging

### Server Logs
```bash
# Start with debug logging
notebooklm-mcp --config notebooklm-config.json server --fastmcp --transport http --debug
```

### Health Check Endpoint
```bash
# Quick health check
curl http://localhost:8001/health
```

### Tool Discovery
```bash
# List all available tools
curl -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'
```

## 🎯 Use Cases

1. **🧪 Development & Testing**: Easy tool testing via browser/Postman
2. **🌐 Web Integration**: Embed NotebookLM in web applications  
3. **📱 Mobile Apps**: HTTP API for mobile client integration
4. **🤖 Multi-Client**: Multiple AI agents connecting simultaneously
5. **📊 Monitoring**: Health checks and status monitoring
6. **🔄 Load Balancing**: Scale across multiple server instances

## 🚨 Production Considerations

- **🔒 Authentication**: Add proper auth for production use
- **🛡️ CORS**: Configure CORS for web client access
- **📈 Scaling**: Use load balancer for multiple instances
- **📊 Monitoring**: Set up health checks and metrics
- **🔐 HTTPS**: Use TLS certificates for secure connections

## 🎉 Summary

HTTP transport enables:
- ✅ **Easy testing** với web tools
- ✅ **Multiple clients** connecting simultaneously  
- ✅ **Web integration** for browser-based apps
- ✅ **API access** for any HTTP client
- ✅ **Better debugging** và monitoring capabilities

Perfect for development, testing, và production web deployments! 🚀