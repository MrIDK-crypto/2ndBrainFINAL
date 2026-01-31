#!/usr/bin/env python3
"""
Test Pinecone connection and API key
"""

import os
import sys

# Get configuration from environment variables
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX", os.getenv("PINECONE_INDEX_NAME", "secondbrain"))

if not PINECONE_API_KEY:
    print("❌ ERROR: PINECONE_API_KEY environment variable not set")
    print("\nSet it with:")
    print("  export PINECONE_API_KEY='your-key-here'")
    exit(1)

print("=" * 60)
print("PINECONE CONNECTION TEST")
print("=" * 60)

try:
    from pinecone import Pinecone

    print(f"\n✓ Pinecone library imported")
    print(f"  API Key: {PINECONE_API_KEY[:20]}...{PINECONE_API_KEY[-10:]}")
    print(f"  Index Name: {PINECONE_INDEX_NAME}")

    # Initialize Pinecone
    print("\n🔗 Connecting to Pinecone...")
    pc = Pinecone(api_key=PINECONE_API_KEY)

    # List indexes
    print("\n📋 Listing indexes...")
    indexes = pc.list_indexes()
    index_names = [idx.name for idx in indexes]

    print(f"  Found {len(index_names)} index(es):")
    for name in index_names:
        print(f"    - {name}")

    # Check if target index exists
    if PINECONE_INDEX_NAME in index_names:
        print(f"\n✓ Target index '{PINECONE_INDEX_NAME}' exists")

        # Get index stats
        print(f"\n📊 Getting stats for '{PINECONE_INDEX_NAME}'...")
        index = pc.Index(PINECONE_INDEX_NAME)
        stats = index.describe_index_stats()

        print(f"  Total vectors: {stats.total_vector_count:,}")
        print(f"  Dimension: {stats.dimension if hasattr(stats, 'dimension') else 'N/A'}")

        if hasattr(stats, 'namespaces') and stats.namespaces:
            print(f"  Namespaces:")
            for namespace, ns_stats in stats.namespaces.items():
                print(f"    - {namespace}: {ns_stats.vector_count:,} vectors")

        print("\n✅ CONNECTION SUCCESSFUL")
        print("=" * 60)
        print("\nYou can now use this API key on Render:")
        print(f"  PINECONE_API_KEY={PINECONE_API_KEY}")
        print(f"  PINECONE_INDEX_NAME={PINECONE_INDEX_NAME}")

    else:
        print(f"\n⚠️  WARNING: Index '{PINECONE_INDEX_NAME}' not found")
        print(f"  Available indexes: {index_names}")
        print("\n  Either:")
        print(f"  1. Use one of the existing indexes above")
        print(f"  2. Create a new index named '{PINECONE_INDEX_NAME}'")

except Exception as e:
    print(f"\n❌ ERROR: {e}")
    print(f"\n  Error type: {type(e).__name__}")
    import traceback
    traceback.print_exc()

    print("\n📝 Troubleshooting:")
    print("  1. Check if the API key is correct")
    print("  2. Check if the API key is active in Pinecone dashboard")
    print("  3. Make sure you're using the correct Pinecone project")

print("\n" + "=" * 60)
