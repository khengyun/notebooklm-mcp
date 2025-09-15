#!/usr/bin/env python3
"""
Proper FastMCP v2 HTTP client using fastmcp.Client
"""

import asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

async def test_proper_fastmcp_client():
    """Test FastMCP v2 server using proper FastMCP Client"""
    
    print("🌐 Testing FastMCP v2 with Proper Client")
    print("=" * 60)
    print("Server should be running on: http://127.0.0.1:8001/mcp")
    print()
    
    try:
        # Create proper FastMCP client with HTTP transport
        transport = StreamableHttpTransport(
            url="http://127.0.0.1:8001/mcp",
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json"
            }
        )
        
        async with Client(transport) as client:
            print("✅ Connected to FastMCP v2 server!")
            
            # Test 1: List available tools
            print("\n1️⃣ Listing available tools...")
            tools = await client.list_tools()
            print(f"   Found {len(tools)} tools:")
            for tool in tools[:5]:  # Show first 5
                print(f"     • {tool.name}: {tool.description or 'No description'}")
            
            # Test 2: Call healthcheck tool
            print("\n2️⃣ Testing healthcheck tool...")
            try:
                health_result = await client.call_tool("healthcheck", {})
                print(f"   ✅ Healthcheck result: {health_result}")
            except Exception as e:
                print(f"   ❌ Healthcheck failed: {e}")
            
            # Test 3: Test complete chat interaction
            print("\n3️⃣ Testing complete chat with NotebookLM...")
            try:
                # Use chat_with_notebook for complete interaction
                chat_result = await client.call_tool("chat_with_notebook", {
                    "request": {
                        "message": "Hello! Can you help me understand what documents are in this notebook?"
                    }
                })
                print(f"   ✅ Chat completed!")
                print(f"   📤 Sent: Hello! Can you help me understand what documents are in this notebook?")
                
                # Extract response from result
                if hasattr(chat_result, 'data') and 'response' in chat_result.data:
                    response_text = chat_result.data['response']
                    print(f"   📥 NotebookLM Response: {response_text[:200]}..." if len(response_text) > 200 else f"   📥 NotebookLM Response: {response_text}")
                else:
                    print(f"   📄 Raw result: {chat_result}")
                    
            except Exception as e:
                print(f"   ❌ Chat failed: {e}")
                
            # Test 4: Test send + get response separately
            print("\n4️⃣ Testing send message + get response separately...")
            try:
                # Send message first
                send_result = await client.call_tool("send_chat_message", {
                    "request": {
                        "message": "What is the main topic of the documents in this notebook?",
                        "wait_for_response": False
                    }
                })
                print(f"   ✅ Message sent: {send_result.data.get('status', 'unknown')}")
                
                # Wait a moment for processing
                import time
                await asyncio.sleep(2)
                
                # Get response
                response_result = await client.call_tool("get_chat_response", {
                    "request": {
                        "timeout": 30
                    }
                })
                print(f"   ✅ Response received!")
                if hasattr(response_result, 'data') and 'response' in response_result.data:
                    response_text = response_result.data['response']
                    print(f"   📥 NotebookLM Response: {response_text[:200]}..." if len(response_text) > 200 else f"   📥 NotebookLM Response: {response_text}")
                else:
                    print(f"   📄 Raw result: {response_result}")
                    
            except Exception as e:
                print(f"   ❌ Send+Get failed: {e}")
            
            # Test 5: Test get_default_notebook
            print("\n5️⃣ Testing get_default_notebook tool...")
            try:
                notebook_result = await client.call_tool("get_default_notebook", {})
                print(f"   ✅ Default notebook: {notebook_result.data}")
            except Exception as e:
                print(f"   ❌ Get notebook failed: {e}")
                
    except Exception as e:
        print(f"❌ Failed to connect to FastMCP server: {e}")
        print("\nMake sure server is running with:")
        print("notebooklm-mcp --config notebooklm-config.json server --fastmcp --transport http --port 8001 --headless")

def main():
    """Main test function"""
    try:
        asyncio.run(test_proper_fastmcp_client())
        print("\n🎉 Test completed successfully!")
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")

if __name__ == "__main__":
    main()