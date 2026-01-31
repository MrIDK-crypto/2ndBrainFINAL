#!/usr/bin/env python3
"""
Debug script to check why documents aren't showing in UI
Run this on Render to diagnose the issue
"""

from database.models import SessionLocal, Document, Connector, DocumentStatus, DocumentClassification
from sqlalchemy import func

def debug_documents():
    """Check documents in database"""
    db = SessionLocal()
    try:
        print("=" * 60)
        print("DOCUMENT DIAGNOSIS")
        print("=" * 60)

        # 1. Total documents
        total = db.query(Document).count()
        print(f"\n1. Total documents in database: {total}")

        # 2. By tenant
        by_tenant = db.query(
            Document.tenant_id,
            func.count(Document.id)
        ).group_by(Document.tenant_id).all()

        print(f"\n2. Documents by tenant:")
        for tenant_id, count in by_tenant:
            print(f"   {tenant_id[:16]}...: {count} documents")

        # 3. By status
        by_status = db.query(
            Document.status,
            func.count(Document.id)
        ).group_by(Document.status).all()

        print(f"\n3. Documents by status:")
        for status, count in by_status:
            print(f"   {status.value if status else 'None'}: {count} documents")

        # 4. By classification
        by_class = db.query(
            Document.classification,
            func.count(Document.id)
        ).group_by(Document.classification).all()

        print(f"\n4. Documents by classification:")
        for classification, count in by_class:
            print(f"   {classification.value if classification else 'None'}: {count} documents")

        # 5. By source_type
        by_source = db.query(
            Document.source_type,
            func.count(Document.id)
        ).group_by(Document.source_type).all()

        print(f"\n5. Documents by source:")
        for source, count in by_source:
            print(f"   {source or 'None'}: {count} documents")

        # 6. Deleted vs active
        deleted = db.query(Document).filter(Document.is_deleted == True).count()
        active = db.query(Document).filter(Document.is_deleted == False).count()
        print(f"\n6. Active vs Deleted:")
        print(f"   Active: {active}")
        print(f"   Deleted: {deleted}")

        # 7. Recent webscraper documents
        print(f"\n7. Recent webscraper documents (last 10):")
        recent = db.query(Document).filter(
            Document.source_type == 'webscraper'
        ).order_by(Document.created_at.desc()).limit(10).all()

        for doc in recent:
            print(f"   - {doc.title[:50]}...")
            print(f"     Status: {doc.status.value if doc.status else 'None'}")
            print(f"     Classification: {doc.classification.value if doc.classification else 'None'}")
            print(f"     Tenant: {doc.tenant_id[:16]}...")
            print(f"     Created: {doc.created_at}")
            print(f"     Deleted: {doc.is_deleted}")
            print()

        # 8. Check connectors
        print(f"\n8. Active connectors:")
        connectors = db.query(Connector).filter(Connector.is_active == True).all()
        for conn in connectors:
            print(f"   - {conn.connector_type.value}: {conn.status.value}")
            print(f"     Tenant: {conn.tenant_id[:16]}...")
            print(f"     Total synced: {conn.total_items_synced}")
            print()

        print("=" * 60)
        print("DIAGNOSIS COMPLETE")
        print("=" * 60)
        print("\nTo fix 'documents not showing' issue:")
        print("1. Check that frontend is querying the correct tenant_id")
        print("2. Check that frontend doesn't filter by status='pending'")
        print("3. Webscraper creates documents with status='classified'")
        print("4. Frontend should query all statuses or include 'classified'")
        print("\nSee FRONTEND_FIXES_NEEDED.md for detailed fixes")

    finally:
        db.close()

if __name__ == '__main__':
    debug_documents()
