
# 🎯 Auto Release Workflow Summary

## How it works:
1. **Push to main** → Triggers test.yml if code changes
2. **Tests pass** → Triggers auto-release.yml 
3. **Auto release** → Bumps version and creates GitHub release
4. **Version bump commit** → Skipped by auto-release to prevent loops

## Triggers:
- ✅ Tests pass on main branch
- ✅ Manual workflow dispatch  
- ❌ Direct push (removed to focus on test-driven releases)
- ❌ Version bump commits (skipped automatically)

## Updated: Tue Sep 16 12:54:07 AM +07 2025

