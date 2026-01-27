# Slack OAuth Fix Applied

## What Was Wrong

Your frontend was hardcoded to show a manual token entry form for Slack instead of using the proper OAuth flow.

## Changes Made

### 1. `frontend/components/integrations/Integrations.tsx`

**Line 1592** - Enabled OAuth for Slack:
```diff
- isOAuth: false  // Changed to false - use token input instead
+ isOAuth: true   // Use OAuth flow like Gmail and Box
```

**Lines 2343-2368** - Removed special case for Slack:
```diff
- // Handle Slack specially - use token modal
- if (id === 'slack') {
-   if (integration?.connected) {
-     await disconnectIntegration(id)
-   } else {
-     setShowSlackTokenModal(true)
-   }
-   return
- }
-
- // Handle OAuth integrations (Gmail, etc.)
+ // Handle OAuth integrations (Slack, Gmail, Box, etc.)
  if (integration?.isOAuth) {
    ...
  }
```

**Line 7** - Use environment variable for API URL:
```diff
- const API_BASE = 'http://localhost:5003/api'
+ const API_BASE = process.env.NEXT_PUBLIC_API_URL
+   ? `${process.env.NEXT_PUBLIC_API_URL}/api`
+   : 'http://localhost:5003/api'
```

## What Happens Now

When users click "Connect" on the Slack card:

1. ✅ They'll be redirected to Slack's authorization page
2. ✅ They click "Allow" to grant permissions
3. ✅ Slack redirects back to your website
4. ✅ Connection complete - no manual token entry needed!

## Next Steps

### 1. Commit and Push Changes
```bash
cd /Users/pranavreddymogathala/use2ndbrain
git add frontend/components/integrations/Integrations.tsx
git commit -m "Fix Slack integration to use OAuth flow instead of manual token entry"
git push origin main
```

### 2. Redeploy Frontend on Render

Render should auto-deploy when you push to GitHub. If not:
1. Go to https://dashboard.render.com
2. Click on `secondbrain-frontend`
3. Click "Manual Deploy" → "Deploy latest commit"

### 3. Verify Environment Variable

Make sure your frontend has the API URL set:
1. Render Dashboard → `secondbrain-frontend` → Environment
2. Check: `NEXT_PUBLIC_API_URL = https://secondbrain-backend2.onrender.com`
3. **NO** `/api` suffix - the code adds it automatically

### 4. Test the OAuth Flow

1. Open your frontend: `https://your-frontend.onrender.com`
2. Go to Integrations page
3. Click "Connect" on Slack
4. You should see Slack's authorization screen (NOT the manual token form)
5. Click "Allow"
6. You'll be redirected back with connection success

## Troubleshooting

### Still showing manual token form?

**Cause:** Browser cache showing old code

**Fix:**
1. Hard refresh: `Cmd+Shift+R` (Mac) or `Ctrl+Shift+R` (Windows)
2. Or open in incognito/private window

### "Invalid redirect_uri" error

**Check:**
1. Render env var: `SLACK_REDIRECT_URI=https://secondbrain-backend2.onrender.com/api/integrations/slack/callback`
2. Slack app setting matches EXACTLY (including https://)

### OAuth redirect works but connection fails

**Check backend logs:**
```bash
# In Render Dashboard
secondbrain-backend2 → Logs → Live logs

# Look for:
[Slack Callback] Token response: ok=true/false
```

### Frontend can't reach backend

**Check:**
```bash
# Test API directly
curl https://secondbrain-backend2.onrender.com/api/health

# Should return:
{"status": "healthy", ...}
```

**If fails, check:**
- Render backend is deployed and running (not sleeping)
- Frontend env var `NEXT_PUBLIC_API_URL` is correct
- CORS allows your frontend domain

## How OAuth Flow Works Now

```
User                    Your Frontend              Your Backend              Slack
 |                            |                         |                      |
 |--[1] Click "Connect"------>|                         |                      |
 |                            |                         |                      |
 |                            |--[2] GET /slack/auth--->|                      |
 |                            |                         |                      |
 |                            |<--[3] auth_url---------|                      |
 |                            |                         |                      |
 |<--[4] Redirect to Slack---|                         |                      |
 |                            |                         |                      |
 |--[5] Authorize on Slack.com--------------------------------->|              |
 |                            |                         |                      |
 |<--[6] Redirect with code (to your backend)-----------------<|              |
 |                            |                         |                      |
 |                            |                         |<-[7] /callback------|
 |                            |                         |                      |
 |                            |                         |--[8] Exchange code-->|
 |                            |                         |<--[9] access_token--|
 |                            |                         |                      |
 |                            |                         | [10] Save to DB      |
 |                            |                         |                      |
 |<--[11] Redirect to frontend with ?success=slack-----|                      |
 |                            |                         |                      |
 |--[12] Show success-------->|                         |                      |
```

## Files Changed

- ✅ `frontend/components/integrations/Integrations.tsx` (3 changes)

## Files NOT Changed (Already Correct)

- ✅ `backend/api/integration_routes.py` - OAuth endpoints already exist
- ✅ `backend/connectors/slack_connector.py` - Connector already handles tokens
- ✅ `render.yaml` - Deployment config already has Slack env vars
- ✅ Slack app settings - Redirect URI already added

## Summary

**Before:** Manual token entry (bad UX, security risk)
**After:** One-click OAuth (like Notion, Asana, Zapier)

**User experience:**
- Before: "Find your token in Slack app settings, copy, paste..."
- After: "Click → Allow → Done!"

The fix is simple but powerful - users can now connect ANY Slack workspace with just 2 clicks.
