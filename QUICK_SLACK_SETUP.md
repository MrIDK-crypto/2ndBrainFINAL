# Quick Slack Setup - Using Existing Credentials

## Step 1: Find Your Render URLs (2 minutes)

1. Go to https://dashboard.render.com
2. Find these two services and copy their URLs:

   **Backend URL:**
   ```
   Click on "secondbrain-backend" → Copy the URL at the top
   Example: https://secondbrain-backend-abcd.onrender.com
   ```

   **Frontend URL:**
   ```
   Click on "secondbrain-frontend" → Copy the URL at the top
   Example: https://secondbrain-frontend-xyz.onrender.com
   ```

   **Write them down:**
   - Backend: `https://__________________________.onrender.com`
   - Frontend: `https://__________________________.onrender.com`

---

## Step 2: Add Credentials to Render Backend (5 minutes)

1. In Render Dashboard, click on **`secondbrain-backend`**
2. Click the **"Environment"** tab (left sidebar)
3. Click **"Add Environment Variable"** and add these:

   ```
   SLACK_CLIENT_ID
   6699781921109.10376139891302

   SLACK_CLIENT_SECRET
   c3e9e6ad53aca52149fc02647ceed215

   SLACK_SIGNING_SECRET
   60210d0077a153d8d6edd24f956157aa

   SLACK_REDIRECT_URI
   https://YOUR-BACKEND-URL.onrender.com/api/integrations/slack/callback
   (⚠️ Replace YOUR-BACKEND-URL with your actual backend URL from Step 1)

   FRONTEND_URL
   https://YOUR-FRONTEND-URL.onrender.com
   (⚠️ Replace YOUR-FRONTEND-URL with your actual frontend URL from Step 1)
   ```

4. Click **"Save Changes"** (your backend will automatically redeploy - takes ~2 minutes)

---

## Step 3: Update Slack App Redirect URL (3 minutes)

1. Go to https://api.slack.com/apps
2. Click on your **"2nd Brain"** app (or whatever you named it)
3. Click **"OAuth & Permissions"** (left sidebar)
4. Scroll to **"Redirect URLs"** section
5. Click **"Add New Redirect URL"**
6. Enter: `https://YOUR-BACKEND-URL.onrender.com/api/integrations/slack/callback`
   - ⚠️ Use your ACTUAL backend URL from Step 1
   - Example: `https://secondbrain-backend-abcd.onrender.com/api/integrations/slack/callback`
7. Click **"Add"**
8. Click **"Save URLs"** at the bottom

---

## Step 4: Verify Bot Scopes (1 minute)

While you're in the Slack app settings:

1. Still on **"OAuth & Permissions"** page
2. Scroll to **"Scopes"** → **"Bot Token Scopes"**
3. Make sure you have these (add if missing):
   - ✅ `channels:history`
   - ✅ `channels:read`
   - ✅ `groups:history`
   - ✅ `groups:read`
   - ✅ `im:history`
   - ✅ `im:read`
   - ✅ `users:read`
   - ✅ `files:read` (optional but recommended)

4. If you added any new scopes, you'll need to **reinstall the app** (Slack will prompt you)

---

## Step 5: Wait for Backend to Deploy (2 minutes)

