#!/usr/bin/env python3
"""
Simple test script to verify NotebookLM MCP server functionality
"""
import asyncio
import sys
import json
from notebooklm_mcp_server import amain

async def test_server():
    """Test basic server functionality"""
    print("🚀 Testing NotebookLM MCP Server...")
    
    # Test với config cơ bản
    test_args = [
        "--cookies", "cookies.json",
        "--notebook", "4741957b-f358-48fb-a16a-da8d20797bc6", 
        "--headless",
        "--debug"
    ]
    
    try:
        # Test server initialization
        result = await amain(test_args)
        if result == 0:
            print("✅ Server initialized successfully")
        else:
            print(f"❌ Server failed with code: {result}")
    except Exception as e:
        print(f"❌ Server error: {e}")
        
    return True

if __name__ == "__main__":
    asyncio.run(test_server())