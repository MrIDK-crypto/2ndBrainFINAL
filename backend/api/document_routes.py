"""
Document API Routes
REST endpoints for document management and classification.
"""

from flask import Blueprint, request, jsonify, g
from sqlalchemy.orm import Session

from database.models import (
    SessionLocal, Document, Connector, DeletedDocument,
    DocumentStatus, DocumentClassification,
    utc_now
)
from services.auth_service import require_auth
from services.classification_service import ClassificationService
from services.embedding_service import get_embedding_service


# Create blueprint
document_bp = Blueprint('documents', __name__, url_prefix='/api/documents')


def get_db():
    """Get database session"""
    return SessionLocal()


# ============================================================================
# LIST DOCUMENTS
# ============================================================================

@document_bp.route('', methods=['GET'])
@require_auth
def list_documents():
    """
    List documents with filtering and pagination.

    Query params:
        status: pending, classified, confirmed, rejected
        classification: work, personal, spam, unknown
        needs_review: true/false - only show documents needing review
        search: search in title/content
        source_type: email, message, file
        limit: page size (default 50)
        offset: page offset (default 0)
        sort: field to sort by (created_at, classification_confidence)
        order: asc or desc

    Response:
    {
        "success": true,
        "documents": [...],
        "pagination": {
            "total": 150,
            "limit": 50,
            "offset": 0,
            "has_more": true
        }
    }
    """
    try:
        db = get_db()
        try:
            # Parse query params
            status = request.args.get('status')
            classification = request.args.get('classification')
            needs_review = request.args.get('needs_review', '').lower() == 'true'
            search = request.args.get('search', '').strip()
            source_type = request.args.get('source_type')
            limit = min(int(request.args.get('limit', 50)), 200)
            offset = int(request.args.get('offset', 0))
            sort = request.args.get('sort', 'created_at')
            order = request.args.get('order', 'desc')

            # Build query
            query = db.query(Document).filter(
                Document.tenant_id == g.tenant_id,
                Document.is_deleted == False
            )

            # Apply filters
            if status:
                status_map = {
                    'pending': DocumentStatus.PENDING,
                    'classified': DocumentStatus.CLASSIFIED,
                    'confirmed': DocumentStatus.CONFIRMED,
                    'rejected': DocumentStatus.REJECTED,
                    'archived': DocumentStatus.ARCHIVED
                }
                if status in status_map:
                    query = query.filter(Document.status == status_map[status])

            if classification:
                class_map = {
                    'work': DocumentClassification.WORK,
                    'personal': DocumentClassification.PERSONAL,
                    'spam': DocumentClassification.SPAM,
                    'unknown': DocumentClassification.UNKNOWN
                }
                if classification in class_map:
                    query = query.filter(Document.classification == class_map[classification])

            if needs_review:
                query = query.filter(
                    Document.status == DocumentStatus.CLASSIFIED,
                    Document.user_confirmed == False
                )

            if search:
                search_pattern = f"%{search}%"
                query = query.filter(
                    db.or_(
                        Document.title.ilike(search_pattern),
                        Document.content.ilike(search_pattern),
                        Document.sender.ilike(search_pattern)
                    )
                )

            if source_type:
                query = query.filter(Document.source_type == source_type)

            # Get total count
            total = query.count()

            # Apply sorting
            sort_column = getattr(Document, sort, Document.created_at)
            if order == 'asc':
                query = query.order_by(sort_column.asc())
            else:
                query = query.order_by(sort_column.desc())

            # Apply pagination
            documents = query.offset(offset).limit(limit).all()

            return jsonify({
                "success": True,
                "documents": [doc.to_dict() for doc in documents],
                "pagination": {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "has_more": offset + limit < total
                }
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# GET SINGLE DOCUMENT
# ============================================================================

@document_bp.route('/<document_id>', methods=['GET'])
@require_auth
def get_document(document_id: str):
    """
    Get a single document by ID.

    Response:
    {
        "success": true,
        "document": { ... }
    }
    """
    try:
        db = get_db()
        try:
            document = db.query(Document).filter(
                Document.id == document_id,
                Document.tenant_id == g.tenant_id
            ).first()

            if not document:
                return jsonify({
                    "success": False,
                    "error": "Document not found"
                }), 404

            return jsonify({
                "success": True,
                "document": document.to_dict(include_content=True)
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# CLASSIFICATION
# ============================================================================

@document_bp.route('/classify', methods=['POST'])
@require_auth
def classify_documents():
    """
    Trigger classification for pending documents.

    Request body (optional):
    {
        "document_ids": ["id1", "id2"],  // Specific documents (optional)
        "limit": 50,  // Max documents to process
        "auto_confirm_threshold": 0.9  // Auto-confirm if confidence >= this
    }

    Response:
    {
        "success": true,
        "results": {
            "total": 50,
            "work": 30,
            "personal": 15,
            "spam": 3,
            "unknown": 2,
            "auto_confirmed": 25,
            "needs_review": 10
        }
    }
    """
    try:
        data = request.get_json() or {}
        document_ids = data.get('document_ids')
        limit = min(data.get('limit', 50), 200)
        auto_confirm_threshold = data.get('auto_confirm_threshold')

        db = get_db()
        try:
            service = ClassificationService(db)

            if document_ids:
                # Classify specific documents
                results = {
                    "total": 0,
                    "work": 0,
                    "personal": 0,
                    "spam": 0,
                    "unknown": 0,
                    "auto_confirmed": 0,
                    "needs_review": 0,
                    "errors": []
                }

                for doc_id in document_ids:
                    document = db.query(Document).filter(
                        Document.id == doc_id,
                        Document.tenant_id == g.tenant_id
                    ).first()

                    if document:
                        classification_result = service.classify_document(document)

                        document.classification = classification_result.classification
                        document.classification_confidence = classification_result.confidence
                        document.classification_reason = classification_result.reason
                        document.status = DocumentStatus.CLASSIFIED
                        document.updated_at = utc_now()

                        results["total"] += 1

                        if classification_result.classification == DocumentClassification.WORK:
                            results["work"] += 1
                        elif classification_result.classification == DocumentClassification.PERSONAL:
                            results["personal"] += 1
                        elif classification_result.classification == DocumentClassification.SPAM:
                            results["spam"] += 1
                        else:
                            results["unknown"] += 1

                        if (
                            auto_confirm_threshold and
                            classification_result.confidence >= auto_confirm_threshold and
                            not classification_result.is_borderline
                        ):
                            document.user_confirmed = True
                            document.user_confirmed_at = utc_now()
                            document.status = DocumentStatus.CONFIRMED
                            results["auto_confirmed"] += 1
                        elif classification_result.is_borderline:
                            results["needs_review"] += 1

                db.commit()

            else:
                # Classify all pending documents
                results = service.classify_pending_documents(
                    tenant_id=g.tenant_id,
                    limit=limit,
                    auto_confirm_threshold=auto_confirm_threshold
                )

            return jsonify({
                "success": True,
                "results": results
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@document_bp.route('/<document_id>/classify', methods=['POST'])
@require_auth
def classify_single_document(document_id: str):
    """
    Classify a single document.

    Response:
    {
        "success": true,
        "document": { ... },
        "classification": {
            "classification": "work",
            "confidence": 0.95,
            "reason": "...",
            "key_indicators": [...],
            "is_borderline": false
        }
    }
    """
    try:
        db = get_db()
        try:
            document = db.query(Document).filter(
                Document.id == document_id,
                Document.tenant_id == g.tenant_id
            ).first()

            if not document:
                return jsonify({
                    "success": False,
                    "error": "Document not found"
                }), 404

            service = ClassificationService(db)
            result = service.classify_document(document)

            # Update document
            document.classification = result.classification
            document.classification_confidence = result.confidence
            document.classification_reason = result.reason
            document.status = DocumentStatus.CLASSIFIED
            document.updated_at = utc_now()

            db.commit()

            return jsonify({
                "success": True,
                "document": document.to_dict(),
                "classification": {
                    "classification": result.classification.value,
                    "confidence": result.confidence,
                    "reason": result.reason,
                    "key_indicators": result.key_indicators,
                    "is_borderline": result.is_borderline
                }
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# CONFIRMATION
# ============================================================================

@document_bp.route('/<document_id>/confirm', methods=['POST'])
@require_auth
def confirm_document(document_id: str):
    """
    Confirm document classification.

    Request body (optional):
    {
        "classification": "work" | "personal" | "spam"  // Override classification
    }

    Response:
    {
        "success": true,
        "document": { ... }
    }
    """
    try:
        data = request.get_json() or {}
        override_classification = data.get('classification')

        classification = None
        if override_classification:
            class_map = {
                'work': DocumentClassification.WORK,
                'personal': DocumentClassification.PERSONAL,
                'spam': DocumentClassification.SPAM
            }
            classification = class_map.get(override_classification.lower())

        db = get_db()
        try:
            service = ClassificationService(db)
            success, error = service.confirm_classification(
                document_id=document_id,
                tenant_id=g.tenant_id,
                confirmed_classification=classification
            )

            if not success:
                return jsonify({
                    "success": False,
                    "error": error
                }), 400

            # Get updated document
            document = db.query(Document).filter(
                Document.id == document_id
            ).first()

            return jsonify({
                "success": True,
                "document": document.to_dict() if document else None
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@document_bp.route('/<document_id>/reject', methods=['POST'])
@require_auth
def reject_document(document_id: str):
    """
    Reject document (mark as personal/excluded from knowledge base).

    Request body (optional):
    {
        "reason": "This is personal correspondence"
    }

    Response:
    {
        "success": true
    }
    """
    try:
        data = request.get_json() or {}
        reason = data.get('reason')

        db = get_db()
        try:
            service = ClassificationService(db)
            success, error = service.reject_document(
                document_id=document_id,
                tenant_id=g.tenant_id,
                reason=reason
            )

            if not success:
                return jsonify({
                    "success": False,
                    "error": error
                }), 400

            return jsonify({"success": True})

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# BULK OPERATIONS
# ============================================================================

@document_bp.route('/bulk/confirm', methods=['POST'])
@require_auth
def bulk_confirm():
    """
    Bulk confirm multiple documents.

    Request body:
    {
        "document_ids": ["id1", "id2", ...],
        "classification": "work"  // Optional override for all
    }

    Response:
    {
        "success": true,
        "results": {
            "confirmed": 10,
            "not_found": 0,
            "errors": []
        }
    }
    """
    try:
        data = request.get_json()

        if not data or not data.get('document_ids'):
            return jsonify({
                "success": False,
                "error": "document_ids required"
            }), 400

        document_ids = data['document_ids']
        override_classification = data.get('classification')

        classification = None
        if override_classification:
            class_map = {
                'work': DocumentClassification.WORK,
                'personal': DocumentClassification.PERSONAL,
                'spam': DocumentClassification.SPAM
            }
            classification = class_map.get(override_classification.lower())

        db = get_db()
        try:
            service = ClassificationService(db)
            results = service.bulk_confirm(
                document_ids=document_ids,
                tenant_id=g.tenant_id,
                classification=classification
            )

            return jsonify({
                "success": True,
                "results": results
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@document_bp.route('/bulk/reject', methods=['POST'])
@require_auth
def bulk_reject():
    """
    Bulk reject multiple documents.

    Request body:
    {
        "document_ids": ["id1", "id2", ...]
    }

    Response:
    {
        "success": true,
        "results": {
            "rejected": 10,
            "not_found": 0,
            "errors": []
        }
    }
    """
    try:
        data = request.get_json()

        if not data or not data.get('document_ids'):
            return jsonify({
                "success": False,
                "error": "document_ids required"
            }), 400

        db = get_db()
        try:
            service = ClassificationService(db)
            results = service.bulk_reject(
                document_ids=data['document_ids'],
                tenant_id=g.tenant_id
            )

            return jsonify({
                "success": True,
                "results": results
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# STATISTICS
# ============================================================================

@document_bp.route('/stats', methods=['GET'])
@require_auth
def get_document_stats():
    """
    Get document classification statistics.

    Response:
    {
        "success": true,
        "stats": {
            "by_status": { "pending": 10, "classified": 50, ... },
            "by_classification": { "work": 40, "personal": 20, ... },
            "needs_review": 15,
            "average_confidence": 0.87,
            "total_documents": 100
        }
    }
    """
    try:
        db = get_db()
        try:
            service = ClassificationService(db)
            stats = service.get_classification_stats(g.tenant_id)

            return jsonify({
                "success": True,
                "stats": stats
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# FOR REVIEW
# ============================================================================

@document_bp.route('/review', methods=['GET'])
@require_auth
def get_documents_for_review():
    """
    Get documents that need user review.

    Query params:
        classification: filter by classification
        limit: page size (default 20)
        offset: page offset

    Response:
    {
        "success": true,
        "documents": [...],
        "pagination": { ... }
    }
    """
    try:
        classification = request.args.get('classification')
        limit = min(int(request.args.get('limit', 20)), 100)
        offset = int(request.args.get('offset', 0))

        classification_filter = None
        if classification:
            class_map = {
                'work': DocumentClassification.WORK,
                'personal': DocumentClassification.PERSONAL,
                'spam': DocumentClassification.SPAM
            }
            classification_filter = class_map.get(classification.lower())

        db = get_db()
        try:
            service = ClassificationService(db)
            documents, total = service.get_documents_for_review(
                tenant_id=g.tenant_id,
                classification_filter=classification_filter,
                limit=limit,
                offset=offset
            )

            return jsonify({
                "success": True,
                "documents": [doc.to_dict() for doc in documents],
                "pagination": {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "has_more": offset + limit < total
                }
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# DELETE
# ============================================================================

@document_bp.route('/<document_id>', methods=['DELETE'])
@require_auth
def delete_document(document_id: str):
    """
    Delete a document (soft or hard delete).

    Query params:
        hard: true/false - if true, permanently removes from database

    Response:
    {
        "success": true
    }
    """
    try:
        hard_delete = request.args.get('hard', '').lower() == 'true'

        db = get_db()
        try:
            document = db.query(Document).filter(
                Document.id == document_id,
                Document.tenant_id == g.tenant_id
            ).first()

            if not document:
                return jsonify({
                    "success": False,
                    "error": "Document not found"
                }), 404

            embeddings_deleted = 0

            if hard_delete:
                # Delete embeddings from Pinecone FIRST (before database deletion)
                try:
                    from services.embedding_service import get_embedding_service
                    embedding_service = get_embedding_service()
                    embed_result = embedding_service.delete_document_embeddings(
                        document_ids=[str(document.id)],
                        tenant_id=g.tenant_id,
                        db=db
                    )
                    if embed_result.get('success'):
                        embeddings_deleted = embed_result.get('deleted', 0)
                        print(f"[delete_document] Deleted {embeddings_deleted} embeddings from Pinecone for doc {document_id}")
                    else:
                        print(f"[delete_document] Warning: Failed to delete embeddings: {embed_result.get('error')}")
                except Exception as embed_error:
                    print(f"[delete_document] Error deleting embeddings: {embed_error}")
                    # Continue with database deletion even if Pinecone fails

                # Track external_id if present (to prevent re-syncing)
                if document.external_id and document.connector_id:
                    from database.models import DeletedDocument
                    deleted_doc_record = DeletedDocument(
                        tenant_id=g.tenant_id,
                        connector_id=document.connector_id,
                        external_id=document.external_id,
                        title=document.title
                    )
                    db.add(deleted_doc_record)

                # Permanently remove from database
                db.delete(document)
            else:
                # Soft delete - also delete embeddings so AI doesn't use them
                try:
                    from services.embedding_service import get_embedding_service
                    embedding_service = get_embedding_service()
                    embed_result = embedding_service.delete_document_embeddings(
                        document_ids=[str(document.id)],
                        tenant_id=g.tenant_id,
                        db=db
                    )
                    if embed_result.get('success'):
                        embeddings_deleted = embed_result.get('deleted', 0)
                except Exception as embed_error:
                    print(f"[delete_document] Error deleting embeddings on soft delete: {embed_error}")

                document.is_deleted = True
                document.deleted_at = utc_now()

            db.commit()

            return jsonify({
                "success": True,
                "hard_deleted": hard_delete,
                "embeddings_deleted": embeddings_deleted
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@document_bp.route('/bulk/delete', methods=['POST'])
@require_auth
def bulk_delete():
    """
    Bulk delete documents (soft or hard delete).

    Request body:
    {
        "document_ids": ["id1", "id2", ...],
        "hard": false  // If true, permanently removes from database, Pinecone, AND tracks external_id
    }

    Response:
    {
        "success": true,
        "results": {
            "deleted": 10,
            "not_found": 0,
            "tracked": 5,
            "embeddings_deleted": 10
        }
    }
    """
    import traceback

    try:
        data = request.get_json()

        if not data or not data.get('document_ids'):
            return jsonify({
                "success": False,
                "error": "document_ids required"
            }), 400

        document_ids = data['document_ids']
        hard_delete = data.get('hard', False)

        db = get_db()
        try:
            results = {"deleted": 0, "not_found": 0, "tracked": 0, "embeddings_deleted": 0, "errors": []}

            # For hard delete, first delete embeddings from Pinecone
            if hard_delete:
                # Get all valid document IDs for this tenant
                valid_doc_ids = []
                for doc_id in document_ids:
                    document = db.query(Document).filter(
                        Document.id == doc_id,
                        Document.tenant_id == g.tenant_id
                    ).first()
                    if document:
                        valid_doc_ids.append(doc_id)

                # Delete from Pinecone FIRST (before database deletion)
                if valid_doc_ids:
                    try:
                        embedding_service = get_embedding_service()
                        embed_result = embedding_service.delete_document_embeddings(
                            document_ids=valid_doc_ids,
                            tenant_id=g.tenant_id,
                            db=db
                        )
                        if embed_result.get('success'):
                            results["embeddings_deleted"] = embed_result.get('deleted', 0)
                            print(f"[bulk_delete] Deleted {results['embeddings_deleted']} embeddings from Pinecone")
                        else:
                            print(f"[bulk_delete] Warning: Failed to delete some embeddings: {embed_result.get('error')}")
                    except Exception as embed_error:
                        print(f"[bulk_delete] Error deleting embeddings: {embed_error}")
                        # Continue with database deletion even if Pinecone fails
                        results["errors"].append({"type": "embedding", "error": str(embed_error)})

            # Now delete from database
            for doc_id in document_ids:
                try:
                    document = db.query(Document).filter(
                        Document.id == doc_id,
                        Document.tenant_id == g.tenant_id
                    ).first()

                    if document:
                        if hard_delete:
                            # Track the external_id to prevent re-sync (only if document has external_id)
                            if document.external_id and document.connector_id:
                                # Check if already tracked (use document's tenant_id for consistency)
                                existing = db.query(DeletedDocument).filter(
                                    DeletedDocument.tenant_id == document.tenant_id,
                                    DeletedDocument.connector_id == document.connector_id,
                                    DeletedDocument.external_id == document.external_id
                                ).first()

                                if not existing:
                                    try:
                                        deleted_record = DeletedDocument(
                                            tenant_id=document.tenant_id,
                                            connector_id=document.connector_id,
                                            external_id=document.external_id,
                                            source_type=document.source_type,
                                            original_title=document.title,
                                            deleted_by=g.user_id
                                        )
                                        db.add(deleted_record)
                                        db.flush()  # Try to insert now to catch constraint errors
                                        results["tracked"] += 1
                                    except Exception as track_error:
                                        # Already tracked (race condition or previous delete) - that's fine
                                        print(f"External ID already tracked: {document.external_id}")
                                        db.rollback()
                                        # Re-query the document since we rolled back
                                        document = db.query(Document).filter(
                                            Document.id == doc_id,
                                            Document.tenant_id == g.tenant_id
                                        ).first()
                                        if not document:
                                            results["not_found"] += 1
                                            continue

                            # Delete document from database (cascade will delete chunks)
                            db.delete(document)
                        else:
                            document.is_deleted = True
                            document.deleted_at = utc_now()
                        results["deleted"] += 1
                    else:
                        results["not_found"] += 1
                except Exception as doc_error:
                    print(f"Error deleting document {doc_id}: {doc_error}")
                    traceback.print_exc()
                    results["errors"].append({"id": doc_id, "error": str(doc_error)})

            db.commit()

            return jsonify({
                "success": True,
                "results": results,
                "hard_deleted": hard_delete
            })

        except Exception as inner_error:
            print(f"Inner error in bulk_delete: {inner_error}")
            traceback.print_exc()
            db.rollback()
            raise
        finally:
            db.close()

    except Exception as e:
        print(f"Error in bulk_delete: {e}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# GET SINGLE DOCUMENT
# ============================================================================

@document_bp.route('/<document_id>', methods=['GET'])
@require_auth
def get_document(document_id):
    """
    Get a single document by ID with full content.

    Response:
    {
        "success": true,
        "document": {
            "id": "...",
            "title": "...",
            "content": "...",
            "content_html": "...",
            "classification": "work",
            "source_type": "email",
            ...
        }
    }
    """
    try:
        db = get_db()
        try:
            # Get document
            doc = db.query(Document).filter(
                Document.id == document_id,
                Document.tenant_id == g.tenant_id,
                Document.is_deleted == False
            ).first()

            if not doc:
                return jsonify({
                    "success": False,
                    "error": "Document not found"
                }), 404

            return jsonify({
                "success": True,
                "document": doc.to_dict(include_content=True)
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@document_bp.route('/all', methods=['DELETE'])
@require_auth
def delete_all_documents():
    """
    Delete ALL documents for current tenant (hard delete).
    Use with caution!

    Response:
    {
        "success": true,
        "deleted_count": 100
    }
    """
    try:
        db = get_db()
        try:
            deleted_count = db.query(Document).filter(
                Document.tenant_id == g.tenant_id
            ).delete()

            db.commit()

            return jsonify({
                "success": True,
                "deleted_count": deleted_count
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
