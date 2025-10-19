# Quick Fix Guide for Windows Chrome Connection Error

## 🚨 Error You're Seeing

```
Failed to initialize client: Message: session not created: cannot connect to chrome at 127.0.0.1:33086
from chrome not reachable
```

## ✅ Quick Solutions (Choose One)

### Solution 1: Disable Headless Mode (Easiest)

1. Open `notebooklm-config.json` in your editor
2. Change `"headless": true` to `"headless": false`
3. Save the file
4. Run your server command again

**What this does:** Browser will open minimized but visible. Still works great for automation!

### Solution 2: Let Automatic Fallback Work (New Feature)

With this update, the system automatically detects Windows and:
- Tries headless mode first
- If that fails, automatically switches to minimized mode
- No manual changes needed!

Just run your command again and it should work.

### Solution 3: Use WSL for Full Headless (Advanced)

For true headless mode on Windows:

1. Install WSL: `wsl --install`
2. Open WSL terminal
3. Install dependencies and run there

## 📋 Config File Example

Your `notebooklm-config.json` should look like:

```json
{
  "default_notebook_id": "your-notebook-id-here",
  "headless": false,  ← Change this from true to false
  "timeout": 60,
  "auth": {
    "profile_dir": "./chrome_profile_notebooklm",
    "use_persistent_session": true,
    "auto_login": true
  },
  "debug": false
}
```

## 🔍 Why This Happens

Windows has compatibility issues with Chrome's headless mode when using the anti-detection driver (`undetected-chromedriver`). This is a known limitation, not a bug in your setup.

## ✨ What's Fixed

- **Platform Detection**: Automatically detects Windows
- **Smart Fallback**: Tries headless, falls back to minimized if needed
- **Better Errors**: Clear messages explaining what to do
- **No Breaking Changes**: Existing setups still work

## 🆘 Still Having Issues?

1. **Delete the profile folder**:
   ```
   rmdir /s chrome_profile_notebooklm
   ```

2. **Re-run init**:
   ```
   notebooklm-mcp init https://notebooklm.google.com/notebook/YOUR_ID
   ```

3. **Check Chrome installation**: Make sure Chrome is installed and up to date

4. **Close Chrome instances**: Close all Chrome windows before starting the server

## 📖 More Details

See [WINDOWS_COMPATIBILITY.md](./WINDOWS_COMPATIBILITY.md) for technical details and advanced options.
