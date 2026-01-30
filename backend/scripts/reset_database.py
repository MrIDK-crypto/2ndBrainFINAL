"""
Reset Database Script
Clears all data and recreates tables with proper tenant isolation.

WARNING: This is DESTRUCTIVE - all data will be lost!
"""

import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from database.models import Base, engine, SessionLocal
from database.config import get_database_url


def reset_postgresql_database():
    """Drop all tables and recreate schema"""
    print("\n" + "="*70)
    print("RESETTING POSTGRESQL DATABASE")
    print("="*70)

    try:
        # Drop all tables
        print("\n[1/3] Dropping all tables...")
        Base.metadata.drop_all(bind=engine)
        print("✓ All tables dropped")

        # Recreate all tables
        print("\n[2/3] Recreating tables with fresh schema...")
        Base.metadata.create_all(bind=engine)
        print("✓ All tables created")

        # Verify tables exist
        print("\n[3/3] Verifying tables...")
        db = SessionLocal()
        try:
            result = db.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            tables = [row[0] for row in result]
            print(f"✓ Created {len(tables)} tables:")
            for table in tables:
                print(f"  - {table}")
        finally:
            db.close()

        print("\n✅ PostgreSQL database reset complete!")
        return True

    except Exception as e:
        print(f"\n❌ Error resetting PostgreSQL: {e}")
        import traceback
        traceback.print_exc()
        return False


def reset_pinecone_index():
    """Delete all vectors from Pinecone"""
    print("\n" + "="*70)
    print("RESETTING PINECONE VECTOR STORE")
    print("="*70)

    try:
        from pinecone import Pinecone

        api_key = os.getenv('PINECONE_API_KEY')
        index_name = os.getenv('PINECONE_INDEX', 'secondbrain')

        if not api_key:
            print("⚠️  PINECONE_API_KEY not found, skipping...")
            return True

        print(f"\n[1/2] Connecting to Pinecone index: {index_name}")
        pc = Pinecone(api_key=api_key)
        index = pc.Index(index_name)

        # Get stats before deletion
        stats = index.describe_index_stats()
        total_vectors = stats.get('total_vector_count', 0)
        print(f"✓ Connected. Current vectors: {total_vectors:,}")

        if total_vectors > 0:
            print(f"\n[2/2] Deleting all {total_vectors:,} vectors...")
            # Delete all vectors by deleting everything in all namespaces
            index.delete(delete_all=True)
            print("✓ All vectors deleted")
        else:
            print("\n[2/2] No vectors to delete")

        # Verify deletion
        stats_after = index.describe_index_stats()
        remaining = stats_after.get('total_vector_count', 0)
        if remaining == 0:
            print(f"\n✅ Pinecone reset complete! 0 vectors remaining.")
        else:
            print(f"\n⚠️  Warning: {remaining} vectors still remain")

        return True

    except Exception as e:
        print(f"\n❌ Error resetting Pinecone: {e}")
        import traceback
        traceback.print_exc()
        return False


def reset_redis_cache():
    """Clear all Redis data"""
    print("\n" + "="*70)
    print("RESETTING REDIS CACHE")
    print("="*70)

    try:
        import redis

        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

        print(f"\n[1/2] Connecting to Redis: {redis_url}")
        r = redis.from_url(redis_url)

        # Get key count before flush
        key_count = r.dbsize()
        print(f"✓ Connected. Current keys: {key_count:,}")

        if key_count > 0:
            print(f"\n[2/2] Flushing {key_count:,} keys...")
            r.flushdb()
            print("✓ All keys deleted")
        else:
            print("\n[2/2] No keys to delete")

        # Verify
        remaining = r.dbsize()
        if remaining == 0:
            print(f"\n✅ Redis reset complete! 0 keys remaining.")
        else:
            print(f"\n⚠️  Warning: {remaining} keys still remain")

        return True

    except Exception as e:
        print(f"\n❌ Error resetting Redis: {e}")
        print("(Redis may not be running locally - this is OK for cloud deployments)")
        return True  # Don't fail if Redis isn't available


def main():
    """Run complete reset"""
    print("\n" + "="*70)
    print("🔥 DATABASE RESET SCRIPT")
    print("="*70)
    print("\n⚠️  WARNING: This will DELETE ALL DATA!")
    print("   - PostgreSQL database (all tables)")
    print("   - Pinecone vectors (all embeddings)")
    print("   - Redis cache (all keys)")
    print("\n" + "="*70)

    # Confirmation (skip if --force flag provided)
    if '--force' not in sys.argv:
        response = input("\nType 'DELETE EVERYTHING' to continue: ")
        if response != 'DELETE EVERYTHING':
            print("\n❌ Reset cancelled.")
            return

    # Reset all stores
    results = []

    results.append(("PostgreSQL", reset_postgresql_database()))
    results.append(("Pinecone", reset_pinecone_index()))
    results.append(("Redis", reset_redis_cache()))

    # Summary
    print("\n" + "="*70)
    print("RESET SUMMARY")
    print("="*70)
    for name, success in results:
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"{name}: {status}")

    if all(success for _, success in results):
        print("\n✅ ALL RESETS COMPLETE!")
        print("\nNext steps:")
        print("  1. Run: python scripts/seed_database.py")
        print("  2. Log in with test accounts")
    else:
        print("\n⚠️  Some resets failed. Check errors above.")


if __name__ == '__main__':
    main()
