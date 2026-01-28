"""
Stage 1: Deep Document Extraction
=================================

Uses GPT-4 to extract rich, structured information from documents
including entities, decisions, processes, knowledge signals, and more.

This replaces regex-based pattern matching with semantic understanding.
"""

import json
import logging
import hashlib
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import os

from services.openai_client import get_openai_client

logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class EntityType(str, Enum):
    PERSON = "PERSON"
    SYSTEM = "SYSTEM"
    PROCESS = "PROCESS"
    DECISION = "DECISION"
    CONCEPT = "CONCEPT"
    TEAM = "TEAM"
    TOOL = "TOOL"
    DATABASE = "DATABASE"
    SERVICE = "SERVICE"
    API = "API"


class SignalType(str, Enum):
    TRIBAL_KNOWLEDGE = "TRIBAL_KNOWLEDGE"  # "Ask John"
    ASSUMED_CONTEXT = "ASSUMED_CONTEXT"    # "As everyone knows"
    VAGUE_FUTURE = "VAGUE_FUTURE"          # "Eventually we'll"
    UNDOCUMENTED_PROCESS = "UNDOCUMENTED_PROCESS"  # "The usual way"
    SINGLE_POINT_REFERENCE = "SINGLE_POINT_REFERENCE"  # Only one person mentioned
    IMPLICIT_DEPENDENCY = "IMPLICIT_DEPENDENCY"  # Hidden dependencies
    HISTORICAL_CONTEXT = "HISTORICAL_CONTEXT"  # "Back when we used X"
    WORKAROUND = "WORKAROUND"              # "The trick is to"
    EDGE_CASE = "EDGE_CASE"                # "Except when"
    FAILURE_MODE = "FAILURE_MODE"          # "If X fails"


class DocumentType(str, Enum):
    DECISION_RECORD = "decision_record"
    PROCESS_DOCUMENTATION = "process_documentation"
    SYSTEM_DOCUMENTATION = "system_documentation"
    MEETING_NOTES = "meeting_notes"
    RUNBOOK = "runbook"
    ARCHITECTURE_DOC = "architecture_doc"
    ONBOARDING = "onboarding"
    TROUBLESHOOTING = "troubleshooting"
    GENERAL = "general"


@dataclass
class ExtractedEntity:
    """An entity extracted from a document"""
    name: str
    entity_type: EntityType
    role: Optional[str] = None
    description: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    mentioned_count: int = 1
    confidence: float = 0.8
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "entity_type": self.entity_type.value if isinstance(self.entity_type, Enum) else self.entity_type,
            "role": self.role,
            "description": self.description,
            "aliases": self.aliases,
            "mentioned_count": self.mentioned_count,
            "confidence": self.confidence,
            "evidence": self.evidence
        }


@dataclass
class ExtractedDecision:
    """A decision extracted from a document"""
    what: str
    who: List[str] = field(default_factory=list)
    when: Optional[str] = None
    why: Optional[str] = None
    why_quality: str = "missing"  # missing, vague, partial, complete
    alternatives_considered: List[str] = field(default_factory=list)
    alternatives_quality: str = "missing"  # missing, mentioned, evaluated
    reversibility: str = "unknown"  # low, medium, high, unknown
    decision_maker_clarity: str = "unclear"  # clear, vague, unclear
    status: str = "active"  # active, superseded, revisit_needed
    confidence: float = 0.8
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ExtractedProcess:
    """A process extracted from a document"""
    name: str
    owner: Optional[str] = None
    backup_owner: Optional[str] = None
    description: Optional[str] = None
    frequency: Optional[str] = None
    steps_documented: bool = False
    step_count: int = 0
    edge_cases_documented: bool = False
    failure_handling_documented: bool = False
    last_verified: Optional[str] = None
    criticality: str = "medium"  # low, medium, high, critical
    automation_level: str = "unknown"  # manual, partial, full, unknown
    confidence: float = 0.8
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ExtractedDependency:
    """A dependency relationship extracted from a document"""
    source: str
    target: str
    dependency_type: str  # uses, requires, calls, reads_from, writes_to
    criticality: str = "medium"  # low, medium, high, critical
    documented_impact: bool = False
    failure_impact: Optional[str] = None
    confidence: float = 0.8
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class KnowledgeSignal:
    """A signal indicating potential knowledge gap"""
    text: str
    signal_type: SignalType
    topic: Optional[str] = None
    referenced_person: Optional[str] = None
    risk_description: Optional[str] = None
    severity: str = "medium"  # low, medium, high, critical
    confidence: float = 0.8

    def to_dict(self) -> Dict:
        return {
            "text": self.text,
            "signal_type": self.signal_type.value if isinstance(self.signal_type, Enum) else self.signal_type,
            "topic": self.topic,
            "referenced_person": self.referenced_person,
            "risk_description": self.risk_description,
            "severity": self.severity,
            "confidence": self.confidence
        }


