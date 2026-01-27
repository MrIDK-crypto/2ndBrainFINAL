# Slack Integration Setup Guide

This guide will walk you through setting up the Slack integration for use2ndbrain.

## Overview

The Slack integration syncs:
- Channel messages (public/private)
- Direct messages (optional)
- Thread replies
- File/link shares
- User mentions and relationships

## Prerequisites

1. A Slack workspace where you have admin permissions
2. The backend running on `http://localhost:5003`
3. The frontend running on `http://localhost:3000` (or 3006)

## Step 1: Create a Slack App

1. Go to https://api.slack.com/apps
2. Click **"Create New App"**
3. Choose **"From scratch"**
4. Enter:
   - **App Name:** `2nd Brain` (or your preferred name)
   - **Workspace:** Select your workspace
5. Click **"Create App"**

## Step 2: Configure OAuth & Permissions

### 2.1 Set Redirect URLs

1. In your Slack app, go to **"OAuth & Permissions"** (left sidebar)
2. Scroll to **"Redirect URLs"**
3. Click **"Add New Redirect URL"**
4. Add: `http://localhost:5003/api/integrations/slack/callback`
5. For production, also add: `https://your-production-domain.com/api/integrations/slack/callback`
6. Click **"Save URLs"**

### 2.2 Add Bot Token Scopes

Scroll down to **"Scopes"** → **"Bot Token Scopes"** and add:

**Essential Scopes (Minimum Required):**
- `channels:history` - Read messages from public channels
- `channels:read` - View basic channel info
- `groups:history` - Read messages from private channels
- `groups:read` - View basic private channel info
- `im:history` - Read DM history
- `im:read` - View DMs
- `users:read` - Get user information

**Recommended Additional Scopes:**
- `files:read` - Download files shared in messages
- `reactions:read` - Read emoji reactions
- `links:read` - Unfurl links

**Optional (for enhanced features):**
- `mpim:history` - Read group DMs
- `mpim:read` - View group DMs
- `team:read` - Read workspace info

### 2.3 Get Your Credentials