1. Go back to Render Dashboard → `secondbrain-backend`
2. Check the **"Events"** tab or **"Logs"** tab
3. Wait for the deploy to finish (you'll see "Deploy live" or "Build successful")
4. Look for these lines in logs:
   ```
   ✓ Database initialized
   ✓ API blueprints registered
   ```

---

## Step 6: Test the Integration (5 minutes)

### Option A: Via Production Frontend (Recommended)

1. Open your production frontend URL: `https://YOUR-FRONTEND-URL.onrender.com`
2. **Log in** to your account (or sign up if you haven't)
3. Click on **"Integrations"** in the sidebar/menu
4. Find the **Slack** card
5. Click **"Connect"** button
6. You'll be redirected to Slack:
   - Select your workspace
   - Choose channels to allow access to
   - Click **"Allow"**
7. You'll be redirected back to your frontend
8. The Slack card should now show **"Connected"** status

### Option B: Direct API Test

```bash
# Replace with your actual backend URL
BACKEND_URL="https://your-backend.onrender.com"

# Test health endpoint
curl $BACKEND_URL/api/health

# Should return:
# {"status": "healthy", "timestamp": "..."}
```

---

## Step 7: Sync Slack Messages (2-10 minutes)

1. In your frontend, on the **Integrations** page
2. Find the Slack card (should show "Connected" with a green checkmark)
3. Click **"Sync Now"** button
4. A modal will appear showing sync progress:
   - Fetching channels...
   - Syncing messages from #general...
   - Syncing messages from #random...
   - etc.
5. Wait for sync to complete

**Note:** First sync may take several minutes depending on:
- Number of channels
- Number of messages
- Render free tier performance (services wake up slowly)

---

## Troubleshooting

### Problem: Backend deploy failed

**Check:**
1. Render Dashboard → secondbrain-backend → Logs tab
2. Look for error messages (usually Python import errors or missing dependencies)

**Common fixes:**
```bash
# If slack_sdk missing, add to requirements.txt:
slack-sdk>=3.23.0
```

### Problem: "Invalid redirect_uri" error during OAuth

**Cause:** Mismatch between Slack app redirect URL and environment variable

**Fix:**
1. Double-check both match EXACTLY (including https://, no trailing slash)
2. Slack app shows: `https://secondbrain-backend-abcd.onrender.com/api/integrations/slack/callback`
3. Render env var `SLACK_REDIRECT_URI` shows the same

### Problem: Frontend can't reach backend

**Check CORS:**
1. Render → secondbrain-frontend → Environment tab
2. Verify: `NEXT_PUBLIC_API_URL=https://your-backend.onrender.com`
3. Save and redeploy if you changed it

**Also check backend CORS** (should be okay with `"*"` in the code)

### Problem: Sync takes forever / times out

**Solutions:**
1. **Select specific channels** instead of syncing all:
   - Use the channel selector in the UI
   - Or update connector settings via API

2. **Reduce sync scope:**
   ```json
   {
     "max_messages_per_channel": 500,
     "oldest_days": 90
   }
   ```

3. **Upgrade Render plan** for better performance (free tier is slow)

### Problem: "Service Unavailable" or long loading times

**Cause:** Render free tier services sleep after 15 minutes of inactivity

**Solution:**
- First request takes ~30 seconds to wake up the service
- Wait patiently, then reload
- Upgrade to paid tier to prevent sleeping

---

## Verify Everything Works

### 1. Check Integration Status

**Via UI:**
- Go to Integrations page
- Slack card should show:
  - Status: "Connected" (green)
  - Last sync: Recent timestamp
  - Total items: Number of messages synced

**Via Database:**
```bash
# In Render Dashboard → secondbrain-db → Connect
# Copy the external connection command and run locally:

psql <connection-string>

# Then query:
SELECT connector_type, status, name, last_sync_at, total_items_synced
FROM connectors
WHERE connector_type = 'slack';
```

### 2. Check Documents Were Imported

```bash
# In the same psql session:
SELECT COUNT(*) FROM documents WHERE source = 'slack';

# Should return > 0
```

### 3. Test Search

1. Go to **Chat** page in your frontend
2. Ask a question about content from your Slack messages
3. Example: "What did we discuss about the project timeline?"
4. Should return relevant messages with citations

---

## Next Steps After Slack Works

1. **Classify Documents**
   - Go to Documents page
   - Click "Classify All"
   - AI will determine which messages are work-related

2. **Analyze Knowledge Gaps**
   - Go to Knowledge Gaps page
   - Click "Analyze"
   - System will find missing information

3. **Answer Gaps**
   - Review detected gaps
   - Provide answers (text or voice)
   - Answers get embedded for search

4. **Generate Training Materials**
   - Select answered gaps
   - Generate videos/guides
   - Share with new team members

---

## Production URLs Reference

Fill these in as you go:

```
Backend URL:  https://_________________________________.onrender.com

Frontend URL: https://_________________________________.onrender.com

Slack OAuth:  https://_________________________________.onrender.com/api/integrations/slack/callback

Health Check: https://_________________________________.onrender.com/api/health
```

---

## Security Note

⚠️ **Your credentials were exposed in a public chat.** While you're using them now, **strongly recommend** regenerating them later:

1. After everything is working
2. Go to Slack app → Basic Information
3. Regenerate Client Secret and Signing Secret
4. Update in Render environment variables
5. No code changes needed - just env var update

This prevents anyone who saw the screenshot from potentially accessing your Slack workspace.

---

## Quick Command Reference

```bash
# Test backend health
curl https://your-backend.onrender.com/api/health

# Check backend logs (in Render dashboard)
secondbrain-backend → Logs → Live logs

# Redeploy backend
secondbrain-backend → Manual Deploy → Deploy latest commit

# Check environment variables
secondbrain-backend → Environment → View all
```

---

**That's it!** You should now have Slack fully integrated with your production deployment on Render.

**Questions?** Check the detailed guides:
- `SLACK_INTEGRATION_SETUP.md` - Full technical reference
- `SLACK_RENDER_SETUP.md` - Production deployment details
