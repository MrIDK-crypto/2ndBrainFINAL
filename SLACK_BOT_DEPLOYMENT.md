# Slack Bot Deployment Guide

> Complete step-by-step guide to deploy the 2nd Brain Slack bot on Render

---

## Overview

The Slack bot is **fully implemented** in the codebase:
- OAuth v2 flow: `/api/slack/oauth/install`, `/api/slack/oauth/callback`
- Slash commands: `/ask <question>`
- Event handling: App mentions (@2ndBrain), Direct messages
- RAG integration: Uses enhanced search service for answers

**Status**: ✅ Code complete, needs Slack app configuration

---

## Step 1: Create Slack App

1. Go to https://api.slack.com/apps
2. Click **"Create New App"** → **"From scratch"**
3. **App Name**: `2nd Brain`
4. **Workspace**: Select your workspace
5. Click **"Create App"**

---

## Step 2: Configure OAuth & Permissions

1. Navigate to **"OAuth & Permissions"** in the left sidebar
2. Scroll to **"Redirect URLs"** section
3. Click **"Add New Redirect URL"**
4. Enter your Render backend URL:
   ```
   https://secondbrain-backend-XXXX.onrender.com/api/slack/oauth/callback
   ```
   (Replace `XXXX` with your actual Render service URL)
5. Click **"Add"** then **"Save URLs"**

6. Scroll to **"Scopes"** section → **"Bot Token Scopes"**
7. Add the following scopes (click "Add an OAuth Scope"):
   - `app_mentions:read` - Hear when @2ndBrain is mentioned
   - `channels:history` - Read messages in channels
   - `channels:read` - Access channel list
   - `chat:write` - Post messages as bot
   - `commands` - Receive slash commands
   - `im:history` - Read DM messages
   - `im:read` - Access DM list
   - `im:write` - Send DMs
   - `users:read` - Read user info

---

## Step 3: Configure Event Subscriptions

1. Navigate to **"Event Subscriptions"** in the left sidebar
2. Toggle **"Enable Events"** to **ON**
3. **Request URL**:
   ```
   https://secondbrain-backend-XXXX.onrender.com/api/slack/events
   ```
4. Wait for Slack to verify the URL (should show ✓ Verified)

5. Scroll to **"Subscribe to bot events"**
6. Click **"Add Bot User Event"** and add:
   - `app_mention` - When someone @mentions the bot
   - `message.im` - When someone DMs the bot

7. Click **"Save Changes"** at the bottom

---

## Step 4: Configure Slash Commands

1. Navigate to **"Slash Commands"** in the left sidebar
2. Click **"Create New Command"**
3. Fill in the form:
   - **Command**: `/ask`
   - **Request URL**: `https://secondbrain-backend-XXXX.onrender.com/api/slack/commands/ask`
   - **Short Description**: `Ask 2nd Brain a question`
   - **Usage Hint**: `What is our pricing model?`
4. Click **"Save"**

---

## Step 5: Get App Credentials

1. Navigate to **"Basic Information"** in the left sidebar
2. Scroll to **"App Credentials"** section
3. Copy the following values:
   - **Client ID**
   - **Client Secret**
   - **Signing Secret**

---

## Step 6: Add Environment Variables to Render

1. Go to your Render dashboard: https://dashboard.render.com
2. Select your **secondbrain-backend** service
3. Click **"Environment"** in the left sidebar
4. Add the following environment variables (click "Add Environment Variable"):

   ```bash
   SLACK_CLIENT_ID=<paste Client ID from Slack>
   SLACK_CLIENT_SECRET=<paste Client Secret from Slack>
   SLACK_SIGNING_SECRET=<paste Signing Secret from Slack>
   ```

5. Click **"Save Changes"**
6. Wait for Render to redeploy (automatic)

---

## Step 7: Install Bot to Workspace

1. In Slack App settings, navigate to **"OAuth & Permissions"**
2. Scroll to top, click **"Install to Workspace"**
3. Review permissions, click **"Allow"**
4. You should be redirected to your frontend at:
   ```
   https://your-frontend.onrender.com/integrations?slack_connected=true
   ```

---

## Step 8: Test the Integration

### Test Slash Command

1. In any Slack channel or DM, type:
   ```
   /ask What is 2nd Brain?
   ```
2. Bot should respond with a RAG-generated answer based on your knowledge base

### Test App Mention

1. In a channel where the bot is present, type:
   ```
   @2nd Brain What are our company values?
   ```
2. Bot should respond in thread

### Test Direct Message

