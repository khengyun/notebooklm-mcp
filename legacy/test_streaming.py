#!/usr/bin/env python3
"""
Enhanced integration test for NotebookLM MCP server với streaming support
"""

import os
import json
import asyncio
import subprocess
import sys
from typing import Any, Dict

async def test_mcp_tools_streaming():
    """Test MCP server tools via JSON-RPC với streaming support"""
    
    # Start MCP server as subprocess
    notebook_id = os.getenv("NOTEBOOK_ID", "4741957b-f358-48fb-a16a-da8d20797bc6")
    
    cmd = [
        sys.executable,
        "notebooklm_mcp_server.py",
        "--notebook", notebook_id,
        "--headless",  # Run headless for CI
        "--debug"
    ]
    
    print(f"🚀 Starting MCP server: {' '.join(cmd)}")
    
    # Start server process
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=os.path.dirname(__file__)
    )
    
    try:
        # Test 1: List tools
        print("📋 Test 1: List tools")
        list_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }
        
        proc.stdin.write(json.dumps(list_request) + "\n")
        proc.stdin.flush()
        
        response_line = proc.stdout.readline()
        if response_line:
            response = json.loads(response_line)
            if "result" in response:
                tools = response["result"]["tools"]
                print(f"✅ Found {len(tools)} tools:")
                for tool in tools:
                    print(f"   - {tool['name']}: {tool['description']}")
            else:
                print(f"❌ Error: {response}")
        
        # Test 2: Chat with streaming
        print("\n💬 Test 2: Chat with streaming response")
        chat_request = {
            "jsonrpc": "2.0", 
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "chat_with_notebook",
                "arguments": {
                    "message": "Hello! Can you give me a brief summary?",
                    "max_wait": 30
                }
            }
        }
        
        proc.stdin.write(json.dumps(chat_request) + "\n")
        proc.stdin.flush()
        
        # Wait for response (may take time due to streaming)
        print("⏳ Waiting for streaming response...")
        response_line = proc.stdout.readline()
        if response_line:
            response = json.loads(response_line)
            if "result" in response:
                result = response["result"]["content"][0]["text"]
                print(f"✅ Chat response: {result[:200]}...")
            else:
                print(f"❌ Chat error: {response}")
        
        # Test 3: Quick response check
        print("\n⚡ Test 3: Quick response check")
        quick_request = {
            "jsonrpc": "2.0",
            "id": 3, 
            "method": "tools/call",
            "params": {
                "name": "get_quick_response",
                "arguments": {}
            }
        }
        
        proc.stdin.write(json.dumps(quick_request) + "\n")
        proc.stdin.flush()
        
        response_line = proc.stdout.readline()
        if response_line:
            response = json.loads(response_line)
            if "result" in response:
                result = response["result"]["content"][0]["text"]
                print(f"✅ Quick response: {result[:100]}...")
            else:
                print(f"❌ Quick response error: {response}")
        
        print("\n🎉 Enhanced integration test completed!")
        
    except Exception as e:
        print(f"❌ Test error: {e}")
        
    finally:
        # Cleanup
        try:
            # Send shutdown command
            shutdown_request = {
                "jsonrpc": "2.0",
                "id": 99,
                "method": "tools/call", 
                "params": {
                    "name": "shutdown",
                    "arguments": {}
                }
            }
            proc.stdin.write(json.dumps(shutdown_request) + "\n")
            proc.stdin.flush()
            
            # Wait briefly then terminate
            proc.wait(timeout=5)
        except:
            proc.terminate()
            proc.wait()

if __name__ == "__main__":
    # Skip if no display (CI environment)
    if not os.getenv("DISPLAY") and not os.getenv("GITHUB_ACTIONS"):
        print("⚠️  Skipping enhanced integration test - no display available")
        print("   Set DISPLAY environment variable or run in headed mode")
        sys.exit(0)
    
    asyncio.run(test_mcp_tools_streaming())