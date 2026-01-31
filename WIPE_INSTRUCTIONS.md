# How to Wipe All Databases

This guide will help you wipe all data from your production databases on Render while preserving the database schema.

## What Will Be Deleted

- ✅ **PostgreSQL Database**: All user accounts, documents, embeddings metadata, etc.
- ✅ **Pinecone Vector Store**: All document embeddings (vector data)
- ✅ **Redis Cache**: All cached data (if enabled)

## What Will Be Preserved

- ✅ **Database Schema**: All table structures remain intact
- ✅ **Pinecone Index**: The index structure remains, just vectors are deleted
- ✅ **Code & Configuration**: No code changes

---

## Step-by-Step Instructions

### Step 1: Access Render Backend Shell

1. Go to https://dashboard.render.com
2. Find your backend service: `twondbrain-backend-docker`
3. Click on it
4. Click the **"Shell"** tab at the top
5. Wait for the shell to connect

### Step 2: Run the Wipe Script

In the Render shell, run:

```bash
python wipe_production_db.py
```

### Step 3: Confirm the Wipe

The script will show you what will be deleted and ask for confirmation:

```
⚠️  WARNING: This will DELETE ALL DATA from:
  - PostgreSQL database (all tables)
  - Pinecone vector index (all embeddings)
  - Redis cache (all keys)

⚠️  Type 'WIPE' to confirm deletion:
```

Type exactly: `WIPE` (all caps) and press Enter.

### Step 4: Wait for Completion

The script will:
1. Delete all rows from PostgreSQL tables
2. Delete all vectors from Pinecone
3. Clear Redis cache
4. Show you a summary of what was deleted

Expected output:
```
✅ PostgreSQL wiped: 1,234 total rows deleted
✅ Pinecone wiped: 5,678 → 0 vectors
✅ Redis wiped: 42 keys deleted

✅ ALL DATABASES WIPED SUCCESSFULLY
```

### Step 5: Start Fresh

After the wipe:

1. Go to https://twondbrain-frontend.onrender.com
2. Sign up with a **new account** (old credentials won't work)
3. Connect your integrations:
   - Gmail
   - Slack
   - Box
   - WebScraper
4. Sync your data

---

## Alternative: Manual Wipe via SQL (PostgreSQL only)

If the script doesn't work, you can manually wipe PostgreSQL:

### 1. Get PostgreSQL Connection String

In Render:
1. Go to your **PostgreSQL database** service (not backend)
2. Look for the **Internal Database URL** or **External Database URL**

### 2. Connect with psql

In your Render backend shell:

```bash
# Connect to database
psql $DATABASE_URL

# List all tables
\dt

# Delete all data (preserving schema)
TRUNCATE TABLE users, tenants, user_sessions, documents, document_chunks,
             connectors, projects, knowledge_gaps, gap_answers, videos,
             audit_logs CASCADE;

# Verify
SELECT COUNT(*) FROM users;

# Exit
\q
```

### 3. Wipe Pinecone

Create a temporary Python script in the shell:

```bash
cat > wipe_pinecone.py << 'EOF'
import os
from pinecone import Pinecone

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "2nd-brain-index"))

stats_before = index.describe_index_stats()
print(f"Before: {stats_before.total_vector_count} vectors")

index.delete(delete_all=True)

stats_after = index.describe_index_stats()
print(f"After: {stats_after.total_vector_count} vectors")
EOF

python wipe_pinecone.py
```

---

## Troubleshooting

### "psycopg2 not installed"

The script needs psycopg2 to connect to PostgreSQL. Install it:

```bash
pip install psycopg2-binary
```

Then run the wipe script again.

### "Pinecone library not installed"

Install Pinecone:

```bash
pip install pinecone-client
```

Then run the wipe script again.

### "DATABASE_URL not set"

Check your environment variables:

```bash
env | grep DATABASE_URL
```

If empty, the DATABASE_URL environment variable is missing. Contact Render support.

### Wipe Completed but Frontend Still Shows Old Data

1. Clear your browser cache (Ctrl+Shift+Delete / Cmd+Shift+Delete)
2. Hard refresh the page (Ctrl+F5 / Cmd+Shift+R)
3. Try in an incognito/private window
4. Check if frontend has been redeployed after the backend wipe

---

## Safety Notes

- ⚠️ **This is IRREVERSIBLE** - there's no undo
- ⚠️ Make sure you have backups if you need any of the data
- ⚠️ All users will need to sign up again
- ⚠️ All integrations will need to be reconnected
- ⚠️ All synced data will need to be re-synced

---

## What Happens After Wipe

✅ Database tables exist but are empty
✅ Pinecone index exists but has 0 vectors
✅ Frontend loads but shows no documents
✅ You can immediately create a new account
✅ You can reconnect all integrations
✅ Data syncs will work normally

---

## Need Help?

If you encounter issues:

1. Check the Render logs for error messages
2. Verify environment variables are set correctly
3. Make sure the backend service is running
4. Try the manual SQL method as a fallback
