"""
Knowledge Service
Manages knowledge gaps, answers, voice transcription, and embedding index rebuilding.

Supports two modes of gap analysis:
1. Simple mode: Single-pass LLM analysis (fast, basic)
2. Multi-stage mode: 5-stage LLM reasoning (comprehensive, intelligent)
"""

import os
import io
import json
import pickle
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from pathlib import Path
import tempfile
import threading

from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from services.openai_client import get_openai_client

from database.models import (
    Document, KnowledgeGap, GapAnswer, Project, Tenant,
    DocumentStatus, DocumentClassification, GapCategory, GapStatus,
    generate_uuid, utc_now
)

# Token budget for Knowledge Gap analysis
# GPT-4o has 128K context, but we want to leave room for system prompt and response
# Estimate: 1 token ≈ 4 chars for English text
MAX_GAP_ANALYSIS_CHARS = 400000  # ~100K tokens, leaving buffer for prompt/response
CHARS_PER_DOC_SUMMARY = 3000  # Estimated chars per structured summary
from services.multistage_gap_analyzer import (
    MultiStageGapAnalyzer, DocumentContext, MultiStageAnalysisResult
)
from services.goal_first_analyzer import (
    GoalFirstGapAnalyzer, DocumentContext as GFDocumentContext, GoalFirstAnalysisResult
)
from services.intelligent_gap_detector import (
    IntelligentGapDetector, get_intelligent_gap_detector, Gap
)

# Import v3.0 Knowledge Gap System
try:
    from services.knowledge_gap_v3 import KnowledgeGapOrchestrator
    V3_AVAILABLE = True
except ImportError as e:
    V3_AVAILABLE = False
    print(f"Knowledge Gap v3.0 not available: {e}")

logger = logging.getLogger(__name__)


# Azure Whisper Deployment (still needed for transcription)
AZURE_WHISPER_DEPLOYMENT = os.getenv("AZURE_WHISPER_DEPLOYMENT", "whisper")


@dataclass
class TranscriptionResult:
    """Result of audio transcription"""
    text: str
    confidence: float
    language: str
    duration_seconds: float
    segments: List[Dict]


@dataclass
class GapAnalysisResult:
    """Result of gap analysis"""
    gaps: List[Dict]
    total_documents_analyzed: int
    categories_found: Dict[str, int]