1. Open a DM with the bot
2. Send a message:
   ```
   Tell me about our product roadmap
   ```
3. Bot should respond with RAG answer

---

## Troubleshooting

### "URL verification failed"

**Cause**: Render backend not deployed or URL incorrect

**Fix**:
1. Verify backend is running: `curl https://secondbrain-backend-XXXX.onrender.com/api/health`
2. Check Event Subscriptions URL matches exactly
3. Check Render logs for errors: Dashboard → Logs

### "Invalid request signature"

**Cause**: Signing secret mismatch

**Fix**:
1. Verify `SLACK_SIGNING_SECRET` in Render matches Slack app
2. Redeploy backend after updating env vars
3. Check for whitespace in secret (trim before pasting)

### "Workspace not connected"

**Cause**: OAuth flow incomplete or token not stored

**Fix**:
1. Reinstall app to workspace (Step 7)
2. Check backend logs for OAuth errors:
   ```
   [SlackBot] Workspace connected: YourWorkspace (T0123456)
   ```
3. Verify callback URL matches redirect URL in Slack app settings

### Bot doesn't respond to `/ask`

**Cause**: Command URL incorrect or backend error

**Fix**:
1. Verify command URL in Slack matches:
   `https://secondbrain-backend-XXXX.onrender.com/api/slack/commands/ask`
2. Check Render logs for command errors:
   ```
   [SlackBot] Command error: ...
   ```
3. Ensure tenant has knowledge base indexed

### Bot doesn't respond to mentions

**Cause**: Event subscription not working

**Fix**:
1. Verify Event Subscriptions URL is verified (green checkmark)
2. Check bot has `app_mentions:read` scope
3. Invite bot to channel: `/invite @2nd Brain`
4. Check logs for event processing:
   ```
   [SlackBot] Handling app mention in channel C0123456
   ```

---

## Architecture Overview

```
Slack User
    ↓
Slack API
    ↓
POST /api/slack/commands/ask (slash command)
POST /api/slack/events (mentions, DMs)
    ↓
backend/api/slack_bot_routes.py
    ↓
services/slack_bot_service.py
    ↓
services/enhanced_search_service.py (RAG)
    ↓
Response sent to Slack
```

---

## Features Implemented

| Feature | Status | Endpoint |
|---------|--------|----------|
| OAuth v2 Flow | ✅ Complete | `/api/slack/oauth/*` |
| `/ask` Command | ✅ Complete | `/api/slack/commands/ask` |
| App Mentions | ✅ Complete | `/api/slack/events` |
| Direct Messages | ✅ Complete | `/api/slack/events` |
| Signature Verification | ✅ Complete | Middleware |
| RAG Integration | ✅ Complete | Uses enhanced search |
| Multi-Workspace | ✅ Complete | Tenant mapping |

---

## Security Notes

- ✅ **Request Signature Verification**: All Slack requests verified using signing secret
- ✅ **5-Minute Timestamp Window**: Prevents replay attacks
- ✅ **Tenant Isolation**: Each workspace mapped to tenant_id
- ✅ **HTTPS Only**: All Slack communication over HTTPS

---

## Logs to Monitor

When running successfully, you should see:

```bash
# OAuth flow
[SlackBot] Workspace connected: Acme Corp (T0123456)

# Slash command
[SlackBot] Handling /ask command: "What is our pricing?"
[SlackBot] RAG search complete: 5 results

# App mention
[SlackBot] Handling app mention in channel C0123456

# Health check
[2025-12-09 10:30:15] [INFO] [HealthCheck] All systems operational
```

---

## Cost & Rate Limits

- **Slack API**: Free tier includes unlimited messages
- **Bot Tokens**: No expiration (unless revoked)
- **Rate Limits**: 1 request/second per workspace (enforced by Slack)
- **Backend**: No additional cost (uses existing Render deployment)

---

## Next Steps

After successful deployment:

1. **Add to Multiple Workspaces**: Each workspace needs separate OAuth
2. **Customize Responses**: Edit `services/slack_bot_service.py`
3. **Add Interactive Components**: Buttons, dropdowns (already has `/api/slack/interactive` endpoint)
4. **Monitor Usage**: Check Render logs for popular queries

---

## Support

If issues persist:

1. Check Render logs: `Dashboard → secondbrain-backend → Logs`
2. Check Slack app logs: `https://api.slack.com/apps/YOUR_APP_ID/event-subscriptions`
3. Verify environment variables are set correctly
4. Test health endpoint: `curl https://secondbrain-backend-XXXX.onrender.com/api/health`

---

*Last updated: 2025-01-30*