@dataclass
class TemporalMarker:
    """A temporal reference in the document"""
    text: str
    marker_type: str  # past_event, future_plan, recurring, deadline
    approximate_date: Optional[str] = None
    what_changed: Optional[str] = None
    confidence: float = 0.7

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class DocumentHealth:
    """Assessment of document health/quality"""
    created_date: Optional[str] = None
    last_updated: Optional[str] = None
    staleness_risk: str = "unknown"  # low, medium, high, critical
    completeness_score: float = 0.5
    clarity_score: float = 0.5
    actionability_score: float = 0.5

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class DocumentExtraction:
    """Complete extraction result for a document"""
    doc_id: str
    title: str
    document_type: DocumentType
    summary: str
    entities: List[ExtractedEntity]
    decisions: List[ExtractedDecision]
    processes: List[ExtractedProcess]
    dependencies: List[ExtractedDependency]
    knowledge_signals: List[KnowledgeSignal]
    temporal_markers: List[TemporalMarker]
    document_health: DocumentHealth
    key_topics: List[str]
    extracted_at: str
    extraction_model: str
    confidence: float
    raw_content_hash: str

    def to_dict(self) -> Dict:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "document_type": self.document_type.value if isinstance(self.document_type, Enum) else self.document_type,
            "summary": self.summary,
            "entities": [e.to_dict() for e in self.entities],
            "decisions": [d.to_dict() for d in self.decisions],
            "processes": [p.to_dict() for p in self.processes],
            "dependencies": [d.to_dict() for d in self.dependencies],
            "knowledge_signals": [s.to_dict() for s in self.knowledge_signals],
            "temporal_markers": [t.to_dict() for t in self.temporal_markers],
            "document_health": self.document_health.to_dict(),
            "key_topics": self.key_topics,
            "extracted_at": self.extracted_at,
            "extraction_model": self.extraction_model,
            "confidence": self.confidence,
            "raw_content_hash": self.raw_content_hash
        }


# =============================================================================
# EXTRACTION PROMPTS
# =============================================================================

DEEP_EXTRACTION_SYSTEM_PROMPT = """You are an expert knowledge analyst specializing in organizational knowledge extraction. Your task is to deeply analyze documents and extract structured information that will help identify knowledge gaps.

You must extract:
1. ENTITIES: People, systems, processes, tools, teams, databases, services, APIs
2. DECISIONS: What was decided, by whom, why, what alternatives were considered
3. PROCESSES: Workflows, procedures, their owners, documentation completeness
4. DEPENDENCIES: How systems/processes depend on each other
5. KNOWLEDGE SIGNALS: Phrases indicating undocumented knowledge ("ask John", "as everyone knows")
6. TEMPORAL MARKERS: When things happened or will happen
7. DOCUMENT HEALTH: How complete, current, and clear the document is

Be thorough. Look for implicit information, not just explicit statements.
Identify risks: single points of failure, tribal knowledge, undocumented processes.

Output valid JSON matching the specified schema."""