class KnowledgeService:
    """
    Knowledge service for managing gaps, answers, and embeddings.

    Features:
    - Knowledge gap identification from documents
    - Answer persistence with voice transcription
    - Whisper API integration for audio
    - Embedding index rebuilding
    """

    # Gap analysis prompt
    GAP_ANALYSIS_PROMPT = """Analyze the following documents and identify knowledge gaps - information that is missing, unclear, or needs documentation.

DOCUMENTS:
{documents}

For each gap you identify, provide:
1. A clear title describing the missing knowledge
2. A description of why this information is important
3. A category (decision, technical, process, context, relationship, timeline, outcome, rationale)
4. A priority (1-5, 5 being highest)
5. 3-5 specific questions that would help fill this gap

Focus on:
- Decisions mentioned but not explained
- Technical details that are assumed but not documented
- Processes that are referenced but not described
- Context that would help understand the situation
- Relationships between people/teams that are unclear
- Timelines and deadlines that aren't specified
- Outcomes of projects/decisions that aren't recorded
- Rationale behind important choices

Respond in JSON format:
{{
    "gaps": [
        {{
            "title": "...",
            "description": "...",
            "category": "decision|technical|process|context|relationship|timeline|outcome|rationale",
            "priority": 1-5,
            "questions": ["question1", "question2", ...],
            "related_topics": ["topic1", "topic2"]
        }}
    ]
}}
"""

    def __init__(self, db: Session):
        self.db = db
        self.client = get_openai_client()

    # ========================================================================
    # DOCUMENT CONTENT PREPARATION (for Knowledge Gap Analysis)
    # ========================================================================

    def _prepare_document_for_analysis(
        self,
        doc: Document,
        use_summary: bool = True,
        max_content_chars: int = 4000
    ) -> str:
        """
        Prepare document content for Knowledge Gap analysis.

        Uses structured_summary when available (efficient, pre-extracted).
        Falls back to truncated content if no summary exists.

        Args:
            doc: Document model instance
            use_summary: Whether to use structured_summary (default True)
            max_content_chars: Max chars if falling back to raw content

        Returns:
            Formatted document text for analysis
        """
        # Header with metadata
        doc_text = f"---\n"
        doc_text += f"Title: {doc.title or 'Untitled'}\n"
        doc_text += f"Type: {doc.source_type or 'unknown'}\n"
        doc_text += f"Date: {doc.source_created_at.isoformat() if doc.source_created_at else 'Unknown'}\n"
        if doc.sender:
            doc_text += f"From: {doc.sender}\n"

        # Use structured summary if available (Phase 2 extraction)
        if use_summary and doc.structured_summary:
            summary = doc.structured_summary
            doc_text += f"\nSummary: {summary.get('summary', 'No summary')}\n"

            # Key topics
            if summary.get('key_topics'):
                doc_text += f"Key Topics: {', '.join(summary['key_topics'])}\n"

            # Entities
            entities = summary.get('entities', {})
            if entities.get('people'):
                doc_text += f"People: {', '.join(entities['people'])}\n"
            if entities.get('systems'):
                doc_text += f"Systems: {', '.join(entities['systems'])}\n"
            if entities.get('organizations'):
                doc_text += f"Organizations: {', '.join(entities['organizations'])}\n"

            # Decisions (critical for gap analysis)
            if summary.get('decisions'):
                doc_text += f"Decisions: {'; '.join(summary['decisions'])}\n"

            # Processes
            if summary.get('processes'):
                doc_text += f"Processes: {'; '.join(summary['processes'])}\n"

            # Dates/deadlines
            if summary.get('dates'):
                dates_str = '; '.join([f"{d.get('date', '?')}: {d.get('event', '?')}"
                                       for d in summary['dates'][:5]])
                doc_text += f"Key Dates: {dates_str}\n"

            # Action items
            if summary.get('action_items'):
                doc_text += f"Action Items: {'; '.join(summary['action_items'][:5])}\n"

            # Technical details
            if summary.get('technical_details'):
                doc_text += f"Technical: {'; '.join(summary['technical_details'][:3])}\n"

            doc_text += f"Word Count: ~{summary.get('word_count', 'unknown')}\n"
        else:
            # Fallback: use truncated raw content
            content = doc.content or ''
            if len(content) > max_content_chars:
                content = content[:max_content_chars] + f"\n[... truncated, {len(doc.content)} total chars]"
            doc_text += f"\nContent:\n{content}\n"

        doc_text += "---\n"
        return doc_text

    def _prepare_documents_for_analysis(
        self,
        documents: List[Document],
        max_total_chars: int = MAX_GAP_ANALYSIS_CHARS,
        prioritize_recent: bool = True
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Prepare multiple documents for Knowledge Gap analysis with token budgeting.

        Prioritizes documents with structured summaries.
        Falls back gracefully when summaries don't exist.
        Implements smart sampling if over budget.

        Args:
            documents: List of Document instances
            max_total_chars: Maximum total characters to include
            prioritize_recent: Prioritize more recent documents

        Returns:
            (combined_text, stats_dict)
        """
        # Sort by date (recent first) if prioritizing
        if prioritize_recent:
            documents = sorted(
                documents,
                key=lambda d: d.source_created_at or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True
            )

        doc_texts = []
        total_chars = 0
        stats = {
            "total_documents": len(documents),
            "documents_included": 0,
            "documents_with_summary": 0,
            "documents_with_fallback": 0,
            "documents_skipped": 0,
            "total_chars": 0
        }

        for doc in documents:
            # Check if we have room for another document
            if total_chars >= max_total_chars:
                stats["documents_skipped"] = len(documents) - stats["documents_included"]
                logger.warning(
                    f"[KnowledgeGap] Token budget reached. Included {stats['documents_included']}/{len(documents)} docs"
                )
                break

            # Prepare document (prefer summary)
            has_summary = bool(doc.structured_summary)
            doc_text = self._prepare_document_for_analysis(
                doc,
                use_summary=True,
                max_content_chars=4000  # Fallback limit per doc
            )

            # Check if adding this doc exceeds budget
            if total_chars + len(doc_text) > max_total_chars:
                # Try with smaller content limit
                doc_text = self._prepare_document_for_analysis(
                    doc,
                    use_summary=True,
                    max_content_chars=2000
                )
                if total_chars + len(doc_text) > max_total_chars:
                    continue  # Skip this doc

            doc_texts.append(doc_text)
            total_chars += len(doc_text)
            stats["documents_included"] += 1

            if has_summary:
                stats["documents_with_summary"] += 1
            else:
                stats["documents_with_fallback"] += 1

        stats["total_chars"] = total_chars
        stats["estimated_tokens"] = total_chars // 4

        # Log stats
        logger.info(f"[KnowledgeGap] Document preparation stats:")
        logger.info(f"  - Total documents: {stats['total_documents']}")
        logger.info(f"  - Included: {stats['documents_included']}")
        logger.info(f"  - With summary: {stats['documents_with_summary']}")
        logger.info(f"  - With fallback (raw): {stats['documents_with_fallback']}")
        logger.info(f"  - Skipped (budget): {stats['documents_skipped']}")
        logger.info(f"  - Total chars: {stats['total_chars']} (~{stats['estimated_tokens']} tokens)")

        return "\n".join(doc_texts), stats

    # ========================================================================
    # KNOWLEDGE GAP ANALYSIS
    # ========================================================================

    def analyze_gaps(
        self,
        tenant_id: str,
        project_id: Optional[str] = None,
        force_reanalyze: bool = False,
        include_pending: bool = True
    ) -> GapAnalysisResult:
        """
        Analyze documents to identify knowledge gaps.

        Args:
            tenant_id: Tenant ID
            project_id: Optional project to analyze (None = all)
            force_reanalyze: Re-analyze even if gaps exist
            include_pending: Include pending/classified documents (not just confirmed)

        Returns:
            GapAnalysisResult with identified gaps
        """
        from sqlalchemy import or_

        # Get work documents - include CONFIRMED, CLASSIFIED, and optionally PENDING
        # This allows gap analysis to work on newly synced documents that haven't
        # been fully confirmed yet
        if include_pending:
            # Include all documents that are classified as WORK (or not yet classified)
            # and are in PENDING, CLASSIFIED, or CONFIRMED status
            query = self.db.query(Document).filter(
                Document.tenant_id == tenant_id,
                Document.is_deleted == False,
                or_(
                    # Confirmed work documents
                    and_(
                        Document.status == DocumentStatus.CONFIRMED,
                        Document.classification == DocumentClassification.WORK
                    ),
                    # Classified work documents (awaiting confirmation)
                    and_(
                        Document.status == DocumentStatus.CLASSIFIED,
                        Document.classification == DocumentClassification.WORK
                    ),
                    # Pending documents (not yet classified) - include all for analysis
                    Document.status == DocumentStatus.PENDING
                )
            )
        else:
            # Original behavior: only confirmed work documents
            query = self.db.query(Document).filter(
                Document.tenant_id == tenant_id,
                Document.status == DocumentStatus.CONFIRMED,
                Document.classification == DocumentClassification.WORK,
                Document.is_deleted == False
            )

        if project_id:
            query = query.filter(Document.project_id == project_id)

        documents = query.limit(200).all()  # Increased limit - token budgeting handles the rest

        if not documents:
            return GapAnalysisResult(
                gaps=[],
                total_documents_analyzed=0,
                categories_found={}
            )

        # Build document text using structured summaries (Phase 3 improvement)
        # Uses pre-extracted summaries from Phase 2 when available
        # Falls back to truncated content for docs without summaries
        # Implements token budgeting to prevent API failures
        combined_text, prep_stats = self._prepare_documents_for_analysis(
            documents,
            max_total_chars=MAX_GAP_ANALYSIS_CHARS,
            prioritize_recent=True
        )

        # Call GPT-4 for analysis
        try:
            response = self.client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a knowledge management expert. Analyze documents to identify gaps in organizational knowledge. Always respond with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": self.GAP_ANALYSIS_PROMPT.format(documents=combined_text)
                    }
                ],
                temperature=0.3,
                max_tokens=4000,  # Increased from 2000 to handle more comprehensive analysis
                response_format={"type": "json_object"}
            )

            result_text = response.choices[0].message.content
            result_data = json.loads(result_text)

            gaps_data = result_data.get("gaps", [])

            # Save gaps to database
            category_counts = {}
            saved_gaps = []

            for gap_data in gaps_data:
                category_str = gap_data.get("category", "context").lower()
                category_map = {
                    "decision": GapCategory.DECISION,
                    "technical": GapCategory.TECHNICAL,
                    "process": GapCategory.PROCESS,
                    "context": GapCategory.CONTEXT,
                    "relationship": GapCategory.RELATIONSHIP,
                    "timeline": GapCategory.TIMELINE,
                    "outcome": GapCategory.OUTCOME,
                    "rationale": GapCategory.RATIONALE
                }
                category = category_map.get(category_str, GapCategory.CONTEXT)

                # Track category counts
                category_counts[category.value] = category_counts.get(category.value, 0) + 1

                # Create gap
                gap = KnowledgeGap(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    title=gap_data.get("title", "Unknown Gap"),
                    description=gap_data.get("description", ""),
                    category=category,
                    priority=min(max(gap_data.get("priority", 3), 1), 5),
                    status=GapStatus.OPEN,
                    questions=[
                        {"text": q, "answered": False}
                        for q in gap_data.get("questions", [])
                    ],
                    context={
                        "related_topics": gap_data.get("related_topics", []),
                        "analyzed_documents": [doc.id for doc in documents[:10]]
                    }
                )
                self.db.add(gap)
                saved_gaps.append(gap)

            self.db.commit()

            return GapAnalysisResult(
                gaps=[{
                    "id": g.id,
                    "title": g.title,
                    "category": g.category.value,
                    "priority": g.priority,
                    "questions_count": len(g.questions)
                } for g in saved_gaps],
                total_documents_analyzed=len(documents),
                categories_found=category_counts
            )

        except Exception as e:
            self.db.rollback()
            return GapAnalysisResult(
                gaps=[],
                total_documents_analyzed=len(documents),
                categories_found={"error": str(e)}
            )

    def analyze_gaps_multistage(
        self,
        tenant_id: str,
        project_id: Optional[str] = None,
        force_reanalyze: bool = False,
        include_pending: bool = True,
        max_documents: int = 100
    ) -> GapAnalysisResult:
        """
        Analyze documents using Multi-Stage LLM Reasoning.

        This method runs a comprehensive 5-stage analysis:
        1. Corpus Understanding - Build mental model
        2. Expert Mind Simulation - Tacit knowledge gaps
        3. New Hire Simulation - Onboarding blockers
        4. Failure Mode Analysis - Operational gaps
        5. Question Synthesis - Intelligent questions

        Args:
            tenant_id: Tenant ID
            project_id: Optional project to analyze (None = all)
            force_reanalyze: Re-analyze even if gaps exist
            include_pending: Include pending/classified documents
            max_documents: Maximum documents to analyze (for cost control)

        Returns:
            GapAnalysisResult with identified gaps
        """
        from sqlalchemy import or_

        logger.info(f"Starting multi-stage gap analysis for tenant {tenant_id}")

        # Get work documents - include CONFIRMED, CLASSIFIED, and optionally PENDING
        if include_pending:
            query = self.db.query(Document).filter(
                Document.tenant_id == tenant_id,
                Document.is_deleted == False,
                or_(
                    and_(
                        Document.status == DocumentStatus.CONFIRMED,
                        Document.classification == DocumentClassification.WORK
                    ),
                    and_(
                        Document.status == DocumentStatus.CLASSIFIED,
                        Document.classification == DocumentClassification.WORK
                    ),
                    Document.status == DocumentStatus.PENDING
                )
            )
        else:
            query = self.db.query(Document).filter(
                Document.tenant_id == tenant_id,
                Document.status == DocumentStatus.CONFIRMED,
                Document.classification == DocumentClassification.WORK,
                Document.is_deleted == False
            )

        if project_id:
            query = query.filter(Document.project_id == project_id)

        # Get documents with limit
        documents = query.limit(max_documents).all()

        if not documents:
            logger.warning(f"No documents found for tenant {tenant_id}")
            return GapAnalysisResult(
                gaps=[],
                total_documents_analyzed=0,
                categories_found={}
            )

        logger.info(f"Found {len(documents)} documents for analysis")

        # Convert to DocumentContext objects
        # Use structured summaries (Phase 3) when available for efficient token usage
        doc_contexts = []
        docs_with_summary = 0
        docs_with_fallback = 0

        for doc in documents:
            # Get project name if available
            project_name = None
            if doc.project_id:
                project = self.db.query(Project).filter(
                    Project.id == doc.project_id
                ).first()
                if project:
                    project_name = project.name

            # Use structured summary content if available (more efficient)
            if doc.structured_summary:
                summary = doc.structured_summary
                # Build condensed content from structured summary
                content_parts = []
                content_parts.append(f"Summary: {summary.get('summary', '')}")

                if summary.get('key_topics'):
                    content_parts.append(f"Topics: {', '.join(summary['key_topics'])}")

                entities = summary.get('entities', {})
                if entities.get('people'):
                    content_parts.append(f"People: {', '.join(entities['people'])}")
                if entities.get('systems'):
                    content_parts.append(f"Systems: {', '.join(entities['systems'])}")
                if entities.get('organizations'):
                    content_parts.append(f"Organizations: {', '.join(entities['organizations'])}")

                if summary.get('decisions'):
                    content_parts.append(f"Decisions: {'; '.join(summary['decisions'])}")
                if summary.get('processes'):
                    content_parts.append(f"Processes: {'; '.join(summary['processes'])}")
                if summary.get('action_items'):
                    content_parts.append(f"Actions: {'; '.join(summary['action_items'][:5])}")
                if summary.get('technical_details'):
                    content_parts.append(f"Technical: {'; '.join(summary['technical_details'][:3])}")

                content = "\n".join(content_parts)
                docs_with_summary += 1
            else:
                # Fallback: truncated raw content
                content = (doc.content or "")[:8000]  # Limit per doc
                if doc.content and len(doc.content) > 8000:
                    content += f"\n[... truncated, {len(doc.content)} total chars]"
                docs_with_fallback += 1

            doc_contexts.append(DocumentContext(
                id=doc.id,
                title=doc.title or "Untitled",
                content=content,
                source_type=doc.source_type or "unknown",
                sender=doc.sender,
                created_at=doc.source_created_at.isoformat() if doc.source_created_at else None,
                project_name=project_name
            ))

        logger.info(f"[MultiStage] Docs with summary: {docs_with_summary}, with fallback: {docs_with_fallback}")

        try:
            # Run multi-stage analysis
            analyzer = MultiStageGapAnalyzer(client=self.client)
            result = analyzer.analyze(
                documents=doc_contexts,
                max_docs_per_stage=min(30, len(doc_contexts)),
                temperature=0.4
            )

            # Convert to knowledge gaps
            gaps_data = analyzer.to_knowledge_gaps(result, project_id)

            # Save gaps to database
            category_counts = {}
            saved_gaps = []

            for gap_data in gaps_data:
                category_str = gap_data.get("category", "context").lower()
                category_map = {
                    "decision": GapCategory.DECISION,
                    "technical": GapCategory.TECHNICAL,
                    "process": GapCategory.PROCESS,
                    "context": GapCategory.CONTEXT,
                    "relationship": GapCategory.RELATIONSHIP,
                    "timeline": GapCategory.TIMELINE,
                    "outcome": GapCategory.OUTCOME,
                    "rationale": GapCategory.RATIONALE
                }
                category = category_map.get(category_str, GapCategory.CONTEXT)

                # Track category counts
                category_counts[category.value] = category_counts.get(category.value, 0) + 1

                # Create gap
                gap = KnowledgeGap(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    title=gap_data.get("title", "Unknown Gap"),
                    description=gap_data.get("description", ""),
                    category=category,
                    priority=min(max(gap_data.get("priority", 3), 1), 5),
                    status=GapStatus.OPEN,
                    questions=gap_data.get("questions", []),
                    context=gap_data.get("context", {})
                )
                self.db.add(gap)
                saved_gaps.append(gap)

            self.db.commit()

            logger.info(f"Multi-stage analysis complete: {len(saved_gaps)} gaps created")

            return GapAnalysisResult(
                gaps=[{
                    "id": g.id,
                    "title": g.title,
                    "category": g.category.value,
                    "priority": g.priority,
                    "questions_count": len(g.questions)
                } for g in saved_gaps],
                total_documents_analyzed=len(documents),
                categories_found=category_counts
            )

        except Exception as e:
            self.db.rollback()
            logger.error(f"Multi-stage analysis failed: {e}")
            return GapAnalysisResult(
                gaps=[],
                total_documents_analyzed=len(documents),
                categories_found={"error": str(e)}
            )

    def analyze_gaps_goalfirst(
        self,
        tenant_id: str,
        project_id: Optional[str] = None,
        force_reanalyze: bool = False,
        include_pending: bool = True,
        max_documents: int = 100
    ) -> GapAnalysisResult:
        """
        Analyze documents using Goal-First Backward Reasoning.

        This method runs a 4-stage analysis:
        1. Goal Extraction - Define the project goal
        2. Decision Extraction - Find strategic, scope, timeline, financial decisions
        3. Alternative Inference - Infer what alternatives existed
        4. Question Generation - Create "why X over Y" questions

        Filter: Only questions a NEW EMPLOYEE would need to understand the project.
        Skip obvious operational questions (like "why 12 beds?").

        Args:
            tenant_id: Tenant ID
            project_id: Optional project to analyze (None = all)
            force_reanalyze: Re-analyze even if gaps exist
            include_pending: Include pending/classified documents
            max_documents: Maximum documents to analyze (for cost control)

        Returns:
            GapAnalysisResult with identified gaps
        """
        from sqlalchemy import or_

        logger.info(f"Starting goal-first gap analysis for tenant {tenant_id}")

        # Get work documents
        if include_pending:
            query = self.db.query(Document).filter(
                Document.tenant_id == tenant_id,
                Document.is_deleted == False,
                or_(
                    and_(
                        Document.status == DocumentStatus.CONFIRMED,
                        Document.classification == DocumentClassification.WORK
                    ),
                    and_(
                        Document.status == DocumentStatus.CLASSIFIED,
                        Document.classification == DocumentClassification.WORK
                    ),
                    Document.status == DocumentStatus.PENDING
                )
            )
        else:
            query = self.db.query(Document).filter(
                Document.tenant_id == tenant_id,
                Document.status == DocumentStatus.CONFIRMED,
                Document.classification == DocumentClassification.WORK,
                Document.is_deleted == False
            )

        if project_id:
            query = query.filter(Document.project_id == project_id)

        documents = query.limit(max_documents).all()

        if not documents:
            logger.warning(f"No documents found for tenant {tenant_id}")
            return GapAnalysisResult(
                gaps=[],
                total_documents_analyzed=0,
                categories_found={}
            )

        logger.info(f"Found {len(documents)} documents for goal-first analysis")

        # Convert to DocumentContext objects for goal-first analyzer
        # Use structured summaries (Phase 3) when available for efficient token usage
        doc_contexts = []
        docs_with_summary = 0
        docs_with_content = 0
        docs_without_content = 0
        total_content_chars = 0

        for doc in documents:
            project_name = None
            if doc.project_id:
                project = self.db.query(Project).filter(
                    Project.id == doc.project_id
                ).first()
                if project:
                    project_name = project.name

            # Use structured summary content if available (Phase 3 improvement)
            if doc.structured_summary:
                summary = doc.structured_summary
                # Build condensed content from structured summary
                content_parts = []
                content_parts.append(f"Summary: {summary.get('summary', '')}")

                if summary.get('key_topics'):
                    content_parts.append(f"Topics: {', '.join(summary['key_topics'])}")

                entities = summary.get('entities', {})
                if entities.get('people'):
                    content_parts.append(f"People: {', '.join(entities['people'])}")
                if entities.get('systems'):
                    content_parts.append(f"Systems: {', '.join(entities['systems'])}")
                if entities.get('organizations'):
                    content_parts.append(f"Organizations: {', '.join(entities['organizations'])}")

                if summary.get('decisions'):
                    content_parts.append(f"Decisions: {'; '.join(summary['decisions'])}")
                if summary.get('processes'):
                    content_parts.append(f"Processes: {'; '.join(summary['processes'])}")
                if summary.get('action_items'):
                    content_parts.append(f"Actions: {'; '.join(summary['action_items'][:5])}")
                if summary.get('technical_details'):
                    content_parts.append(f"Technical: {'; '.join(summary['technical_details'][:3])}")

                content = "\n".join(content_parts)
                content_len = len(content)
                docs_with_summary += 1
                docs_with_content += 1
                total_content_chars += content_len
            else:
                # Fallback: truncated raw content
                raw_content = doc.content or ""
                content_len = len(raw_content)

                if content_len > 0:
                    # Truncate to prevent token bomb
                    content = raw_content[:8000]
                    if content_len > 8000:
                        content += f"\n[... truncated, {content_len} total chars]"
                    docs_with_content += 1
                    total_content_chars += min(content_len, 8000)
                else:
                    content = ""
                    docs_without_content += 1

            doc_contexts.append(GFDocumentContext(
                id=doc.id,
                title=doc.title or "Untitled",
                content=content,
                source_type=doc.source_type or "unknown",
                sender=doc.sender,
                created_at=doc.source_created_at.isoformat() if doc.source_created_at else None,
                project_name=project_name
            ))

        # Log content statistics
        logger.info(f"[GoalFirst] Document content stats:")
        logger.info(f"  - Documents with SUMMARY: {docs_with_summary}")
        logger.info(f"  - Documents WITH content: {docs_with_content}")
        logger.info(f"  - Documents WITHOUT content: {docs_without_content}")
        logger.info(f"  - Total content characters: {total_content_chars}")

        if docs_without_content == len(documents):
            logger.warning("[GoalFirst] WARNING: ALL documents have ZERO content!")
            logger.warning("[GoalFirst] Content extraction likely failed - check Box sync permissions")
            logger.warning("[GoalFirst] Analysis will produce generic/irrelevant questions without document content")

        try:
            # Run goal-first analysis
            analyzer = GoalFirstGapAnalyzer(client=self.client)
            result = analyzer.analyze(
                documents=doc_contexts,
                max_docs_per_stage=min(30, len(doc_contexts)),
                temperature=0.3
            )

            # Convert to knowledge gaps
            gaps_data = analyzer.to_knowledge_gaps(result, project_id)

            # Save gaps to database
            category_counts = {}
            saved_gaps = []

            for gap_data in gaps_data:
                category_str = gap_data.get("category", "context").lower()
                category_map = {
                    "strategic": GapCategory.DECISION,
                    "decision": GapCategory.DECISION,
                    "scope": GapCategory.CONTEXT,
                    "timeline": GapCategory.TIMELINE,
                    "financial": GapCategory.RATIONALE,
                    "competition": GapCategory.DECISION,
                    "context": GapCategory.CONTEXT
                }
                category = category_map.get(category_str, GapCategory.CONTEXT)

                category_counts[category.value] = category_counts.get(category.value, 0) + 1

                gap = KnowledgeGap(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    title=gap_data.get("title", "Unknown Gap"),
                    description=gap_data.get("description", ""),
                    category=category,
                    priority=min(max(gap_data.get("priority", 3), 1), 5),
                    status=GapStatus.OPEN,
                    questions=gap_data.get("questions", []),
                    context=gap_data.get("context", {})
                )
                self.db.add(gap)
                saved_gaps.append(gap)

            self.db.commit()

            logger.info(f"Goal-first analysis complete: {len(saved_gaps)} gaps created")

            return GapAnalysisResult(
                gaps=[{
                    "id": g.id,
                    "title": g.title,
                    "category": g.category.value,
                    "priority": g.priority,
                    "questions_count": len(g.questions)
                } for g in saved_gaps],
                total_documents_analyzed=len(documents),
                categories_found=category_counts
            )

        except Exception as e:
            self.db.rollback()
            logger.error(f"Goal-first analysis failed: {e}")
            return GapAnalysisResult(
                gaps=[],
                total_documents_analyzed=len(documents),
                categories_found={"error": str(e)}
            )

    def analyze_gaps_intelligent(
        self,
        tenant_id: str,
        project_id: Optional[str] = None,
        force_reanalyze: bool = False,
        include_pending: bool = True,
        max_documents: int = 100
    ) -> GapAnalysisResult:
        """
        Analyze documents using Intelligent Gap Detection (Advanced NLP).

        This method runs a comprehensive 6-layer analysis:
        1. Frame-Based Extraction - Structured concept detection (decisions, processes)
        2. Semantic Role Labeling - Missing agents, causes, manners
        3. Discourse Analysis - Claims without evidence, results without causes
        4. Knowledge Graph - Missing entity relations, isolated knowledge
        5. Cross-Document Verification - Contradictions, single-source knowledge
        6. Grounded Question Generation - Specific, actionable questions

        Features:
        - Pattern-based detection (not just GPT guessing)
        - Bus factor risk analysis
        - Contradiction detection
        - Entity relationship gaps
        - Grounded questions with evidence

        Args:
            tenant_id: Tenant ID
            project_id: Optional project to analyze (None = all)
            force_reanalyze: Re-analyze even if gaps exist
            include_pending: Include pending/classified documents
            max_documents: Maximum documents to analyze

        Returns:
            GapAnalysisResult with intelligent gaps
        """
        from sqlalchemy import or_

        logger.info(f"Starting INTELLIGENT gap analysis for tenant {tenant_id}")

        # Get work documents
        if include_pending:
            query = self.db.query(Document).filter(
                Document.tenant_id == tenant_id,
                Document.is_deleted == False,
                or_(
                    and_(
                        Document.status == DocumentStatus.CONFIRMED,
                        Document.classification == DocumentClassification.WORK
                    ),
                    and_(
                        Document.status == DocumentStatus.CLASSIFIED,
                        Document.classification == DocumentClassification.WORK
                    ),
                    Document.status == DocumentStatus.PENDING
                )
            )
        else:
            query = self.db.query(Document).filter(
                Document.tenant_id == tenant_id,
                Document.status == DocumentStatus.CONFIRMED,
                Document.classification == DocumentClassification.WORK,
                Document.is_deleted == False
            )

        if project_id:
            query = query.filter(Document.project_id == project_id)

        documents = query.limit(max_documents).all()

        if not documents:
            logger.warning(f"No documents found for tenant {tenant_id}")
            return GapAnalysisResult(
                gaps=[],
                total_documents_analyzed=0,
                categories_found={}
            )

        logger.info(f"Found {len(documents)} documents for intelligent analysis")

        try:
            # Initialize intelligent gap detector
            detector = get_intelligent_gap_detector()

            # Process each document
            docs_processed = 0
            for doc in documents:
                # Get content - prefer structured summary, fallback to raw
                if doc.structured_summary:
                    summary = doc.structured_summary
                    content_parts = []
                    content_parts.append(f"Summary: {summary.get('summary', '')}")

                    if summary.get('key_topics'):
                        content_parts.append(f"Topics: {', '.join(summary['key_topics'])}")
                    if summary.get('decisions'):
                        content_parts.append(f"Decisions: {'; '.join(summary['decisions'])}")
                    if summary.get('processes'):
                        content_parts.append(f"Processes: {'; '.join(summary['processes'])}")
                    if summary.get('action_items'):
                        content_parts.append(f"Actions: {'; '.join(summary['action_items'][:5])}")
                    if summary.get('technical_details'):
                        content_parts.append(f"Technical: {'; '.join(summary['technical_details'][:3])}")

                    # Include raw content for better pattern matching
                    raw_content = doc.content or ""
                    if len(raw_content) > 0:
                        content_parts.append(f"\nFull Content:\n{raw_content[:30000]}")

                    content = "\n".join(content_parts)
                else:
                    content = (doc.content or "")[:30000]

                if len(content) > 100:
                    detector.add_document(
                        doc_id=doc.id,
                        title=doc.title or "Untitled",
                        content=content
                    )
                    docs_processed += 1

            logger.info(f"[Intelligent] Processed {docs_processed} documents with content")

            # Run analysis
            result = detector.analyze()

            # Convert to knowledge gaps
            gaps_data = detector.to_knowledge_gaps(result, project_id)

            # Save gaps to database
            category_counts = {}
            saved_gaps = []

            for gap_data in gaps_data[:50]:  # Limit to top 50 gaps
                category_str = gap_data.get("category", "context").lower()
                category_map = {
                    "decision": GapCategory.DECISION,
                    "technical": GapCategory.TECHNICAL,
                    "process": GapCategory.PROCESS,
                    "context": GapCategory.CONTEXT,
                    "relationship": GapCategory.RELATIONSHIP,
                    "timeline": GapCategory.TIMELINE,
                    "outcome": GapCategory.OUTCOME,
                    "rationale": GapCategory.RATIONALE
                }
                category = category_map.get(category_str, GapCategory.CONTEXT)

                category_counts[category.value] = category_counts.get(category.value, 0) + 1

                gap = KnowledgeGap(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    title=gap_data.get("title", "Unknown Gap")[:200],
                    description=gap_data.get("description", "")[:1000],
                    category=category,
                    priority=min(max(gap_data.get("priority", 3), 1), 5),
                    status=GapStatus.OPEN,
                    questions=gap_data.get("questions", []),
                    context={
                        **gap_data.get("context", {}),
                        "analysis_type": "intelligent",
                        "stats": result.get("stats", {})
                    }
                )
                self.db.add(gap)
                saved_gaps.append(gap)

            self.db.commit()

            # Log detailed stats
            stats = result.get("stats", {})
            logger.info(f"[Intelligent] Analysis complete:")
            logger.info(f"  - Total frames extracted: {stats.get('total_frames', 0)}")
            logger.info(f"  - Frames with gaps: {stats.get('frames_with_gaps', 0)}")
            logger.info(f"  - Bus factor risks: {stats.get('bus_factor_risks', 0)}")
            logger.info(f"  - Contradictions found: {stats.get('contradictions', 0)}")
            logger.info(f"  - Gaps created: {len(saved_gaps)}")

            return GapAnalysisResult(
                gaps=[{
                    "id": g.id,
                    "title": g.title,
                    "category": g.category.value,
                    "priority": g.priority,
                    "questions_count": len(g.questions)
                } for g in saved_gaps],
                total_documents_analyzed=len(documents),
                categories_found=category_counts
            )

        except Exception as e:
            self.db.rollback()
            logger.error(f"Intelligent analysis failed: {e}", exc_info=True)
            return GapAnalysisResult(
                gaps=[],
                total_documents_analyzed=len(documents),
                categories_found={"error": str(e)}
            )

    def analyze_gaps_v3(
        self,
        tenant_id: str,
        project_id: Optional[str] = None,
        force_reanalyze: bool = False,
        include_pending: bool = True,
        max_documents: int = 100
    ) -> GapAnalysisResult:
        """
        Analyze documents using Knowledge Gap Detection v3.0 (Enhanced).

        This is the most advanced analysis method with 6 stages:
        1. Deep Document Extraction (GPT-4) - Semantic understanding
        2. Knowledge Graph Assembly - Entity resolution & relationships
        3. Multi-Analyzer Gap Detection - 8 specialized analyzers
        4. LLM Question Generation - Contextual, natural questions
        5. Intelligent Prioritization - Multi-factor scoring
        6. Feedback & Learning Loop - Continuous improvement

        Analyzers include:
        - Bus Factor Analysis
        - Decision Archaeology
        - Process Completeness
        - Tribal Knowledge Detection
        - Dependency Risk
        - Temporal Staleness
        - Contradiction Detection
        - Onboarding Barrier Analysis

        Args:
            tenant_id: Tenant ID
            project_id: Optional project to analyze
            force_reanalyze: Re-analyze even if gaps exist
            include_pending: Include pending documents
            max_documents: Maximum documents to analyze

        Returns:
            GapAnalysisResult with gaps and metadata
        """
        if not V3_AVAILABLE:
            logger.warning("Knowledge Gap v3.0 not available, falling back to intelligent mode")
            return self.analyze_gaps_intelligent(
                tenant_id, project_id, force_reanalyze, include_pending, max_documents
            )

        logger.info(f"[v3.0] Starting enhanced knowledge gap analysis for tenant {tenant_id}")

        # Get documents to analyze
        # Include pending, classified, confirmed (exclude rejected and archived)
        allowed_statuses = [
            DocumentStatus.PENDING,
            DocumentStatus.CLASSIFIED,
            DocumentStatus.CONFIRMED,
            DocumentStatus.PROCESSING
        ] if include_pending else [
            DocumentStatus.CLASSIFIED,
            DocumentStatus.CONFIRMED
        ]

        query = self.db.query(Document).filter(
            Document.tenant_id == tenant_id,
            Document.status.in_(allowed_statuses)
        )

        if project_id:
            query = query.filter(Document.project_id == project_id)

        documents = query.order_by(Document.created_at.desc()).limit(max_documents).all()

        if not documents:
            logger.warning(f"[v3.0] No documents found for analysis")
            return GapAnalysisResult(
                gaps=[],
                total_documents_analyzed=0,
                categories_found={}
            )

        logger.info(f"[v3.0] Found {len(documents)} documents to analyze")

        # Prepare documents for v3.0 orchestrator
        doc_list = []
        for doc in documents:
            content = doc.content or doc.summary or ""
            if content and len(content.strip()) > 50:
                doc_list.append({
                    "id": doc.id,
                    "title": doc.title or "Untitled",
                    "content": content,
                    "metadata": {
                        "source_type": doc.source_type,
                        "classification": doc.classification.value if doc.classification else None,
                        "created_at": doc.created_at.isoformat() if doc.created_at else None
                    }
                })

        if not doc_list:
            logger.warning(f"[v3.0] No documents with content found")
            return GapAnalysisResult(
                gaps=[],
                total_documents_analyzed=len(documents),
                categories_found={}
            )

        logger.info(f"[v3.0] Analyzing {len(doc_list)} documents with content")

        try:
            # Initialize v3.0 orchestrator
            orchestrator = KnowledgeGapOrchestrator()

            # Run analysis
            result = orchestrator.analyze(
                documents=doc_list,
                tenant_id=tenant_id,
                project_id=project_id,
                top_n_questions=30
            )

            # Convert to knowledge gaps and save
            category_counts = {}
            saved_gaps = []

            for pq in result.prioritized_questions[:50]:
                # pq is a dictionary from to_dict() call
                question_data = pq.get("question", {})
                gap_data = pq.get("gap", {})

                # Map v3 categories to database categories
                category_str = (question_data.get("category") or "context").lower()
                category_map = {
                    "process": GapCategory.PROCESS,
                    "technical": GapCategory.TECHNICAL,
                    "decision": GapCategory.DECISION,
                    "context": GapCategory.CONTEXT,
                    "relationship": GapCategory.RELATIONSHIP,
                    "timeline": GapCategory.TIMELINE,
                    "outcome": GapCategory.OUTCOME,
                    "rationale": GapCategory.RATIONALE
                }
                category = category_map.get(category_str, GapCategory.CONTEXT)
                category_counts[category.value] = category_counts.get(category.value, 0) + 1

                # Build questions list from generated question
                primary_question = question_data.get("primary_question", "Unknown question")
                questions = [primary_question]
                sub_questions = question_data.get("sub_questions", [])
                if sub_questions:
                    questions.extend(sub_questions[:3])

                # Calculate priority (1-5) from score (0-1)
                score = pq.get("final_score", pq.get("priority_score", 0.5))
                priority = max(1, min(5, int(score * 5) + 1))

                gap = KnowledgeGap(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    title=primary_question[:200],
                    description=question_data.get("priority_reasoning") or question_data.get("business_impact") or "",
                    category=category,
                    priority=priority,
                    status=GapStatus.OPEN,
                    questions=questions,
                    context={
                        "analysis_type": "v3.0",
                        "gap_type": gap_data.get("gap_type", "unknown"),
                        "severity": gap_data.get("severity", "medium"),
                        "score": score,
                        "score_breakdown": pq.get("score_breakdown", {}),
                        "suggested_respondent": question_data.get("suggested_respondent"),
                        "estimated_effort": question_data.get("estimated_effort"),
                        "answer_format": question_data.get("answer_format_suggestion")
                    }
                )
                self.db.add(gap)
                saved_gaps.append(gap)

            self.db.commit()

            # Log stats (result is an AnalysisResult object)
            logger.info(f"[v3.0] Analysis complete:")
            logger.info(f"  - Documents analyzed: {result.documents_processed}")
            logger.info(f"  - Entities extracted: {result.total_entities}")
            logger.info(f"  - Gaps detected: {result.total_gaps}")
            logger.info(f"  - Questions generated: {result.total_questions}")
            logger.info(f"  - Gaps saved: {len(saved_gaps)}")

            return GapAnalysisResult(
                gaps=[{
                    "id": g.id,
                    "title": g.title,
                    "category": g.category.value,
                    "priority": g.priority,
                    "questions_count": len(g.questions)
                } for g in saved_gaps],
                total_documents_analyzed=len(documents),
                categories_found=category_counts
            )

        except Exception as e:
            self.db.rollback()
            logger.error(f"[v3.0] Analysis failed: {e}", exc_info=True)
            # Fallback to intelligent mode
            logger.info("[v3.0] Falling back to intelligent mode")
            return self.analyze_gaps_intelligent(
                tenant_id, project_id, force_reanalyze, include_pending, max_documents
            )

    def get_gaps(
        self,
        tenant_id: str,
        project_id: Optional[str] = None,
        status: Optional[GapStatus] = None,
        category: Optional[GapCategory] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[KnowledgeGap], int]:
        """
        Get knowledge gaps with filtering.
        """
        query = self.db.query(KnowledgeGap).filter(
            KnowledgeGap.tenant_id == tenant_id
        )

        if project_id:
            query = query.filter(KnowledgeGap.project_id == project_id)
        if status:
            query = query.filter(KnowledgeGap.status == status)
        if category:
            query = query.filter(KnowledgeGap.category == category)

        total = query.count()
        gaps = query.order_by(
            KnowledgeGap.priority.desc(),
            KnowledgeGap.created_at.desc()
        ).offset(offset).limit(limit).all()

        return gaps, total

    # ========================================================================
    # ANSWER MANAGEMENT
    # ========================================================================

    def submit_answer(
        self,
        gap_id: str,
        question_index: int,
        answer_text: str,
        user_id: str,
        tenant_id: str,
        is_voice_transcription: bool = False,
        audio_file_path: Optional[str] = None,
        transcription_confidence: Optional[float] = None
    ) -> Tuple[Optional[GapAnswer], Optional[str]]:
        """
        Submit an answer to a knowledge gap question.

        Args:
            gap_id: Knowledge gap ID
            question_index: Index of question in gap.questions
            answer_text: The answer text
            user_id: User who submitted
            tenant_id: Tenant ID
            is_voice_transcription: If answer came from voice
            audio_file_path: Path to audio file (if voice)
            transcription_confidence: Whisper confidence

        Returns:
            (GapAnswer, error_message)
        """
        try:
            # Get the gap
            gap = self.db.query(KnowledgeGap).filter(
                KnowledgeGap.id == gap_id,
                KnowledgeGap.tenant_id == tenant_id
            ).first()

            if not gap:
                return None, "Knowledge gap not found"

            # Get question text
            questions = gap.questions or []
            if question_index >= len(questions):
                return None, f"Question index {question_index} out of range"

            question_text = questions[question_index].get("text", "")

            # Create answer
            answer = GapAnswer(
                knowledge_gap_id=gap_id,
                tenant_id=tenant_id,  # Security: direct tenant isolation
                user_id=user_id,
                question_index=question_index,
                question_text=question_text,
                answer_text=answer_text,
                is_voice_transcription=is_voice_transcription,
                audio_file_path=audio_file_path,
                transcription_confidence=transcription_confidence,
                transcription_model="whisper" if is_voice_transcription else None
            )
            self.db.add(answer)

            # Update question as answered
            questions[question_index]["answered"] = True
            questions[question_index]["answer_id"] = answer.id
            gap.questions = questions

            # Check if all questions answered
            all_answered = all(q.get("answered", False) for q in questions)
            if all_answered:
                gap.status = GapStatus.ANSWERED

            gap.updated_at = utc_now()

            self.db.commit()

            return answer, None

        except Exception as e:
            self.db.rollback()
            return None, str(e)

    def get_answers(
        self,
        gap_id: str,
        tenant_id: str
    ) -> List[GapAnswer]:
        """
        Get all answers for a knowledge gap.
        """
        # Verify gap belongs to tenant
        gap = self.db.query(KnowledgeGap).filter(
            KnowledgeGap.id == gap_id,
            KnowledgeGap.tenant_id == tenant_id
        ).first()

        if not gap:
            return []

        return self.db.query(GapAnswer).filter(
            GapAnswer.knowledge_gap_id == gap_id
        ).order_by(GapAnswer.question_index).all()

    def update_answer(
        self,
        answer_id: str,
        answer_text: str,
        user_id: str,
        tenant_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Update an existing answer.
        """
        try:
            answer = self.db.query(GapAnswer).filter(
                GapAnswer.id == answer_id
            ).first()

            if not answer:
                return False, "Answer not found"

            # Verify tenant
            gap = self.db.query(KnowledgeGap).filter(
                KnowledgeGap.id == answer.knowledge_gap_id,
                KnowledgeGap.tenant_id == tenant_id
            ).first()

            if not gap:
                return False, "Not authorized"

            answer.answer_text = answer_text
            answer.updated_at = utc_now()

            self.db.commit()
            return True, None

        except Exception as e:
            self.db.rollback()
            return False, str(e)

    # ========================================================================
    # WHISPER TRANSCRIPTION
    # ========================================================================

    def transcribe_audio(
        self,
        audio_data: bytes,
        filename: str = "audio.wav",
        language: Optional[str] = None
    ) -> TranscriptionResult:
        """
        Transcribe audio using Whisper API.

        Args:
            audio_data: Raw audio bytes
            filename: Original filename (for format detection)
            language: Optional language hint (e.g., "en")

        Returns:
            TranscriptionResult with text and metadata
        """
        try:
            # Save to temp file (OpenAI API needs file-like object)
            with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix, delete=False) as tmp:
                tmp.write(audio_data)
                tmp_path = tmp.name

            try:
                # Open file for API
                with open(tmp_path, "rb") as audio_file:
                    # Call Whisper API
                    response = self.client.audio.transcriptions.create(
                        model=AZURE_WHISPER_DEPLOYMENT,
                        file=audio_file,
                        language=language,
                        response_format="verbose_json",
                        timestamp_granularities=["segment"]
                    )

                # Parse response
                return TranscriptionResult(
                    text=response.text,
                    confidence=1.0,  # Whisper doesn't provide confidence
                    language=response.language or language or "en",
                    duration_seconds=response.duration or 0,
                    segments=[
                        {
                            "start": s.start,
                            "end": s.end,
                            "text": s.text
                        }
                        for s in (response.segments or [])
                    ]
                )

            finally:
                # Clean up temp file
                os.unlink(tmp_path)

        except Exception as e:
            return TranscriptionResult(
                text="",
                confidence=0.0,
                language="",
                duration_seconds=0,
                segments=[{"error": str(e)}]
            )

    def transcribe_and_answer(
        self,
        gap_id: str,
        question_index: int,
        audio_data: bytes,
        filename: str,
        user_id: str,
        tenant_id: str,
        save_audio: bool = True
    ) -> Tuple[Optional[GapAnswer], Optional[str]]:
        """
        Transcribe audio and save as answer.

        Args:
            gap_id: Knowledge gap ID
            question_index: Question index
            audio_data: Audio bytes
            filename: Original filename
            user_id: User ID
            tenant_id: Tenant ID
            save_audio: Whether to save audio file

        Returns:
            (GapAnswer, error)
        """
        # Transcribe
        result = self.transcribe_audio(audio_data, filename)

        if not result.text:
            return None, "Transcription failed or returned empty text"

        # Save audio file if requested
        audio_path = None
        if save_audio:
            tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if tenant and tenant.data_directory:
                audio_dir = Path(tenant.data_directory) / "audio"
                audio_dir.mkdir(parents=True, exist_ok=True)

                audio_path = str(audio_dir / f"{generate_uuid()}{Path(filename).suffix}")
                with open(audio_path, "wb") as f:
                    f.write(audio_data)

        # Submit answer
        return self.submit_answer(
            gap_id=gap_id,
            question_index=question_index,
            answer_text=result.text,
            user_id=user_id,
            tenant_id=tenant_id,
            is_voice_transcription=True,
            audio_file_path=audio_path,
            transcription_confidence=result.confidence
        )

    # ========================================================================
    # EMBEDDING INDEX MANAGEMENT
    # ========================================================================

    def rebuild_embedding_index(
        self,
        tenant_id: str,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Rebuild the embedding index for a tenant.

        Args:
            tenant_id: Tenant ID
            force: Force rebuild even if index exists

        Returns:
            Summary of rebuild operation
        """
        try:
            # Get tenant
            tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                return {"error": "Tenant not found"}

            # Get confirmed work documents
            documents = self.db.query(Document).filter(
                Document.tenant_id == tenant_id,
                Document.status == DocumentStatus.CONFIRMED,
                Document.classification == DocumentClassification.WORK,
                Document.is_deleted == False
            ).all()

            # Also include gap answers as documents
            answers = self.db.query(GapAnswer).join(
                KnowledgeGap,
                GapAnswer.knowledge_gap_id == KnowledgeGap.id
            ).filter(
                KnowledgeGap.tenant_id == tenant_id
            ).all()

            # Return early if nothing to index
            if not documents and not answers:
                return {
                    "success": True,
                    "documents_processed": 0,
                    "chunks_created": 0,
                    "message": "No documents or answers to index"
                }

            # Build chunks
            chunks = []
            doc_index = {}

            for doc in documents:
                # Split document into chunks
                doc_chunks = self._chunk_document(doc)
                for i, chunk_text in enumerate(doc_chunks):
                    chunk_id = f"{doc.id}_{i}"
                    chunks.append({
                        "id": chunk_id,
                        "text": chunk_text,
                        "doc_id": doc.id,
                        "chunk_index": i
                    })
                    doc_index[chunk_id] = {
                        "doc_id": doc.id,
                        "title": doc.title,
                        "source_type": doc.source_type,
                        "sender": doc.sender,
                        "date": doc.source_created_at.isoformat() if doc.source_created_at else None
                    }

            # Add answers as chunks
            for answer in answers:
                chunk_id = f"answer_{answer.id}"
                chunks.append({
                    "id": chunk_id,
                    "text": f"Q: {answer.question_text}\nA: {answer.answer_text}",
                    "doc_id": f"gap_{answer.knowledge_gap_id}",
                    "chunk_index": 0
                })
                doc_index[chunk_id] = {
                    "doc_id": f"gap_{answer.knowledge_gap_id}",
                    "title": f"Answer: {answer.question_text[:50]}...",
                    "source_type": "gap_answer",
                    "sender": "Knowledge Gap Response",
                    "date": answer.created_at.isoformat() if answer.created_at else None
                }

            if not chunks:
                return {
                    "success": True,
                    "documents_processed": len(documents),
                    "chunks_created": 0,
                    "message": "No content to index"
                }

            # Generate embeddings in batches
            embeddings = []
            batch_size = 100

            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]
                batch_texts = [c["text"] for c in batch]

                response = self.client.create_embedding(
                    text=batch_texts,
                    dimensions=1536  # Match existing index
                )

                for j, emb in enumerate(response.data):
                    embeddings.append(emb.embedding)

            # Build index structure
            import numpy as np

            embedding_matrix = np.array(embeddings, dtype=np.float32)

            # Build chunks in the format expected by EnhancedRAGv2
            # RAG expects: {"content": str, "metadata": dict}
            formatted_chunks = []
            for c in chunks:
                formatted_chunks.append({
                    "content": c["text"],
                    "metadata": doc_index.get(c["id"], {}),
                    "chunk_id": c["id"]
                })

            index_data = {
                "chunks": formatted_chunks,
                "embeddings": embedding_matrix,
                "doc_index": doc_index,
                "chunk_ids": [c["id"] for c in chunks],
                "metadata": {
                    "created_at": utc_now().isoformat(),
                    "document_count": len(documents),
                    "chunk_count": len(chunks),
                    "embedding_model": self.client.get_embedding_model(),
                    "embedding_dimensions": 1536
                }
            }

            # Save to tenant directory
            if tenant.data_directory:
                index_path = Path(tenant.data_directory) / "embedding_index.pkl"
                index_path.parent.mkdir(parents=True, exist_ok=True)

                with open(index_path, "wb") as f:
                    pickle.dump(index_data, f)

            return {
                "success": True,
                "documents_processed": len(documents),
                "answers_included": len(answers),
                "chunks_created": len(chunks),
                "index_path": str(index_path) if tenant.data_directory else None
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _chunk_document(
        self,
        document: Document,
        chunk_size: int = 1000,
        overlap: int = 200
    ) -> List[str]:
        """
        Split document into overlapping chunks.
        """
        content = document.content or ""
        if not content:
            return []

        # Add title/metadata to first chunk
        header = f"Title: {document.title or 'Untitled'}\n"
        if document.sender:
            header += f"From: {document.sender}\n"
        header += "\n"

        chunks = []
        start = 0

        while start < len(content):
            end = start + chunk_size

            # Try to break at sentence boundary
            if end < len(content):
                # Look for sentence end
                for sep in [". ", ".\n", "! ", "!\n", "? ", "?\n"]:
                    last_sep = content[start:end].rfind(sep)
                    if last_sep > chunk_size // 2:
                        end = start + last_sep + len(sep)
                        break

            chunk_text = content[start:end].strip()

            if chunk_text:
                # Add header to first chunk
                if start == 0:
                    chunk_text = header + chunk_text
                chunks.append(chunk_text)

            start = end - overlap

        return chunks

    # ========================================================================
    # STATISTICS
    # ========================================================================

    def complete_knowledge_process(
        self,
        tenant_id: str,
        mark_completed: bool = True
    ) -> Dict[str, Any]:
        """
        Complete the knowledge transfer process by integrating all answered
        knowledge gaps into the RAG embedding index.

        This method:
        1. Collects all answered questions from knowledge gaps
        2. Rebuilds the embedding index to include answers
        3. Optionally marks gaps as completed/closed

        Args:
            tenant_id: Tenant ID
            mark_completed: Whether to mark gaps as completed (default True)

        Returns:
            Summary of the completion process including:
            - answers_integrated: Number of answers added to RAG
            - documents_indexed: Number of documents in RAG
            - gaps_completed: Number of gaps marked as completed
            - index_status: Status of embedding index rebuild
        """
        try:
            logger.info(f"Starting knowledge process completion for tenant {tenant_id}")

            # Get all answered knowledge gaps
            answered_gaps = self.db.query(KnowledgeGap).filter(
                KnowledgeGap.tenant_id == tenant_id,
                KnowledgeGap.status.in_([GapStatus.ANSWERED, GapStatus.IN_PROGRESS, GapStatus.OPEN])
            ).all()

            # Count answers that will be integrated
            all_answers = self.db.query(GapAnswer).join(
                KnowledgeGap,
                GapAnswer.knowledge_gap_id == KnowledgeGap.id
            ).filter(
                KnowledgeGap.tenant_id == tenant_id
            ).all()

            answers_count = len(all_answers)
            logger.info(f"Found {answers_count} answers to integrate into RAG")

            # Rebuild embedding index (this includes answers automatically)
            rebuild_result = self.rebuild_embedding_index(
                tenant_id=tenant_id,
                force=True  # Force rebuild to ensure answers are included
            )

            if rebuild_result.get("error"):
                return {
                    "success": False,
                    "error": rebuild_result["error"],
                    "answers_integrated": 0,
                    "documents_indexed": 0,
                    "gaps_completed": 0
                }

            gaps_completed = 0

            # Mark gaps with any answers as verified/completed
            if mark_completed:
                for gap in answered_gaps:
                    # Check if this gap has any answers
                    gap_answers = self.db.query(GapAnswer).filter(
                        GapAnswer.knowledge_gap_id == gap.id
                    ).count()

                    if gap_answers > 0:
                        # Mark as verified if has answers
                        gap.status = GapStatus.VERIFIED
                        gap.updated_at = utc_now()
                        gaps_completed += 1

                self.db.commit()
                logger.info(f"Marked {gaps_completed} gaps as verified")

            return {
                "success": True,
                "answers_integrated": answers_count,
                "documents_indexed": rebuild_result.get("documents_processed", 0),
                "chunks_created": rebuild_result.get("chunks_created", 0),
                "gaps_completed": gaps_completed,
                "index_path": rebuild_result.get("index_path"),
                "message": f"Successfully integrated {answers_count} answers into RAG knowledge base"
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"Knowledge process completion failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "answers_integrated": 0,
                "documents_indexed": 0,
                "gaps_completed": 0
            }

    def get_gap_stats(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get knowledge gap statistics.
        """
        # Gaps by status
        status_counts = dict(
            self.db.query(
                KnowledgeGap.status,
                func.count(KnowledgeGap.id)
            ).filter(
                KnowledgeGap.tenant_id == tenant_id
            ).group_by(KnowledgeGap.status).all()
        )

        # Gaps by category
        category_counts = dict(
            self.db.query(
                KnowledgeGap.category,
                func.count(KnowledgeGap.id)
            ).filter(
                KnowledgeGap.tenant_id == tenant_id
            ).group_by(KnowledgeGap.category).all()
        )

        # Total answers
        total_answers = self.db.query(func.count(GapAnswer.id)).join(
            KnowledgeGap,
            GapAnswer.knowledge_gap_id == KnowledgeGap.id
        ).filter(
            KnowledgeGap.tenant_id == tenant_id
        ).scalar()

        # Voice answers
        voice_answers = self.db.query(func.count(GapAnswer.id)).join(
            KnowledgeGap,
            GapAnswer.knowledge_gap_id == KnowledgeGap.id
        ).filter(
            KnowledgeGap.tenant_id == tenant_id,
            GapAnswer.is_voice_transcription == True
        ).scalar()

        return {
            "by_status": {
                status.value if hasattr(status, 'value') else str(status): count
                for status, count in status_counts.items()
            },
            "by_category": {
                cat.value if hasattr(cat, 'value') else str(cat): count
                for cat, count in category_counts.items()
            },
            "total_gaps": sum(status_counts.values()),
            "total_answers": total_answers or 0,
            "voice_answers": voice_answers or 0
        }
