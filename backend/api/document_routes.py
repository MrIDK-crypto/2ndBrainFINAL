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

# Import S3 service
try:
    from services.s3_service import get_s3_service
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False
    print("⚠ S3 service not available - files will not be uploaded to cloud storage")


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
# MANUAL DOCUMENT UPLOAD
# ============================================================================

@document_bp.route('/upload', methods=['POST'])
@require_auth
def upload_documents():
    """
    Manually upload documents (files or pasted text).

    Request body (multipart/form-data for files):
    - files: File uploads (PDF, DOCX, TXT, etc.)

    Request body (JSON for text):
    {
        "title": "Document Title",
        "content": "Document text content...",
        "classification": "work" | "personal" | "spam" | "unknown"  // Optional
    }

    Response:
    {
        "success": true,
        "documents": [
            {
                "id": "...",
                "title": "...",
                "status": "pending" | "classified"
            }
        ]
    }
    """
    try:
        db = get_db()
        documents_created = []

        try:
            # Check if this is a file upload or text paste
            if request.content_type and 'multipart/form-data' in request.content_type:
                # Handle file uploads
                files = request.files.getlist('files')
                if not files:
                    return jsonify({
                        "success": False,
                        "error": "No files provided"
                    }), 400

                # Import parsers
                from parsers.document_parser import DocumentParser
                parser = DocumentParser()

                parsing_errors = []  # Track errors for better feedback

                for file in files:
                    if file.filename == '':
                        continue

                    # Read file content
                    file_content = file.read()
                    file.seek(0)  # Reset for potential re-reading

                    # Parse based on file type
                    filename = file.filename
                    lower_name = filename.lower()

                    try:
                        print(f"[Upload] Processing file: {filename} ({len(file_content)} bytes)")

                        if lower_name.endswith('.pdf'):
                            print(f"[Upload] Parsing PDF: {filename}")
                            text = parser.parse_pdf_bytes(file_content)
                        elif lower_name.endswith(('.docx', '.doc')):
                            print(f"[Upload] Parsing Word doc: {filename}")
                            text = parser.parse_word_bytes(file_content)
                        elif lower_name.endswith('.txt'):
                            print(f"[Upload] Parsing text file: {filename}")
                            text = file_content.decode('utf-8')
                        else:
                            # Try to decode as text
                            try:
                                print(f"[Upload] Attempting to decode as text: {filename}")
                                text = file_content.decode('utf-8')
                            except Exception as decode_err:
                                error_msg = f"Unsupported file type or encoding: {filename}"
                                print(f"[Upload] {error_msg}: {decode_err}")
                                parsing_errors.append(error_msg)
                                continue

                        print(f"[Upload] Extracted text length: {len(text) if text else 0}")

                        if not text or len(text.strip()) < 50:
                            error_msg = f"File content too short (< 50 chars): {filename}"
                            print(f"[Upload] {error_msg}")
                            parsing_errors.append(error_msg)
                            continue

                        # Upload original file to S3 if available
                        file_url = None
                        if S3_AVAILABLE:
                            try:
                                s3_service = get_s3_service()
                                s3_key = s3_service.generate_s3_key(
                                    tenant_id=g.tenant_id,
                                    file_type='documents',
                                    filename=filename
                                )
                                file_url, s3_error = s3_service.upload_bytes(
                                    file_bytes=file_content,
                                    s3_key=s3_key,
                                    content_type=file.content_type
                                )
                                if file_url:
                                    print(f"[Upload] File uploaded to S3: {file_url}")
                                else:
                                    print(f"[Upload] S3 upload failed: {s3_error}")
                            except Exception as e:
                                print(f"[Upload] S3 error: {e}")

                        # Create document
                        metadata = {
                            'filename': filename,
                            'uploaded_by': g.user_id,
                            'file_size': len(file_content)
                        }
                        if file_url:
                            metadata['file_url'] = file_url

                        doc = Document(
                            tenant_id=g.tenant_id,
                            title=filename,
                            content=text,
                            source_type='manual_upload',
                            classification=DocumentClassification.UNKNOWN,
                            status=DocumentStatus.PENDING,
                            doc_metadata=metadata
                        )
                        db.add(doc)
                        db.flush()

                        documents_created.append({
                            'id': doc.id,
                            'title': doc.title,
                            'status': doc.status.value
                        })

                    except Exception as e:
                        error_msg = f"Failed to parse {filename}: {str(e)}"
                        print(f"[Upload] {error_msg}")
                        import traceback
                        traceback.print_exc()
                        parsing_errors.append(error_msg)
                        continue

            else:
                # Handle text paste
                data = request.get_json()
                if not data:
                    return jsonify({
                        "success": False,
                        "error": "No data provided"
                    }), 400

                title = data.get('title', '').strip()
                content = data.get('content', '').strip()
                classification = data.get('classification', 'unknown').lower()

                if not title or not content:
                    return jsonify({
                        "success": False,
                        "error": "Title and content are required"
                    }), 400

                if len(content) < 50:
                    return jsonify({
                        "success": False,
                        "error": "Content is too short (minimum 50 characters)"
                    }), 400

                # Map classification
                class_map = {
                    'work': DocumentClassification.WORK,
                    'personal': DocumentClassification.PERSONAL,
                    'spam': DocumentClassification.SPAM,
                    'unknown': DocumentClassification.UNKNOWN
                }
                class_enum = class_map.get(classification, DocumentClassification.UNKNOWN)

                # Create document
                doc = Document(
                    tenant_id=g.tenant_id,
                    title=title,
                    content=content,
                    source_type='manual_paste',
                    classification=class_enum,
                    status=DocumentStatus.PENDING if class_enum == DocumentClassification.UNKNOWN else DocumentStatus.CONFIRMED,
                    classification_confidence=1.0 if class_enum != DocumentClassification.UNKNOWN else None,
                    doc_metadata={
                        'uploaded_by': g.user_id,
                        'word_count': len(content.split())
                    }
                )
                db.add(doc)
                db.flush()

                documents_created.append({
                    'id': doc.id,
                    'title': doc.title,
                    'status': doc.status.value
                })

            if not documents_created:
                error_detail = "No valid documents were created."
                if parsing_errors:
                    error_detail += " Errors: " + "; ".join(parsing_errors[:3])  # Show first 3 errors
                return jsonify({
                    "success": False,
                    "error": error_detail,
                    "parsing_errors": parsing_errors
                }), 400

            db.commit()

            # Trigger embedding in background for all created documents
            try:
                embedding_service = get_embedding_service()
                for doc_info in documents_created:
                    doc = db.query(Document).filter(Document.id == doc_info['id']).first()
                    if doc:
                        embedding_service.embed_document(doc)
                        doc.embedded_at = utc_now()
                db.commit()
            except Exception as e:
                print(f"[Upload] Embedding error: {e}")
                # Don't fail the upload if embedding fails

            return jsonify({
                "success": True,
                "documents": documents_created,
                "count": len(documents_created)
            })

        finally:
            db.close()

    except Exception as e:
        print(f"[Upload] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@document_bp.route('/upload-url', methods=['POST'])
@require_auth
def upload_from_url():
    """
    Add documents from URL (web page or PDF).

    Request body (JSON):
    {
        "url": "https://example.com/document",
        "classification": "work" | "personal" | "spam" | "unknown"  // Optional
    }

    Response:
    {
        "success": true,
        "documents": [
            {
                "id": "...",
                "title": "...",
                "status": "pending" | "classified"
            }
        ]
    }
    """
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({
                "success": False,
                "error": "URL is required"
            }), 400

        url = data.get('url', '').strip()
        classification = data.get('classification', 'unknown').lower()

        # Validate URL
        if not url.startswith(('http://', 'https://')):
            return jsonify({
                "success": False,
                "error": "Invalid URL. Must start with http:// or https://"
            }), 400

        db = get_db()
        documents_created = []

        try:
            import requests
            from bs4 import BeautifulSoup
            from urllib.parse import urlparse
            import io

            # Fetch content from URL
            print(f"[UploadURL] Fetching content from: {url}")
            response = requests.get(url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; 2ndBrainBot/1.0)'
            })

            if response.status_code != 200:
                return jsonify({
                    "success": False,
                    "error": f"Failed to fetch URL: HTTP {response.status_code}"
                }), 400

            content_type = response.headers.get('Content-Type', '').lower()
            parsed_url = urlparse(url)
            title = parsed_url.path.split('/')[-1] or parsed_url.netloc

            # Parse content based on type
            if 'application/pdf' in content_type or url.lower().endswith('.pdf'):
                # Handle PDF
                from parsers.document_parser import DocumentParser
                parser = DocumentParser()
                try:
                    text = parser.parse_pdf_bytes(response.content)
                    if not text or len(text.strip()) < 50:
                        return jsonify({
                            "success": False,
                            "error": "PDF content is too short or empty"
                        }), 400
                except Exception as e:
                    return jsonify({
                        "success": False,
                        "error": f"Failed to parse PDF: {str(e)}"
                    }), 400

            elif 'text/html' in content_type:
                # Handle HTML page
                soup = BeautifulSoup(response.text, 'html.parser')

                # Extract title
                title_tag = soup.find('title')
                if title_tag:
                    title = title_tag.get_text().strip()

                # Remove script and style
                for script in soup(['script', 'style']):
                    script.decompose()

                # Extract text
                main_content = (
                    soup.find('main') or
                    soup.find('article') or
                    soup.find('body') or
                    soup
                )
                text = main_content.get_text(separator='\n', strip=True)

                # Clean up
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                text = '\n\n'.join(lines)

                if not text or len(text.strip()) < 50:
                    return jsonify({
                        "success": False,
                        "error": "Page content is too short or empty"
                    }), 400

            else:
                return jsonify({
                    "success": False,
                    "error": f"Unsupported content type: {content_type}. Only HTML and PDF are supported."
                }), 400

            # Map classification
            class_map = {
                'work': DocumentClassification.WORK,
                'personal': DocumentClassification.PERSONAL,
                'spam': DocumentClassification.SPAM,
                'unknown': DocumentClassification.UNKNOWN
            }
            class_enum = class_map.get(classification, DocumentClassification.UNKNOWN)

            # Create document
            doc = Document(
                tenant_id=g.tenant_id,
                title=title,
                content=text,
                source_type='manual_url',
                source_url=url,
                classification=class_enum,
                status=DocumentStatus.PENDING if class_enum == DocumentClassification.UNKNOWN else DocumentStatus.CONFIRMED,
                classification_confidence=1.0 if class_enum != DocumentClassification.UNKNOWN else None,
                doc_metadata={
                    'url': url,
                    'content_type': content_type,
                    'uploaded_by': g.user_id,
                    'fetched_at': datetime.now().isoformat()
                }
            )
            db.add(doc)
            db.commit()

            documents_created.append({
                'id': doc.id,
                'title': doc.title,
                'status': doc.status.value
            })

            # Trigger embedding in background
            try:
                from services.embedding_service import get_embedding_service
                embedding_service = get_embedding_service()
                embed_result = embedding_service.embed_documents(
                    documents=[doc],
                    tenant_id=g.tenant_id,
                    db=db,
                    force_reembed=False
                )
                print(f"[UploadURL] Embedding result: {embed_result}")
            except Exception as embed_error:
                print(f"[UploadURL] Embedding error (non-fatal): {embed_error}")

            return jsonify({
                "success": True,
                "documents": documents_created,
                "count": len(documents_created)
            })

        finally:
            db.close()

    except requests.exceptions.Timeout:
        return jsonify({
            "success": False,
            "error": "Request timed out. The URL may be slow or unavailable."
        }), 500
    except requests.exceptions.ConnectionError:
        return jsonify({
            "success": False,
            "error": "Failed to connect to the URL. Please check the URL and try again."
        }), 500
    except Exception as e:
        print(f"[UploadURL] Error: {e}")
        import traceback
        traceback.print_exc()
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


