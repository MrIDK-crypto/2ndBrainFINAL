#!/bin/bash

# Reset and Seed Database
# Convenience script to reset and seed in one command

set -e  # Exit on error

echo "=========================================================================="
echo "🔄 RESET AND SEED DATABASE"
echo "=========================================================================="
echo ""
echo "This script will:"
echo "  1. Delete all data (PostgreSQL, Pinecone, Redis)"
echo "  2. Create fresh test tenants and users"
echo ""

# Check if in backend directory
if [ ! -f "app_v2.py" ]; then
    echo "❌ Error: Must run from backend directory"
    echo "   cd backend && bash scripts/reset_and_seed.sh"
    exit 1
fi

# Step 1: Reset
echo "Step 1/2: Resetting databases..."
echo ""
python scripts/reset_database.py --force

echo ""
echo "=========================================================================="
echo ""

# Step 2: Seed
echo "Step 2/2: Creating seed data..."
echo ""
python scripts/seed_database.py --force

echo ""
echo "=========================================================================="
echo "✅ COMPLETE!"
echo "=========================================================================="
echo ""
echo "You can now:"
echo "  • Login at: https://twondbrain-frontend.onrender.com"
echo "  • Use: admin@acme.com / admin123"
echo "  • Or any other test account from the list above"
echo ""
