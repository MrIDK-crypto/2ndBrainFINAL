"""
Extraction Service - Extract structured summaries from documents

Extracts key information during sync for efficient Knowledge Gap analysis:
- Summary
- Key topics/themes
- Entities (people, systems, organizations)
- Decisions
- Processes
- Dates/deadlines
- Action items

Created: 2025-12-09
"""

import os
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session

from services.openai_client import get_openai_client

from database.models import Document

# Max content to send for extraction (chars)
MAX_EXTRACTION_CONTENT = 50000


def utc_now():
    return datetime.now(timezone.utc)


# Extraction prompt
EXTRACTION_PROMPT = """Analyze this document and extract structured information.

DOCUMENT TITLE: {title}
DOCUMENT TYPE: {doc_type}
CONTENT:
{content}

Extract the following information. Be specific and reference actual content from the document.
If a field has no relevant information, use an empty list or null.

Return a JSON object with this structure:
{{
    "summary": "2-3 sentence overview of what this document is about",
    "key_topics": ["topic1", "topic2", "topic3"],
    "entities": {{
        "people": ["person names mentioned"],
        "systems": ["systems, tools, software mentioned"],
        "organizations": ["companies, teams, departments mentioned"]
    }},
    "decisions": ["any decisions mentioned or implied"],
    "processes": ["any processes, workflows, or procedures described"],
    "dates": [
        {{"date": "YYYY-MM-DD or description", "event": "what happened/will happen"}}
    ],
    "action_items": ["any tasks, todos, or next steps mentioned"],
    "technical_details": ["any technical specifications, configurations, or implementations"],
    "word_count": <approximate word count of original content>
}}

Focus on extracting CONCRETE, SPECIFIC information that would help someone understand:
1. What this document is about
2. Who is involved
3. What systems/tools are mentioned
4. What decisions were made
5. What needs to be done

Return ONLY the JSON object, no other text."""


class ExtractionService:
    """
    Service for extracting structured summaries from documents.

    Used during sync to pre-process documents for efficient Knowledge Gap analysis.
    Instead of sending full document content to GPT during gap analysis,
    we use these pre-extracted summaries.
    """

    def __init__(self, client=None):
        """Initialize extraction service."""
        if client:
            self.client = client
        else:
            self.client = get_openai_client()

    def extract_from_content(
        self,
        content: str,
        title: str = "Untitled",
        doc_type: str = "document"
    ) -> Optional[Dict[str, Any]]:
        """
        Extract structured summary from document content.

        Args:
            content: Document text content
            title: Document title
            doc_type: Type of document (email, file, etc.)

        Returns:
            Dict with extracted structured information, or None if extraction fails
        """
        if not content or len(content.strip()) < 50:
            return None

        # Truncate content if too long
        truncated_content = content[:MAX_EXTRACTION_CONTENT]
        if len(content) > MAX_EXTRACTION_CONTENT:
            truncated_content += f"\n\n[... Content truncated. Original length: {len(content)} chars]"

        try:
            response = self.client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a document analyst. Extract structured information from documents accurately. Return only valid JSON."
                    },
                    {
                        "role": "user",
                        "content": EXTRACTION_PROMPT.format(
                            title=title,
                            doc_type=doc_type,
                            content=truncated_content
                        )
                    }
                ],
                temperature=0.1,  # Low temperature for consistent extraction
                max_tokens=2000,
                response_format={"type": "json_object"}
            )

            result_text = response.choices[0].message.content
            result = json.loads(result_text)

            # Add metadata
            result["extracted_at"] = utc_now().isoformat()
            result["content_length"] = len(content)
            result["was_truncated"] = len(content) > MAX_EXTRACTION_CONTENT

            return result

        except json.JSONDecodeError as e:
            print(f"[ExtractionService] JSON parse error: {e}")
            return None
        except Exception as e:
            print(f"[ExtractionService] Extraction error: {e}")
            return None

    def extract_document(
        self,
        document: Document,
        db: Session,
        force: bool = False
    ) -> bool:
        """
        Extract structured summary for a single document and save to DB.

        Args:
            document: Document model instance
            db: Database session
            force: If True, re-extract even if already extracted

        Returns:
            True if extraction was successful
        """
        # Skip if already extracted (unless forced)
        if not force and document.structured_summary:
            return True

        # Skip if no content
        if not document.content:
            return False

        print(f"[ExtractionService] Extracting: {document.title or document.id[:8]}...")

        result = self.extract_from_content(
            content=document.content,
            title=document.title or "Untitled",
            doc_type=document.source_type or "document"
        )

        if result:
            document.structured_summary = result
            document.structured_summary_at = utc_now()
            db.commit()
            print(f"[ExtractionService] Extracted {len(result.get('key_topics', []))} topics, "
                  f"{len(result.get('decisions', []))} decisions")
            return True

        return False

    def extract_documents(
        self,
        documents: List[Document],
        db: Session,
        force: bool = False,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Extract structured summaries for multiple documents.

        Args:
            documents: List of Document model instances
            db: Database session
            force: If True, re-extract even if already extracted
            progress_callback: Optional callback(current, total, status)

        Returns:
            Dict with extraction stats
        """
        total = len(documents)
        extracted = 0
        skipped = 0
        errors = 0

        for i, doc in enumerate(documents):
            if progress_callback:
                progress_callback(i + 1, total, f"Extracting: {doc.title or 'Untitled'}")

            # Skip if already has extraction and not forcing
            if not force and doc.structured_summary:
                skipped += 1
                continue

            # Skip if no content
            if not doc.content:
                skipped += 1
                continue

            try:
                success = self.extract_document(doc, db, force=force)
                if success:
                    extracted += 1
                else:
                    errors += 1
            except Exception as e:
                print(f"[ExtractionService] Error extracting {doc.id}: {e}")
                errors += 1

        return {
            "total": total,
            "extracted": extracted,
            "skipped": skipped,
            "errors": errors
        }

    def extract_tenant_documents(
        self,
        tenant_id: str,
        db: Session,
        force: bool = False,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Extract structured summaries for all documents of a tenant.

        Args:
            tenant_id: Tenant ID
            db: Database session
            force: If True, re-extract all
            limit: Optional limit on number of documents

        Returns:
            Dict with extraction stats
        """
        query = db.query(Document).filter(
            Document.tenant_id == tenant_id,
            Document.is_deleted == False,
            Document.content != None,
            Document.content != ''
        )

        if not force:
            query = query.filter(Document.structured_summary == None)

        if limit:
            query = query.limit(limit)

        documents = query.all()
        print(f"[ExtractionService] Found {len(documents)} documents to extract for tenant {tenant_id}")

        return self.extract_documents(documents, db, force=force)


# Singleton instance
_extraction_service: Optional[ExtractionService] = None


def get_extraction_service() -> ExtractionService:
    """Get or create singleton ExtractionService instance"""
    global _extraction_service
    if _extraction_service is None:
        _extraction_service = ExtractionService()
    return _extraction_service
