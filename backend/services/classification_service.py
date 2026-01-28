"""
Document Classification Service
AI-powered classification of documents as work/personal with user confirmation flow.
"""

import os
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from database.models import (
    Document, Connector, Tenant,
    DocumentStatus, DocumentClassification,
    utc_now
)
from services.openai_client import get_openai_client


@dataclass
class ClassificationResult:
    """Result of document classification"""
    classification: DocumentClassification
    confidence: float  # 0.0 to 1.0
    reason: str
    key_indicators: List[str]
    is_borderline: bool  # True if needs human review


class ClassificationService:
    """
    Document classification service using GPT-4.

    Features:
    - Classifies documents as work/personal/spam
    - Provides confidence scores and explanations
    - Flags borderline cases for human review
    - Batch processing with rate limiting
    """

    # Confidence thresholds
    HIGH_CONFIDENCE_THRESHOLD = 0.85
    BORDERLINE_THRESHOLD = 0.65

    # Classification prompt template
    CLASSIFICATION_PROMPT = """You are a document classification expert. Analyze the following document and classify it as WORK, PERSONAL, or SPAM.

DOCUMENT METADATA:
- Title/Subject: {title}
- Sender: {sender}
- Source Type: {source_type}
- Date: {date}

DOCUMENT CONTENT:
{content}

CLASSIFICATION GUIDELINES:

WORK documents include:
- Professional emails, meeting notes, project discussions
- Business communications, reports, proposals
- Code reviews, technical documentation
- Client communications, contracts
- Team discussions, task assignments
- Company announcements, HR communications

PERSONAL documents include:
- Family and friend communications
- Personal appointments, health matters
- Shopping, banking (personal accounts)
- Social events, hobbies
- Personal photos, memories
- Non-work subscriptions, newsletters

SPAM includes:
- Promotional emails from unknown sources
- Marketing that user didn't sign up for
- Phishing attempts, scam messages
- Automated notifications without value
- Mass mailings, chain emails

Respond in the following JSON format:
{{
    "classification": "WORK" | "PERSONAL" | "SPAM",
    "confidence": 0.0-1.0,
    "reason": "Brief explanation of why this classification was chosen",
    "key_indicators": ["indicator1", "indicator2", "indicator3"],
    "is_borderline": true | false
}}

Be conservative: if unsure between WORK and PERSONAL, mark as borderline.
"""

    def __init__(self, db: Session):
        self.db = db
        self.client = get_openai_client()

    # ========================================================================
    # SINGLE DOCUMENT CLASSIFICATION
    # ========================================================================

    def classify_document(self, document: Document) -> ClassificationResult:
        """
        Classify a single document.

        Args:
            document: Document to classify

        Returns:
            ClassificationResult with classification, confidence, and explanation
        """
        try:
            # Build prompt
            content_preview = (document.content or "")[:3000]  # Limit content length

            prompt = self.CLASSIFICATION_PROMPT.format(
                title=document.title or "No title",
                sender=document.sender_email or document.sender or "Unknown",
                source_type=document.source_type or "Unknown",
                date=document.source_created_at.isoformat() if document.source_created_at else "Unknown",
                content=content_preview
            )

            # Call GPT-4
            response = self.client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a document classification expert. Always respond with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,  # Low temperature for consistent classification
                max_tokens=500,
                response_format={"type": "json_object"}
            )

            # Parse response
            result_text = response.choices[0].message.content
            result_data = json.loads(result_text)

            # Map classification string to enum
            classification_map = {
                "WORK": DocumentClassification.WORK,
                "PERSONAL": DocumentClassification.PERSONAL,
                "SPAM": DocumentClassification.SPAM
            }

            classification = classification_map.get(
                result_data.get("classification", "").upper(),
                DocumentClassification.UNKNOWN
            )

            confidence = float(result_data.get("confidence", 0.5))

            # Determine if borderline
            is_borderline = (
                result_data.get("is_borderline", False) or
                confidence < self.BORDERLINE_THRESHOLD
            )

            return ClassificationResult(
                classification=classification,
                confidence=confidence,
                reason=result_data.get("reason", ""),
                key_indicators=result_data.get("key_indicators", []),
                is_borderline=is_borderline
            )

        except json.JSONDecodeError as e:
            return ClassificationResult(
                classification=DocumentClassification.UNKNOWN,
                confidence=0.0,
                reason=f"Failed to parse classification response: {str(e)}",
                key_indicators=[],
                is_borderline=True
            )
        except Exception as e:
            return ClassificationResult(
                classification=DocumentClassification.UNKNOWN,
                confidence=0.0,
                reason=f"Classification error: {str(e)}",
                key_indicators=[],
                is_borderline=True
            )

    # ========================================================================
    # BATCH CLASSIFICATION
    # ========================================================================

    def classify_pending_documents(
        self,
        tenant_id: str,
        limit: int = 50,
        auto_confirm_threshold: float = None
    ) -> Dict[str, Any]:
        """
        Classify all pending documents for a tenant.

        Args:
            tenant_id: Tenant ID
            limit: Maximum documents to process
            auto_confirm_threshold: Auto-confirm if confidence >= this (None = no auto-confirm)

        Returns:
            Summary of classification results
        """
        # Get pending documents
        documents = self.db.query(Document).filter(
            Document.tenant_id == tenant_id,
            Document.status == DocumentStatus.PENDING,
            Document.is_deleted == False
        ).limit(limit).all()

        results = {
            "total": len(documents),
            "work": 0,
            "personal": 0,
            "spam": 0,
            "unknown": 0,
            "auto_confirmed": 0,
            "needs_review": 0,
            "errors": []
        }

        for doc in documents:
            try:
                # Classify
                classification_result = self.classify_document(doc)

                # Update document
                doc.classification = classification_result.classification
                doc.classification_confidence = classification_result.confidence
                doc.classification_reason = classification_result.reason
                doc.status = DocumentStatus.CLASSIFIED
                doc.updated_at = utc_now()

                # Track counts
                if classification_result.classification == DocumentClassification.WORK:
                    results["work"] += 1
                elif classification_result.classification == DocumentClassification.PERSONAL:
                    results["personal"] += 1
                elif classification_result.classification == DocumentClassification.SPAM:
                    results["spam"] += 1
                else:
                    results["unknown"] += 1

                # Auto-confirm high confidence classifications
                if (
                    auto_confirm_threshold and
                    classification_result.confidence >= auto_confirm_threshold and
                    not classification_result.is_borderline
                ):
                    doc.user_confirmed = True
                    doc.user_confirmed_at = utc_now()
                    doc.status = DocumentStatus.CONFIRMED
                    results["auto_confirmed"] += 1
                elif classification_result.is_borderline:
                    results["needs_review"] += 1

            except Exception as e:
                results["errors"].append({
                    "document_id": doc.id,
                    "error": str(e)
                })

        self.db.commit()
        return results

    # ========================================================================
    # USER CONFIRMATION
    # ========================================================================

    def confirm_classification(
        self,
        document_id: str,
        tenant_id: str,
        confirmed_classification: Optional[DocumentClassification] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        User confirms (or corrects) document classification.

        Args:
            document_id: Document ID
            tenant_id: Tenant ID (for security)
            confirmed_classification: Override classification (None = confirm current)

        Returns:
            (success, error_message)
        """
        try:
            document = self.db.query(Document).filter(
                Document.id == document_id,
                Document.tenant_id == tenant_id
            ).first()

            if not document:
                return False, "Document not found"

            if confirmed_classification:
                document.classification = confirmed_classification

            document.user_confirmed = True
            document.user_confirmed_at = utc_now()
            document.status = DocumentStatus.CONFIRMED
            document.updated_at = utc_now()

            self.db.commit()
            return True, None

        except Exception as e:
            self.db.rollback()
            return False, str(e)

    def reject_document(
        self,
        document_id: str,
        tenant_id: str,
        reason: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        User rejects/deletes a document (marks as personal to exclude from knowledge base).

        Args:
            document_id: Document ID
            tenant_id: Tenant ID
            reason: Optional reason for rejection

        Returns:
            (success, error_message)
        """
        try:
            document = self.db.query(Document).filter(
                Document.id == document_id,
                Document.tenant_id == tenant_id
            ).first()

            if not document:
                return False, "Document not found"

            document.classification = DocumentClassification.PERSONAL
            document.user_confirmed = True
            document.user_confirmed_at = utc_now()
            document.status = DocumentStatus.REJECTED
            document.updated_at = utc_now()

            if reason:
                doc_meta = document.doc_metadata or {}
                doc_meta["rejection_reason"] = reason
                document.doc_metadata = doc_meta

            self.db.commit()
            return True, None

        except Exception as e:
            self.db.rollback()
            return False, str(e)

    def bulk_confirm(
        self,
        document_ids: List[str],
        tenant_id: str,
        classification: Optional[DocumentClassification] = None
    ) -> Dict[str, Any]:
        """
        Bulk confirm multiple documents.

        Args:
            document_ids: List of document IDs
            tenant_id: Tenant ID
            classification: Optional override classification for all

        Returns:
            Summary of results
        """
        results = {
            "confirmed": 0,
            "not_found": 0,
            "errors": []
        }

        for doc_id in document_ids:
            success, error = self.confirm_classification(doc_id, tenant_id, classification)
            if success:
                results["confirmed"] += 1
            elif error == "Document not found":
                results["not_found"] += 1
            else:
                results["errors"].append({"document_id": doc_id, "error": error})

        return results

    def bulk_reject(
        self,
        document_ids: List[str],
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Bulk reject multiple documents.
        """
        results = {
            "rejected": 0,
            "not_found": 0,
            "errors": []
        }

        for doc_id in document_ids:
            success, error = self.reject_document(doc_id, tenant_id)
            if success:
                results["rejected"] += 1
            elif error == "Document not found":
                results["not_found"] += 1
            else:
                results["errors"].append({"document_id": doc_id, "error": error})

        return results

    # ========================================================================
    # QUERIES
    # ========================================================================

    def get_documents_for_review(
        self,
        tenant_id: str,
        classification_filter: Optional[DocumentClassification] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Document], int]:
        """
        Get documents needing user review.

        Args:
            tenant_id: Tenant ID
            classification_filter: Filter by classification
            limit: Page size
            offset: Page offset

        Returns:
            (list of documents, total count)
        """
        query = self.db.query(Document).filter(
            Document.tenant_id == tenant_id,
            Document.status == DocumentStatus.CLASSIFIED,
            Document.user_confirmed == False,
            Document.is_deleted == False
        )

        if classification_filter:
            query = query.filter(Document.classification == classification_filter)

        # Order by confidence (lowest first - needs most review)
        query = query.order_by(Document.classification_confidence.asc())

        total = query.count()
        documents = query.offset(offset).limit(limit).all()

        return documents, total

    def get_confirmed_work_documents(
        self,
        tenant_id: str
    ) -> List[Document]:
        """
        Get all confirmed work documents (for knowledge base).
        """
        return self.db.query(Document).filter(
            Document.tenant_id == tenant_id,
            Document.status == DocumentStatus.CONFIRMED,
            Document.classification == DocumentClassification.WORK,
            Document.is_deleted == False
        ).all()

    def get_classification_stats(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get classification statistics for a tenant.
        """
        from sqlalchemy import func

        # Total documents by status
        status_counts = dict(
            self.db.query(
                Document.status,
                func.count(Document.id)
            ).filter(
                Document.tenant_id == tenant_id,
                Document.is_deleted == False
            ).group_by(Document.status).all()
        )

        # Total documents by classification
        classification_counts = dict(
            self.db.query(
                Document.classification,
                func.count(Document.id)
            ).filter(
                Document.tenant_id == tenant_id,
                Document.is_deleted == False
            ).group_by(Document.classification).all()
        )

        # Documents needing review
        needs_review = self.db.query(func.count(Document.id)).filter(
            Document.tenant_id == tenant_id,
            Document.status == DocumentStatus.CLASSIFIED,
            Document.user_confirmed == False,
            Document.is_deleted == False
        ).scalar()

        # Average confidence
        avg_confidence = self.db.query(func.avg(Document.classification_confidence)).filter(
            Document.tenant_id == tenant_id,
            Document.classification_confidence.isnot(None),
            Document.is_deleted == False
        ).scalar()

        return {
            "by_status": {
                status.value if hasattr(status, 'value') else str(status): count
                for status, count in status_counts.items()
            },
            "by_classification": {
                cls.value if hasattr(cls, 'value') else str(cls): count
                for cls, count in classification_counts.items()
            },
            "needs_review": needs_review or 0,
            "average_confidence": round(float(avg_confidence or 0), 3),
            "total_documents": sum(status_counts.values())
        }