@document_bp.route('/<document_id>/classify', methods=['PUT'])
@require_auth
def manually_classify_document(document_id: str):
    """
    Manually set document classification (no AI, direct override).

    Request body:
    {
        "classification": "work" | "personal" | "spam" | "unknown"
    }
    """
    try:
        data = request.get_json()
        classification = data.get('classification', '').lower()

        valid_classifications = ['work', 'personal', 'spam', 'unknown']
        if classification not in valid_classifications:
            return jsonify({
                "success": False,
                "error": f"Invalid classification. Must be one of: {', '.join(valid_classifications)}"
            }), 400

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

            # Update classification
            from database.models import DocumentClassification, DocumentStatus
            if classification == 'work':
                document.classification = DocumentClassification.WORK
            elif classification == 'personal':
                document.classification = DocumentClassification.PERSONAL
            elif classification == 'spam':
                document.classification = DocumentClassification.SPAM
            else:
                document.classification = DocumentClassification.UNKNOWN

            document.classification_confidence = 1.0  # Manual = 100% confidence
            document.classification_reason = "Manually classified by user"
            document.status = DocumentStatus.CONFIRMED
            document.updated_at = utc_now()

            db.commit()

            return jsonify({
                "success": True,
                "document": {
                    "id": document.id,
                    "classification": document.classification.value
                }
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@document_bp.route('/bulk/classify', methods=['POST'])
@require_auth
def bulk_classify_documents():
    """
    Manually classify multiple documents at once.

    Request body:
    {
        "document_ids": ["id1", "id2", ...],
        "classification": "work" | "personal" | "spam" | "unknown"
    }
    """
    try:
        data = request.get_json()
        document_ids = data.get('document_ids', [])
        classification = data.get('classification', '').lower()

        if not document_ids:
            return jsonify({
                "success": False,
                "error": "No document IDs provided"
            }), 400

        valid_classifications = ['work', 'personal', 'spam', 'unknown']
        if classification not in valid_classifications:
            return jsonify({
                "success": False,
                "error": f"Invalid classification. Must be one of: {', '.join(valid_classifications)}"
            }), 400

        db = get_db()
        try:
            # Map classification string to enum
            from database.models import DocumentClassification, DocumentStatus
            if classification == 'work':
                class_enum = DocumentClassification.WORK
            elif classification == 'personal':
                class_enum = DocumentClassification.PERSONAL
            elif classification == 'spam':
                class_enum = DocumentClassification.SPAM
            else:
                class_enum = DocumentClassification.UNKNOWN

            # Update all documents
            updated_count = db.query(Document).filter(
                Document.id.in_(document_ids),
                Document.tenant_id == g.tenant_id
            ).update({
                'classification': class_enum,
                'classification_confidence': 1.0,
                'classification_reason': 'Bulk classified by user',
                'status': DocumentStatus.CONFIRMED,
                'updated_at': utc_now()
            }, synchronize_session=False)

            db.commit()

            return jsonify({
                "success": True,
                "updated_count": updated_count,
                "classification": classification
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


@document_bp.route('/debug/tenant-info', methods=['GET'])
@require_auth
def get_tenant_debug_info():
    """
    Debug endpoint to see current tenant info and document counts.

    Response:
    {
        "success": true,
        "debug": {
            "current_tenant_id": "...",
            "current_user_id": "...",
            "current_email": "...",
            "documents_for_this_tenant": 0,
            "all_tenants_with_documents": [
                {"tenant_id": "xxx", "count": 80},
                ...
            ],
            "all_users": [
                {"email": "demo@test.com", "tenant_id": "xxx", "has_documents": true},
                ...
            ]
        }
    }
    """
    try:
        db = get_db()
        try:
            from sqlalchemy import func
            from database.models import User, Tenant

            # Current user's document count
            my_doc_count = db.query(Document).filter(
                Document.tenant_id == g.tenant_id,
                Document.is_deleted == False
            ).count()

            # All tenants with documents
            all_tenants = db.query(
                Document.tenant_id,
                func.count(Document.id).label('count')
            ).filter(
                Document.is_deleted == False
            ).group_by(Document.tenant_id).all()

            # Get all users with their tenant info
            users_data = []
            users = db.query(User).all()
            for user in users:
                tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
                doc_count = db.query(Document).filter(
                    Document.tenant_id == user.tenant_id,
                    Document.is_deleted == False
                ).count()

                users_data.append({
                    "email": user.email,
                    "full_name": user.full_name,
                    "tenant_id": user.tenant_id[:16] + "..." if len(user.tenant_id) > 16 else user.tenant_id,
                    "tenant_name": tenant.name if tenant else "Unknown",
                    "document_count": doc_count,
                    "is_current_user": user.id == g.user_id
                })

            return jsonify({
                "success": True,
                "debug": {
                    "current_tenant_id": g.tenant_id,
                    "current_user_id": g.user_id,
                    "current_email": g.email,
                    "documents_for_this_tenant": my_doc_count,
                    "all_tenants_with_documents": [
                        {
                            "tenant_id": tenant_id[:16] + "..." if len(tenant_id) > 16 else tenant_id,
                            "count": count
                        }
                        for tenant_id, count in all_tenants
                    ],
                    "all_users": users_data,
                    "suggestion": "Login with an account that has documents, or use /api/documents/migrate to move documents to your current account"
                }
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@document_bp.route('/migrate', methods=['POST'])
@require_auth
def migrate_documents_to_current_tenant():
    """
    Migrate all documents from another tenant to the current user's tenant.
    Useful when documents were created under wrong account.

    Request body:
    {
        "from_email": "other-user@example.com"  // Email of user whose documents to migrate
    }

    Response:
    {
        "success": true,
        "migrated_count": 80,
        "from_tenant": "xxx",
        "to_tenant": "yyy"
    }
    """
    try:
        data = request.get_json()
        if not data or 'from_email' not in data:
            return jsonify({
                "success": False,
                "error": "from_email is required"
            }), 400

        from_email = data['from_email'].lower().strip()

        db = get_db()
        try:
            from database.models import User

            # Find the source user
            source_user = db.query(User).filter(User.email == from_email).first()
            if not source_user:
                return jsonify({
                    "success": False,
                    "error": f"User not found: {from_email}"
                }), 404

            source_tenant_id = source_user.tenant_id

            # Don't migrate if it's the same tenant
            if source_tenant_id == g.tenant_id:
                return jsonify({
                    "success": False,
                    "error": "Source and destination tenants are the same"
                }), 400

            # Count documents to migrate
            docs_to_migrate = db.query(Document).filter(
                Document.tenant_id == source_tenant_id,
                Document.is_deleted == False
            ).all()

            if not docs_to_migrate:
                return jsonify({
                    "success": True,
                    "migrated_count": 0,
                    "message": "No documents to migrate"
                })

            # Migrate documents
            migrated_count = 0
            for doc in docs_to_migrate:
                doc.tenant_id = g.tenant_id
                migrated_count += 1

            db.commit()

            print(f"[Migrate] Migrated {migrated_count} documents from {from_email} ({source_tenant_id[:8]}...) to {g.email} ({g.tenant_id[:8]}...)")

            return jsonify({
                "success": True,
                "migrated_count": migrated_count,
                "from_email": from_email,
                "from_tenant": source_tenant_id[:16] + "...",
                "to_tenant": g.tenant_id[:16] + "...",
                "to_email": g.email
            })

        finally:
            db.close()

    except Exception as e:
        import traceback
        traceback.print_exc()
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