DEEP_EXTRACTION_USER_PROMPT = """Analyze the following document and extract structured information.

DOCUMENT TITLE: {title}
DOCUMENT ID: {doc_id}

CONTENT:
{content}

---

Extract the following as JSON:

{{
  "document_type": "decision_record|process_documentation|system_documentation|meeting_notes|runbook|architecture_doc|onboarding|troubleshooting|general",
  "summary": "2-3 sentence summary of the document",
  "key_topics": ["topic1", "topic2", ...],

  "entities": [
    {{
      "name": "Entity name",
      "entity_type": "PERSON|SYSTEM|PROCESS|DECISION|CONCEPT|TEAM|TOOL|DATABASE|SERVICE|API",
      "role": "What role/purpose this entity has in the context",
      "description": "Brief description",
      "aliases": ["other names used for this entity"],
      "mentioned_count": 3,
      "confidence": 0.9,
      "evidence": ["quote from doc showing this entity"]
    }}
  ],

  "decisions": [
    {{
      "what": "What was decided",
      "who": ["Person/team who made decision"],
      "when": "When it was made (if mentioned)",
      "why": "The rationale given (if any)",
      "why_quality": "missing|vague|partial|complete",
      "alternatives_considered": ["Alternative 1", "Alternative 2"],
      "alternatives_quality": "missing|mentioned|evaluated",
      "reversibility": "low|medium|high|unknown",
      "decision_maker_clarity": "clear|vague|unclear",
      "status": "active|superseded|revisit_needed",
      "confidence": 0.8,
      "evidence": ["quote showing this decision"]
    }}
  ],

  "processes": [
    {{
      "name": "Process name",
      "owner": "Who owns/maintains this process",
      "backup_owner": "Backup person (if mentioned)",
      "description": "What the process does",
      "frequency": "How often it runs (daily, weekly, on-demand, etc.)",
      "steps_documented": true|false,
      "step_count": 5,
      "edge_cases_documented": true|false,
      "failure_handling_documented": true|false,
      "last_verified": "When was this last confirmed accurate",
      "criticality": "low|medium|high|critical",
      "automation_level": "manual|partial|full|unknown",
      "confidence": 0.8,
      "evidence": ["quote about this process"]
    }}
  ],

  "dependencies": [
    {{
      "source": "System/process that depends",
      "target": "System/process being depended on",
      "dependency_type": "uses|requires|calls|reads_from|writes_to",
      "criticality": "low|medium|high|critical",
      "documented_impact": true|false,
      "failure_impact": "What happens if target fails",
      "confidence": 0.8,
      "evidence": ["quote showing dependency"]
    }}
  ],

  "knowledge_signals": [
    {{
      "text": "Exact quote from document",
      "signal_type": "TRIBAL_KNOWLEDGE|ASSUMED_CONTEXT|VAGUE_FUTURE|UNDOCUMENTED_PROCESS|SINGLE_POINT_REFERENCE|IMPLICIT_DEPENDENCY|HISTORICAL_CONTEXT|WORKAROUND|EDGE_CASE|FAILURE_MODE",
      "topic": "What topic this relates to",
      "referenced_person": "Person referenced (if any)",
      "risk_description": "Why this is a knowledge risk",
      "severity": "low|medium|high|critical",
      "confidence": 0.8
    }}
  ],

  "temporal_markers": [
    {{
      "text": "Quote with temporal reference",
      "marker_type": "past_event|future_plan|recurring|deadline",
      "approximate_date": "Best guess at date/timeframe",
      "what_changed": "What changed or will change",
      "confidence": 0.7
    }}
  ],

  "document_health": {{
    "created_date": "If mentioned",
    "last_updated": "If mentioned or inferable",
    "staleness_risk": "low|medium|high|critical",
    "completeness_score": 0.0-1.0,
    "clarity_score": 0.0-1.0,
    "actionability_score": 0.0-1.0
  }},

  "overall_confidence": 0.0-1.0
}}

Be thorough. Extract ALL entities, decisions, and processes mentioned.
Look for IMPLICIT knowledge signals - phrases like "the usual way", "as we discussed", "everyone knows".
Identify single points of failure where only one person is mentioned for a critical system.

Return ONLY valid JSON, no other text."""


# =============================================================================
# DEEP EXTRACTOR CLASS
# =============================================================================

