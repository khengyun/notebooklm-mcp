#!/usr/bin/env python3
"""
Example: Basic NotebookLM automation
"""

import asyncio
from notebooklm_mcp import NotebookLMClient, ServerConfig

async def main():
    """Basic chat example with NotebookLM"""
    
    # Configure client
    config = ServerConfig(
        default_notebook_id="your-notebook-id",
        headless=True,  # Set to False to see browser
        debug=True
    )
    
    client = NotebookLMClient(config)
    
    try:
        print("🚀 Starting NotebookLM client...")
        await client.start()
        
        print("🔐 Authenticating...")
        auth_success = await client.authenticate()
        
        if not auth_success:
            print("⚠️  Authentication required - please login in browser")
            return
        
        print("✅ Authenticated successfully!")
        
        # Send a message
        message = "Can you provide a summary of the key insights from this document?"
        print(f"📤 Sending: {message}")
        
        await client.send_message(message)
        
        # Get streaming response
        print("⏳ Waiting for response...")
        response = await client.get_response(wait_for_completion=True)
        
        print(f"🤖 NotebookLM Response:\n{response}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        
    finally:
        await client.close()
        print("👋 Session closed")

if __name__ == "__main__":
    asyncio.run(main())