#!/usr/bin/env python3
"""
Alternative approach: Use undetected-chromedriver để bypass Google detection
"""

import asyncio
import subprocess
import sys
from pathlib import Path

def install_undetected_chrome():
    """Install undetected-chromedriver package"""
    try:
        import undetected_chromedriver
        print("✅ undetected-chromedriver already installed")
        return True
    except ImportError:
        print("📦 Installing undetected-chromedriver...")
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", "undetected-chromedriver"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ undetected-chromedriver installed successfully")
            return True
        else:
            print(f"❌ Installation failed: {result.stderr}")
            return False

async def test_undetected_browser():
    """Test NotebookLM access với undetected chrome"""
    if not install_undetected_chrome():
        return
    
    try:
        import undetected_chromedriver as uc
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        print("🚀 Starting undetected Chrome...")
        
        # Create undetected Chrome instance
        options = uc.ChromeOptions()
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-extensions")
        
        driver = uc.Chrome(options=options, version_main=None)
        
        try:
            print("🌐 Navigating to NotebookLM...")
            driver.get("https://notebooklm.google.com/notebook/4741957b-f358-48fb-a16a-da8d20797bc6")
            
            # Wait for page load
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            current_url = driver.current_url
            print(f"📍 Current URL: {current_url}")
            
            if "signin" in current_url or "accounts.google.com" in current_url:
                print("🔐 Login page detected - please login manually")
                print("   Browser will stay open for 60 seconds...")
                print("   Login and navigate to your notebook")
                
                # Wait for user to login
                await asyncio.sleep(60)
                
                # Check final status
                final_url = driver.current_url
                print(f"📍 Final URL: {final_url}")
                
                if "notebooklm.google.com" in final_url and "signin" not in final_url:
                    print("✅ Successfully accessed NotebookLM!")
                    
                    # Test basic interaction
                    print("🔍 Looking for chat interface...")
                    page_source = driver.page_source[:1000]
                    print(f"📄 Page preview: {page_source}")
                else:
                    print("❌ Still not authenticated")
            else:
                print("✅ Direct access successful!")
                
        finally:
            print("🔄 Closing browser...")
            driver.quit()
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_undetected_browser())