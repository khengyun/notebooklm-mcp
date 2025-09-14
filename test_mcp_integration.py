#!/usr/bin/env python3
"""
Test MCP Server functionality with NotebookLM
Demo cho AutoGen integration
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

async def test_mcp_server():
    """Test MCP server với JSON-RPC calls"""
    
    print("🚀 Testing NotebookLM MCP Server for AutoGen Integration")
    print("=" * 60)
    
    # Start MCP server process
    notebook_id = "4741957b-f358-48fb-a16a-da8d20797bc6"
    
    cmd = [
        sys.executable, "-m", "notebooklm_mcp.cli", 
        "server", 
        "--notebook", notebook_id,
        "--headless"
    ]
    
    print(f"📋 Starting server: {' '.join(cmd)}")
    
    # Create process with STDIO for MCP communication
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    try:
        # Wait for server to start
        print("⏳ Waiting for server to initialize...")
        await asyncio.sleep(8)
        
        # Test 1: List available tools
        print("\n🔧 Test 1: List MCP Tools")
        tools_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {}
        }
        
        request_json = json.dumps(tools_request) + "\n"
        print(f"📤 Sending: {tools_request}")
        
        process.stdin.write(request_json.encode())
        await process.stdin.drain()
        
        # Read response
        try:
            response_line = await asyncio.wait_for(
                process.stdout.readline(), 
                timeout=5.0
            )
            response = json.loads(response_line.decode().strip())
            print(f"📥 Response: {json.dumps(response, indent=2)}")
            
            # Show available tools
            if "result" in response and "tools" in response["result"]:
                tools = response["result"]["tools"]
                print(f"\n✅ Found {len(tools)} MCP tools:")
                for tool in tools:
                    print(f"  - {tool['name']}: {tool['description']}")
            
        except asyncio.TimeoutError:
            print("⚠️ Response timeout - server might still be starting")
            
        # Test 2: Healthcheck
        print("\n💓 Test 2: Healthcheck")
        health_request = {
            "jsonrpc": "2.0", 
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "healthcheck",
                "arguments": {}
            }
        }
        
        request_json = json.dumps(health_request) + "\n"
        print(f"📤 Sending: {health_request}")
        
        process.stdin.write(request_json.encode())
        await process.stdin.drain()
        
        try:
            response_line = await asyncio.wait_for(
                process.stdout.readline(),
                timeout=5.0
            )
            response = json.loads(response_line.decode().strip())
            print(f"📥 Health Response: {json.dumps(response, indent=2)}")
            
        except asyncio.TimeoutError:
            print("⚠️ Health check timeout")
            
        # Test 3: Send message to NotebookLM
        print("\n💬 Test 3: Send Message to NotebookLM")
        message_request = {
            "jsonrpc": "2.0",
            "id": 3, 
            "method": "tools/call",
            "params": {
                "name": "chat_with_notebook",
                "arguments": {
                    "message": "What is MoE architecture?",
                    "max_wait": 30
                }
            }
        }
        
        request_json = json.dumps(message_request) + "\n"
        print(f"📤 Sending: {message_request}")
        
        process.stdin.write(request_json.encode())
        await process.stdin.drain()
        
        try:
            response_line = await asyncio.wait_for(
                process.stdout.readline(),
                timeout=35.0
            )
            response = json.loads(response_line.decode().strip())
            print(f"📥 Chat Response: {json.dumps(response, indent=2)}")
            
        except asyncio.TimeoutError:
            print("⚠️ Chat response timeout")
            
        print("\n✅ MCP Server testing completed!")
        print("🎯 Ready for AutoGen McpWorkbench integration!")
        
    finally:
        # Cleanup
        print("\n🔄 Shutting down server...")
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()


if __name__ == "__main__":
    asyncio.run(test_mcp_server())