class DeepDocumentExtractor:
    """
    Extracts rich, structured information from documents using Azure OpenAI.
    """

    def __init__(self, model: str = None):
        self.client = get_openai_client()
        self.model = model or self.client.get_chat_model()
        logger.info(f"[DeepExtractor] Initialized with model: {self.model}")

    def extract(self, doc_id: str, title: str, content: str) -> DocumentExtraction:
        """
        Extract structured information from a document.

        Args:
            doc_id: Unique document identifier
            title: Document title
            content: Document content

        Returns:
            DocumentExtraction with all extracted information
        """
        logger.info(f"[DeepExtractor] Extracting from: {title} ({len(content)} chars)")

        # Truncate if too long (GPT-4 context limit)
        max_content_length = 100000
        if len(content) > max_content_length:
            content = content[:max_content_length]
            logger.warning(f"[DeepExtractor] Truncated content to {max_content_length} chars")

        # Calculate content hash for caching/deduplication
        content_hash = hashlib.md5(content.encode()).hexdigest()

        try:
            # Call GPT-4 for extraction
            response = self.client.chat_completion(
                messages=[
                    {"role": "system", "content": DEEP_EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": DEEP_EXTRACTION_USER_PROMPT.format(
                        title=title,
                        doc_id=doc_id,
                        content=content
                    )}
                ],
                temperature=0.1,  # Low temperature for consistent extraction
                max_tokens=8000,
                response_format={"type": "json_object"}
            )

            # Parse response
            raw_json = response.choices[0].message.content
            extracted = json.loads(raw_json)

            logger.info(f"[DeepExtractor] Extracted: {len(extracted.get('entities', []))} entities, "
                       f"{len(extracted.get('decisions', []))} decisions, "
                       f"{len(extracted.get('processes', []))} processes, "
                       f"{len(extracted.get('knowledge_signals', []))} signals")

            # Convert to dataclass structure
            return self._parse_extraction(doc_id, title, extracted, content_hash)

        except json.JSONDecodeError as e:
            logger.error(f"[DeepExtractor] JSON parse error: {e}")
            return self._create_empty_extraction(doc_id, title, content_hash, str(e))
        except Exception as e:
            logger.error(f"[DeepExtractor] Extraction error: {e}")
            return self._create_empty_extraction(doc_id, title, content_hash, str(e))

    def _parse_extraction(
        self,
        doc_id: str,
        title: str,
        data: Dict,
        content_hash: str
    ) -> DocumentExtraction:
        """Parse GPT-4 response into structured dataclasses"""

        # Parse entities
        entities = []
        for e in data.get("entities", []):
            try:
                entity_type = EntityType(e.get("entity_type", "CONCEPT"))
            except ValueError:
                entity_type = EntityType.CONCEPT

            entities.append(ExtractedEntity(
                name=e.get("name", "Unknown"),
                entity_type=entity_type,
                role=e.get("role"),
                description=e.get("description"),
                aliases=e.get("aliases", []),
                mentioned_count=e.get("mentioned_count", 1),
                confidence=e.get("confidence", 0.8),
                evidence=e.get("evidence", [])
            ))

        # Parse decisions
        decisions = []
        for d in data.get("decisions", []):
            decisions.append(ExtractedDecision(
                what=d.get("what", "Unknown decision"),
                who=d.get("who", []),
                when=d.get("when"),
                why=d.get("why"),
                why_quality=d.get("why_quality", "missing"),
                alternatives_considered=d.get("alternatives_considered", []),
                alternatives_quality=d.get("alternatives_quality", "missing"),
                reversibility=d.get("reversibility", "unknown"),
                decision_maker_clarity=d.get("decision_maker_clarity", "unclear"),
                status=d.get("status", "active"),
                confidence=d.get("confidence", 0.8),
                evidence=d.get("evidence", [])
            ))

        # Parse processes
        processes = []
        for p in data.get("processes", []):
            processes.append(ExtractedProcess(
                name=p.get("name", "Unknown process"),
                owner=p.get("owner"),
                backup_owner=p.get("backup_owner"),
                description=p.get("description"),
                frequency=p.get("frequency"),
                steps_documented=p.get("steps_documented", False),
                step_count=p.get("step_count", 0),
                edge_cases_documented=p.get("edge_cases_documented", False),
                failure_handling_documented=p.get("failure_handling_documented", False),
                last_verified=p.get("last_verified"),
                criticality=p.get("criticality", "medium"),
                automation_level=p.get("automation_level", "unknown"),
                confidence=p.get("confidence", 0.8),
                evidence=p.get("evidence", [])
            ))

        # Parse dependencies
        dependencies = []
        for d in data.get("dependencies", []):
            dependencies.append(ExtractedDependency(
                source=d.get("source", "Unknown"),
                target=d.get("target", "Unknown"),
                dependency_type=d.get("dependency_type", "uses"),
                criticality=d.get("criticality", "medium"),
                documented_impact=d.get("documented_impact", False),
                failure_impact=d.get("failure_impact"),
                confidence=d.get("confidence", 0.8),
                evidence=d.get("evidence", [])
            ))

        # Parse knowledge signals
        signals = []
        for s in data.get("knowledge_signals", []):
            try:
                signal_type = SignalType(s.get("signal_type", "ASSUMED_CONTEXT"))
            except ValueError:
                signal_type = SignalType.ASSUMED_CONTEXT

            signals.append(KnowledgeSignal(
                text=s.get("text", ""),
                signal_type=signal_type,
                topic=s.get("topic"),
                referenced_person=s.get("referenced_person"),
                risk_description=s.get("risk_description"),
                severity=s.get("severity", "medium"),
                confidence=s.get("confidence", 0.8)
            ))

        # Parse temporal markers
        temporal = []
        for t in data.get("temporal_markers", []):
            temporal.append(TemporalMarker(
                text=t.get("text", ""),
                marker_type=t.get("marker_type", "past_event"),
                approximate_date=t.get("approximate_date"),
                what_changed=t.get("what_changed"),
                confidence=t.get("confidence", 0.7)
            ))

        # Parse document health
        health_data = data.get("document_health", {})
        health = DocumentHealth(
            created_date=health_data.get("created_date"),
            last_updated=health_data.get("last_updated"),
            staleness_risk=health_data.get("staleness_risk", "unknown"),
            completeness_score=health_data.get("completeness_score", 0.5),
            clarity_score=health_data.get("clarity_score", 0.5),
            actionability_score=health_data.get("actionability_score", 0.5)
        )

        # Parse document type
        try:
            doc_type = DocumentType(data.get("document_type", "general"))
        except ValueError:
            doc_type = DocumentType.GENERAL

        return DocumentExtraction(
            doc_id=doc_id,
            title=title,
            document_type=doc_type,
            summary=data.get("summary", "No summary available"),
            entities=entities,
            decisions=decisions,
            processes=processes,
            dependencies=dependencies,
            knowledge_signals=signals,
            temporal_markers=temporal,
            document_health=health,
            key_topics=data.get("key_topics", []),
            extracted_at=datetime.utcnow().isoformat(),
            extraction_model=self.model,
            confidence=data.get("overall_confidence", 0.7),
            raw_content_hash=content_hash
        )

    def _create_empty_extraction(
        self,
        doc_id: str,
        title: str,
        content_hash: str,
        error: str
    ) -> DocumentExtraction:
        """Create empty extraction on error"""
        return DocumentExtraction(
            doc_id=doc_id,
            title=title,
            document_type=DocumentType.GENERAL,
            summary=f"Extraction failed: {error}",
            entities=[],
            decisions=[],
            processes=[],
            dependencies=[],
            knowledge_signals=[],
            temporal_markers=[],
            document_health=DocumentHealth(),
            key_topics=[],
            extracted_at=datetime.utcnow().isoformat(),
            extraction_model=self.model,
            confidence=0.0,
            raw_content_hash=content_hash
        )

    def extract_batch(
        self,
        documents: List[Dict[str, str]],
        max_concurrent: int = 5
    ) -> List[DocumentExtraction]:
        """
        Extract from multiple documents.

        Args:
            documents: List of {"doc_id", "title", "content"} dicts
            max_concurrent: Maximum concurrent extractions

        Returns:
            List of DocumentExtraction objects
        """
        results = []

        for doc in documents:
            extraction = self.extract(
                doc_id=doc["doc_id"],
                title=doc["title"],
                content=doc["content"]
            )
            results.append(extraction)

        logger.info(f"[DeepExtractor] Batch complete: {len(results)} documents")
        return results
