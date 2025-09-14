#!/usr/bin/env python3
"""
Demo AutoGen MCP Client gọi đến running MCP Server
"""

import json
import subprocess
import sys
import time

def demo_mcp_client_calls():
    """Demo các JSON-RPC calls mà AutoGen sẽ gửi đến MCP server"""
    
    print("🤖 AutoGen MCP Client Demo")
    print("=" * 40)
    print("📡 Connecting to running MCP server...")
    print()
    
    # Các JSON-RPC requests mà AutoGen sẽ gửi
    requests = [
        {
            "name": "List Tools",
            "request": {
                "jsonrpc": "2.0",
                "id": 1, 
                "method": "tools/list",
                "params": {}
            }
        },
        {
            "name": "Healthcheck", 
            "request": {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "healthcheck",
                    "arguments": {}
                }
            }
        },
        {
            "name": "Chat with NotebookLM",
            "request": {
                "jsonrpc": "2.0", 
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "chat_with_notebook",
                    "arguments": {
                        "message": "What is Mixture of Experts?",
                        "max_wait": 30
                    }
                }
            }
        }
    ]
    
    for i, call in enumerate(requests, 1):
        print(f"📤 {i}. {call['name']}")
        print(f"   Request: {json.dumps(call['request'], indent=2)}")
        print()
        print("   💡 AutoGen sẽ gửi request này qua STDIO đến MCP server")
        print("   🎯 MCP server (Terminal 1) sẽ process và trả response")
        print("   📥 AutoGen nhận JSON response với kết quả")
        print()
        print("-" * 50)
        print()
    
    print("🚀 AutoGen Integration Ready!")
    print("📋 Steps to integrate:")
    print("1. Keep MCP server running (Terminal 1)")
    print("2. AutoGen McpWorkbench connects via STDIO")  
    print("3. AutoGen agents can call all 8 MCP tools")
    print("4. Real-time NotebookLM interaction!")

if __name__ == "__main__":
    demo_mcp_client_calls()