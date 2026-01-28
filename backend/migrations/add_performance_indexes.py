"""
Add Performance Indexes Migration
Date: 2026-01-28

Adds 4 new indexes to Document table for faster queries:
- ix_document_sender: Speeds up sender email queries
- ix_document_embedded: Speeds up embedding status checks
- ix_document_confidence: Speeds up sorting by classification
- ix_document_created: Speeds up date-based queries
"""

from sqlalchemy import create_engine, Index, inspect
from database.config import get_database_url
from database.models import Document


def upgrade():
    """Add performance indexes"""
    engine = create_engine(get_database_url())

    # Check which indexes already exist
    inspector = inspect(engine)
    existing_indexes = {idx['name'] for idx in inspector.get_indexes('documents')}

    with engine.connect() as conn:
        # Add sender index
        if 'ix_document_sender' not in existing_indexes:
            Index(
                'ix_document_sender',
                Document.tenant_id,
                Document.sender_email
            ).create(conn)
            print("✓ Created index: ix_document_sender")
        else:
            print("⊘ Index already exists: ix_document_sender")

        # Add embedded_at index
        if 'ix_document_embedded' not in existing_indexes:
            Index(
                'ix_document_embedded',
                Document.tenant_id,
                Document.embedded_at
            ).create(conn)
            print("✓ Created index: ix_document_embedded")
        else:
            print("⊘ Index already exists: ix_document_embedded")

        # Add confidence index
        if 'ix_document_confidence' not in existing_indexes:
            Index(
                'ix_document_confidence',
                Document.classification_confidence
            ).create(conn)
            print("✓ Created index: ix_document_confidence")
        else:
            print("⊘ Index already exists: ix_document_confidence")

        # Add created_at index
        if 'ix_document_created' not in existing_indexes:
            Index(
                'ix_document_created',
                Document.tenant_id,
                Document.created_at
            ).create(conn)
            print("✓ Created index: ix_document_created")
        else:
            print("⊘ Index already exists: ix_document_created")

    print("\n✓ All performance indexes created successfully")


def downgrade():
    """Remove performance indexes"""
    engine = create_engine(get_database_url())

    with engine.connect() as conn:
        # Drop indexes in reverse order
        for idx_name in ['ix_document_created', 'ix_document_confidence',
                        'ix_document_embedded', 'ix_document_sender']:
            try:
                conn.execute(f"DROP INDEX IF EXISTS {idx_name}")
                print(f"✓ Dropped index: {idx_name}")
            except Exception as e:
                print(f"⚠ Could not drop {idx_name}: {e}")

    print("\n✓ All performance indexes removed")


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'downgrade':
        print("Running downgrade migration...")
        downgrade()
    else:
        print("Running upgrade migration...")
        upgrade()
