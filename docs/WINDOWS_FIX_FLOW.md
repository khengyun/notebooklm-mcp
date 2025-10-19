# Windows Headless Mode Fix - Flow Diagram

## Before Fix

```
User runs: notebooklm-mcp server --headless
                    ↓
          Platform: Windows
                    ↓
     undetected-chromedriver tries headless mode
                    ↓
                  ❌ FAILS
                    ↓
     "cannot connect to chrome" error
                    ↓
              Server exits
```

## After Fix (Automatic Fallback)

```
User runs: notebooklm-mcp server --headless
                    ↓
          Platform: Windows
                    ↓
     ┌─────────────────────────────┐
     │ Detect OS: Windows          │
     └─────────────┬───────────────┘
                   ↓
     ┌─────────────────────────────┐
     │ Try headless with extra     │
     │ stability flags:            │
     │ - --disable-gpu             │
     │ - --disable-dev-shm-usage   │
     │ - --no-sandbox              │
     └─────────────┬───────────────┘
                   ↓
          Does it work?
           ↙         ↘
        YES           NO
         ↓             ↓
    ✅ Success    Automatic Fallback
         ↓             ↓
    Run server   ┌─────────────────┐
                 │ Remove headless │
                 │ Use minimized   │
                 │ window instead  │
                 └────────┬────────┘
                          ↓
                    ✅ Success
                          ↓
                    Run server
```

## Manual Fix Option

```
User edits: notebooklm-config.json
                    ↓
     "headless": true → "headless": false
                    ↓
User runs: notebooklm-mcp server
                    ↓
          Platform: Windows
                    ↓
     Browser starts in minimized mode
                    ↓
                ✅ Success
                    ↓
               Run server
```

## Platform Behavior Matrix

| Platform | Headless Mode | Result | Fallback |
|----------|--------------|--------|----------|
| **Linux** | ✅ Enabled | ✅ Works | N/A |
| **Mac** | ✅ Enabled | ✅ Works | N/A |
| **Windows** | ✅ Enabled | ⚠️ May fail | ✅ Auto-fallback to minimized |
| **Windows** | ❌ Disabled | ✅ Works (minimized) | N/A |
| **WSL** | ✅ Enabled | ✅ Works | N/A |

## Error Handling Flow

```
Server Start
     ↓
Initialize Chrome
     ↓
Connection Error?
     ↓
    YES → Is Windows + Headless?
          ↓
         YES → Show Windows-specific help message
               - Option 1: Set headless=false
               - Option 2: Use WSL
               - Option 3: Auto-fallback works
          ↓
         NO → Show general troubleshooting
              - Check Chrome installation
              - Delete profile folder
              - Re-run init
```

## User Experience Comparison

### Before Fix
1. Run `init` ✅ Works
2. Config updated to headless=true
3. Run `server` ❌ Fails with cryptic error
4. User confused, posts GitHub issue

### After Fix
1. Run `init` ✅ Works
2. Config updated to headless=true (with note)
3. Run `server` ✅ Auto-fallback or clear instructions
4. User happy, server running

## Code Changes Summary

### client.py
- Added `platform.system()` detection
- Windows gets special Chrome arguments
- Try/except with automatic fallback
- Better logging for each step

### cli.py
- Windows warning during `init`
- Enhanced error messages with platform detection
- Clear troubleshooting steps for Windows users
- Links to documentation

### tests/test_windows_compatibility.py
- 5 new tests for Windows behavior
- Platform detection tests
- Config update tests
- All 133 tests pass
