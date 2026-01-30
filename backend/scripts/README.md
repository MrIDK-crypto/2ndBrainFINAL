# Database Management Scripts

Scripts for resetting and seeding the database with test data.

---

## Overview

| Script | Purpose |
|--------|---------|
| `reset_database.py` | **DESTRUCTIVE** - Clears all data from PostgreSQL, Pinecone, and Redis |
| `seed_database.py` | Creates test tenants and users with proper isolation |

---

## Quick Start

### **Option 1: Full Reset + Seed (Recommended)**

Reset everything and create fresh test data:

```bash
cd backend

# Reset all databases (DESTRUCTIVE!)
python scripts/reset_database.py

# Create test tenants and users
python scripts/seed_database.py
```

### **Option 2: Add Seed Data to Existing Database**

If you just want to add test users without deleting existing data:

```bash
cd backend
python scripts/seed_database.py --force
```

---

## Reset Database Script

### What It Does

Clears **ALL DATA** from:
1. **PostgreSQL** - Drops and recreates all tables
2. **Pinecone** - Deletes all vectors (embeddings)
3. **Redis** - Flushes all cache keys

### Usage

```bash
# Interactive mode (asks for confirmation)
python scripts/reset_database.py

# Force mode (no confirmation)
python scripts/reset_database.py --force
```

### Safety

- **Requires confirmation** unless `--force` flag is used
- You must type `DELETE EVERYTHING` to proceed
- **This cannot be undone** - all data will be lost

### Example Output

```
🔥 DATABASE RESET SCRIPT
========================================================================

⚠️  WARNING: This will DELETE ALL DATA!
   - PostgreSQL database (all tables)
   - Pinecone vectors (all embeddings)
   - Redis cache (all keys)

========================================================================

Type 'DELETE EVERYTHING' to continue: DELETE EVERYTHING

========================================================================
RESETTING POSTGRESQL DATABASE
========================================================================

[1/3] Dropping all tables...
✓ All tables dropped

[2/3] Recreating tables with fresh schema...
✓ All tables created

[3/3] Verifying tables...
✓ Created 15 tables:
  - tenants
  - users
  - user_sessions
  - connectors
  - documents
  - document_chunks
  - projects
  - knowledge_gaps
  - gap_answers
  - videos
  - audit_logs
  - ...

✅ PostgreSQL database reset complete!

========================================================================
RESETTING PINECONE VECTOR STORE
========================================================================

[1/2] Connecting to Pinecone index: secondbrain
✓ Connected. Current vectors: 12,453

[2/2] Deleting all 12,453 vectors...
✓ All vectors deleted

✅ Pinecone reset complete! 0 vectors remaining.

========================================================================
RESETTING REDIS CACHE
========================================================================

[1/2] Connecting to Redis: redis://localhost:6379/0
✓ Connected. Current keys: 47

[2/2] Flushing 47 keys...
✓ All keys deleted

✅ Redis reset complete! 0 keys remaining.

========================================================================
RESET SUMMARY
========================================================================
PostgreSQL: ✅ SUCCESS
Pinecone: ✅ SUCCESS
Redis: ✅ SUCCESS

✅ ALL RESETS COMPLETE!

Next steps:
  1. Run: python scripts/seed_database.py
  2. Log in with test accounts
```

---

## Seed Database Script

### What It Creates

Creates a complete multi-tenant setup with:

#### **4 Tenants (Organizations)**

| Tenant | Domain | Plan | Users |
|--------|--------|------|-------|
| Acme Corporation | acme.com | Enterprise | 4 users |
| Startup Inc | startup.io | Professional | 3 users |
| Small Business LLC | smallbiz.com | Starter | 2 users |
| Free Tier Co | freetier.org | Free | 1 user |

#### **10 Users (Across All Tenants)**

Each tenant has proper isolation - users can only see their tenant's data.

### Usage

```bash
# Create seed data
python scripts/seed_database.py

# Force creation (skip existing data warning)
python scripts/seed_database.py --force
```

### Example Output