1. Go to **"Basic Information"** (left sidebar)
2. Scroll to **"App Credentials"**
3. Copy these values (you'll need them for `.env`):
   - **Client ID**
   - **Client Secret**
   - **Signing Secret**

## Step 3: Configure Backend Environment

1. Navigate to the backend directory:
   ```bash
   cd /Users/pranavreddymogathala/use2ndbrain/backend
   ```

2. Create or edit your `.env` file:
   ```bash
   # Copy from template if it doesn't exist
   cp ../.env.template .env
   ```

3. Add your Slack credentials to `.env`:
   ```bash
   # Slack Integration
   SLACK_CLIENT_ID=your-client-id-here
   SLACK_CLIENT_SECRET=your-client-secret-here
   SLACK_SIGNING_SECRET=your-signing-secret-here

   # Optional: Override redirect URI for production
   # SLACK_REDIRECT_URI=https://your-domain.com/api/integrations/slack/callback
   ```

## Step 4: Install Dependencies

Make sure the Slack SDK is installed:

```bash
cd /Users/pranavreddymogathala/use2ndbrain/backend
pip install slack-sdk
```

Or install all requirements:

```bash
pip install -r requirements.txt
```

## Step 5: Start the Application

### Terminal 1 - Backend
```bash
cd /Users/pranavreddymogathala/use2ndbrain/backend
python app_v2.py
# Should run on http://localhost:5003
```

### Terminal 2 - Frontend
```bash
cd /Users/pranavreddymogathala/use2ndbrain/frontend
npm run dev
# Usually runs on http://localhost:3000 or 3006
```

## Step 6: Connect Slack (via UI)

1. Open the frontend in your browser: `http://localhost:3000`
2. Log in to your account
3. Navigate to **Integrations** page
4. Find the **Slack** card
5. Click **"Connect"** button
6. You'll be redirected to Slack to authorize the app
7. Select the channels you want to sync (or grant access to all)
8. Click **"Allow"**
9. You'll be redirected back to the app

## Step 7: Configure Channels (Optional)

After connecting, you can configure which channels to sync:

### Via API:
```bash
# Get available channels
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:5003/api/integrations/slack/channels

# Update selected channels
curl -X PUT \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channels": ["C1234567890", "C0987654321"]}' \
  http://localhost:5003/api/integrations/slack/channels
```

### Via UI:
The UI should have a channel selection interface after connecting.

## Step 8: Sync Slack Messages

### Via UI:
1. Go to **Integrations** page
2. Find the Slack card (should show "Connected")
3. Click **"Sync Now"** button
4. Monitor sync progress in the modal

### Via API:
```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:5003/api/integrations/slack/sync
```

## Troubleshooting

### Issue: "Slack SDK not installed"

**Solution:**
```bash
cd /Users/pranavreddymogathala/use2ndbrain/backend
pip install slack-sdk
```

### Issue: "Invalid OAuth state"

**Causes:**
- State token expired (10 minute timeout)
- Server restarted during OAuth flow
- Redirect URI mismatch

**Solutions:**
1. Try the OAuth flow again
2. Verify redirect URI in Slack app matches `.env` configuration
3. Check that `SLACK_REDIRECT_URI` in `.env` matches what you configured in Slack app

### Issue: OAuth callback shows "missing_params"

**Solution:**
Check that your Slack app's redirect URL exactly matches:
```
http://localhost:5003/api/integrations/slack/callback
```

### Issue: "insufficient_scope" error

**Solution:**
1. Go to your Slack app → **OAuth & Permissions**
2. Add the missing scopes (see Step 2.2)
3. Reinstall the app to your workspace
4. Reconnect in the UI

### Issue: Messages not syncing

**Debugging Steps:**

1. Check backend logs for errors:
   ```bash
   # Look for lines starting with [Slack]
   ```

2. Verify connector status in database:
   ```bash
   sqlite3 backend/data/secondbrain.db "SELECT * FROM connectors WHERE connector_type='slack'"
   ```

3. Test connection manually:
   ```python
   from slack_sdk import WebClient

   client = WebClient(token="xoxb-your-bot-token")
   response = client.auth_test()
   print(response)
   ```

### Issue: "Slack app not installed to workspace"

**Solution:**
1. Go to your Slack app → **Install App**
2. Click **"Install to Workspace"**
3. Authorize the app
4. Copy the **Bot User OAuth Token** (starts with `xoxb-`)
5. You can use this token directly via the `/slack/token` endpoint if OAuth flow fails

## Advanced: Manual Token Entry

If the OAuth flow isn't working, you can manually enter the token:

1. Get your Bot User OAuth Token from Slack app → **Install App**
2. Use the token endpoint:
   ```bash
   curl -X POST \
     -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"access_token": "xoxb-your-bot-token"}' \
     http://localhost:5003/api/integrations/slack/token
   ```

## Connector Settings

The Slack connector supports these optional settings (stored in database):

```json
{
  "channels": [],              // Empty = sync all accessible channels
  "include_dms": true,         // Include direct messages
  "include_threads": true,     // Include thread replies
  "max_messages_per_channel": 1000,  // Message limit per channel
  "oldest_days": 365           // How far back to sync (in days)
}
```

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│ User clicks "Connect Slack"                     │
└───────────────┬─────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────┐
│ GET /api/integrations/slack/auth                │
│ → Generates OAuth URL with state token          │
└───────────────┬─────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────┐
│ User redirected to Slack                        │
│ → Authorizes app, selects channels              │
└───────────────┬─────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────┐
│ Slack redirects to callback URL with code       │
│ GET /api/integrations/slack/callback?code=...   │
└───────────────┬─────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────┐
│ Backend exchanges code for access token         │
│ → Saves to Connector table in database          │
└───────────────┬─────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────┐
│ User clicks "Sync Now"                          │
│ POST /api/integrations/slack/sync               │
└───────────────┬─────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────┐
│ SlackConnector.sync() runs:                     │
│ 1. Get accessible channels                      │
│ 2. For each channel:                            │
│    - Fetch message history                      │
│    - Convert to Document objects                │
│    - Extract user mentions                      │
│    - Include thread replies if enabled          │
│ 3. Save documents to database                   │
└─────────────────────────────────────────────────┘
```

## File References

| File | Purpose |
|------|---------|
| `backend/connectors/slack_connector.py` | Main Slack integration logic |
| `backend/api/integration_routes.py` | OAuth & sync endpoints (lines 339-731) |
| `backend/database/models.py` | Connector database model |
| `.env` | Configuration (credentials) |

## Next Steps

After successful sync:

1. **Classify Documents**: Messages are imported as "pending" classification
   - Go to **Documents** page
   - Run classification to determine work vs personal content

2. **Analyze Knowledge Gaps**:
   - Go to **Knowledge Gaps** page
   - Click "Analyze" to detect missing information

3. **Search & RAG**:
   - Use the **Chat** interface to search Slack messages
   - Ask questions about conversations and decisions

4. **Generate Training Materials**:
   - Create videos and guides from Slack knowledge

## Production Deployment

For production (Google Cloud Run, Render, etc.):

1. Update `.env` with production URLs:
   ```bash
   SLACK_REDIRECT_URI=https://your-domain.com/api/integrations/slack/callback
   FRONTEND_URL=https://your-frontend-domain.com
   ```

2. Update Slack app redirect URLs to include production URL

3. Use environment variables in Cloud Run/Render (not `.env` file)

4. Ensure HTTPS is enabled (required by Slack)

## Support

If you encounter issues:

1. Check backend logs for detailed error messages
2. Verify all environment variables are set correctly
3. Confirm Slack app scopes match requirements
4. Test OAuth flow in incognito/private browsing mode
5. Check database for connector status

---

**Last Updated:** 2026-01-26
