import asyncio

from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams


async def main():
    """Test AutoGen integration with NotebookLM MCP Server"""

    print("🔍 Checking if config exists...")
    import os

    print("🔍 Checking if config exists...")
    if not os.path.exists("notebooklm-config.json"):
        print("❌ Config file not found!")
        print(
            "💡 Please run: notebooklm-mcp init https://notebooklm.google.com/notebook/YOUR_NOTEBOOK_ID"
        )
        return
    
    # Test authentication status first
    print("🔐 Testing authentication status...")
    test_workbench = None
    try:
        # Quick test with headless mode
        test_params = StdioServerParams(
            command="notebooklm-mcp", 
            args=["--config", "notebooklm-config.json", "server", "--headless"]
        )
        test_workbench = McpWorkbench(test_params)
        
        await test_workbench.start()
        await asyncio.sleep(3)  # Short wait
        
        # Try health check
        health_result = await test_workbench.call_tool("healthcheck", {})
        print("✅ Authentication valid - proceeding with headless mode")
        await test_workbench.close()
        
        
    except Exception as e:
        print(f"⚠️  Authentication needed: {e}")
        print("🔧 Running in GUI mode for manual authentication...")
        print("   Please complete login in the browser window")
        
        # Use GUI mode
        params = StdioServerParams(
            command="notebooklm-mcp", 
            args=["--config", "notebooklm-config.json", "server"]
        )
        
        # Close test workbench if it exists
        if test_workbench:
            try:
                await test_workbench.close()
            except Exception:
                pass

    # Configure MCP server with determined params

    # Create MCP workbench
    workbench = McpWorkbench(params)

    try:
        # Initialize the workbench
        print("🚀 Starting NotebookLM MCP Server...")
        await workbench.start()

        # Give server time to initialize
        print("⏳ Waiting for server initialization...")
        await asyncio.sleep(5)

        # Test health check first
        print("🏥 Testing health check...")
        try:
            health_result = await workbench.call_tool("healthcheck", {})
            print(f"✅ Health Status: {health_result}")
        except Exception as e:
            print(f"⚠️  Health check failed: {e}")
            print("This might be due to authentication issues in headless mode")

        # Test quick response (doesn't require new messages)
        print("⚡ Testing quick response...")
        try:
            quick_result = await workbench.call_tool("get_quick_response", {})
            print(f"📝 Quick Response: {quick_result}")
        except Exception as e:
            print(f"⚠️  Quick response failed: {e}")

        # Test chat functionality (might fail if not authenticated)
        print("💬 Testing chat with notebook...")
        try:
            chat_result = await workbench.call_tool(
                "chat_with_notebook",
                {"message": "Hello from AutoGen test!", "max_wait": 30},
            )
            print(f"� Response: {chat_result}")
        except Exception as e:
            print(f"⚠️  Chat failed: {e}")
            print("💡 This is expected if authentication is required")

        print("✅ AutoGen integration test completed!")
        print("📝 Note: Some tests may fail if manual authentication is needed")

    except Exception as e:
        print(f"❌ Error during test: {e}")
        print("")
        print("� Troubleshooting steps:")
        print("1. Ensure config exists: notebooklm-mcp init YOUR_NOTEBOOK_URL")
        print(
            "2. Test manual login: notebooklm-mcp --config notebooklm-config.json chat --message 'test'"
        )
        print("3. Check if profile has valid authentication")

    finally:
        # Clean up
        try:
            await workbench.stop()
            print("🛑 MCP workbench stopped")
        except:
            pass


if __name__ == "__main__":
    print("🤖 NotebookLM MCP Server - AutoGen Integration Test")
    print("=" * 50)
    asyncio.run(main())