```
🌱 DATABASE SEED SCRIPT
========================================================================

========================================================================
CREATING TENANTS
========================================================================

[1/4] Creating: Acme Corporation
  ✓ ID: 01234567-89ab-cdef-0123-456789abcdef
  ✓ Domain: acme.com
  ✓ Plan: enterprise
  ✓ Enterprise customer - unlimited access

[2/4] Creating: Startup Inc
  ✓ ID: 12345678-9abc-def0-1234-56789abcdef0
  ✓ Domain: startup.io
  ✓ Plan: professional
  ✓ Professional plan with advanced features

[3/4] Creating: Small Business LLC
  ✓ ID: 23456789-abcd-ef01-2345-6789abcdef01
  ✓ Domain: smallbiz.com
  ✓ Plan: starter
  ✓ Starter plan - basic features

[4/4] Creating: Free Tier Co
  ✓ ID: 3456789a-bcde-f012-3456-789abcdef012
  ✓ Domain: freetier.org
  ✓ Plan: free
  ✓ Free plan for testing

✅ Created 4 tenants

========================================================================
CREATING USERS
========================================================================

[1/10] Creating: Alice Admin
  ✓ ID: 456789ab-cdef-0123-4567-89abcdef0123
  ✓ Email: admin@acme.com
  ✓ Tenant: acme.com
  ✓ Role: admin

...

✅ Created 10 users

========================================================================
VERIFYING TENANT ISOLATION
========================================================================

✓ Acme Corporation (acme.com):
  - Tenant ID: 01234567-89ab-cdef-0123-456789abcdef
  - Plan: enterprise
  - Users: 4
  - Other tenants have 6 users (isolated ✓)

✓ Startup Inc (startup.io):
  - Tenant ID: 12345678-9abc-def0-1234-56789abcdef0
  - Plan: professional
  - Users: 3
  - Other tenants have 7 users (isolated ✓)

✓ Small Business LLC (smallbiz.com):
  - Tenant ID: 23456789-abcd-ef01-2345-6789abcdef01
  - Plan: starter
  - Users: 2
  - Other tenants have 8 users (isolated ✓)

✓ Free Tier Co (freetier.org):
  - Tenant ID: 3456789a-bcde-f012-3456-789abcdef012
  - Plan: free
  - Users: 1
  - Other tenants have 9 users (isolated ✓)

✅ Tenant isolation verified!

========================================================================
SEED DATA SUMMARY
========================================================================

📁 acme.com
  --------------------------------------------------------------------
  👤 Alice Admin           (admin)
     Email:    admin@acme.com
     Password: admin123
     User ID:  456789ab-cdef-0123-4567-89abcdef0123
     Tenant:   01234567-89ab-cdef-0123-456789abcdef

  👤 Bob User              (member)
     Email:    user@acme.com
     Password: user123
     User ID:  56789abc-def0-1234-5678-9abcdef01234
     Tenant:   01234567-89ab-cdef-0123-456789abcdef

  ...

========================================================================
LOGIN INSTRUCTIONS
========================================================================

1. Go to your frontend: https://twondbrain-frontend.onrender.com
2. Click 'Login'
3. Use any email/password combination above

RECOMMENDED TEST ACCOUNTS:
  • admin@acme.com / admin123 (Enterprise admin)
  • founder@startup.io / founder123 (Professional admin)
  • test@freetier.org / test123 (Free tier)

✅ Seed data created successfully!
```

---

## Test Accounts

### **Acme Corporation (Enterprise)**

| Email | Password | Name | Role |
|-------|----------|------|------|
| admin@acme.com | admin123 | Alice Admin | Admin |
| user@acme.com | user123 | Bob User | Member |
| viewer@acme.com | viewer123 | Charlie Viewer | Viewer |
| demo@acme.com | demo123 | Ivan Demo | Member |

### **Startup Inc (Professional)**

| Email | Password | Name | Role |
|-------|----------|------|------|
| founder@startup.io | founder123 | Diana Founder | Admin |
| engineer@startup.io | engineer123 | Eve Engineer | Member |
| demo@startup.io | demo123 | Julia Demo | Member |

### **Small Business LLC (Starter)**

| Email | Password | Name | Role |
|-------|----------|------|------|
| owner@smallbiz.com | owner123 | Frank Owner | Admin |
| employee@smallbiz.com | employee123 | Grace Employee | Member |

### **Free Tier Co (Free)**

| Email | Password | Name | Role |
|-------|----------|------|------|
| test@freetier.org | test123 | Henry Test | Admin |

---

## Tenant Isolation Features

### **How It Works**

1. **Separate Tenants**
   - Each organization is a separate tenant
   - Tenants have unique IDs (UUIDs)
   - Different subscription plans (Free, Starter, Professional, Enterprise)

2. **User Assignment**
   - Every user belongs to exactly one tenant
   - Users have `tenant_id` foreign key
   - JWT tokens include `tenant_id` claim

3. **Data Isolation**
   - All queries filtered by `tenant_id`
   - No cross-tenant data access
   - Enforced at database level

4. **Rate Limiting**
   - Different limits per plan
   - Free tier: 20 searches/min
   - Enterprise: 500 searches/min

### **Testing Isolation**

1. **Login as admin@acme.com**
   - Should see only Acme's data
   - Cannot see Startup's documents

2. **Login as founder@startup.io**
   - Should see only Startup's data
   - Cannot see Acme's documents

3. **Try to access another tenant's data**
   - API should return 403 Forbidden
   - Or 404 Not Found (document doesn't exist in your tenant)

---

## Environment Variables Required

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:port/dbname

# Pinecone (for vector reset)
PINECONE_API_KEY=your-key
PINECONE_INDEX=secondbrain

# Redis (for cache reset)
REDIS_URL=redis://host:port/0
```

---

## Troubleshooting

### Script fails with "No module named 'database'"

```bash
# Make sure you're in the backend directory
cd backend
python scripts/reset_database.py
```

### PostgreSQL connection error

```bash
# Check DATABASE_URL is set
echo $DATABASE_URL

# Or check .env file
cat .env | grep DATABASE_URL
```

### Pinecone skip warning

```
⚠️  PINECONE_API_KEY not found, skipping...
```

This is OK - Pinecone reset is optional if you don't have embeddings yet.

### Redis skip warning

```
❌ Error resetting Redis: ...
(Redis may not be running locally - this is OK for cloud deployments)
```

This is OK - Redis reset is optional for local development.

---

## Production Warning

⚠️ **DO NOT RUN THESE SCRIPTS IN PRODUCTION**

These scripts are for **development and testing only**.

For production:
- Use database migrations (Alembic)
- Create backups before any destructive operation
- Use proper user onboarding flow (signup API)

---

## Next Steps After Seeding

1. **Test Login**
   - Go to frontend
   - Login with test accounts
   - Verify tenant isolation

2. **Add Test Data**
   - Connect integrations (Gmail, Slack, Box)
   - Sync some documents
   - Run knowledge gap analysis

3. **Test Features**
   - Search (RAG)
   - Knowledge gaps
   - Video generation
   - Chat interface

---

**Created**: 2026-01-30
**Last Updated**: 2026-01-30
