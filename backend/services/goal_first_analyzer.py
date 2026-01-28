"""
Technical Knowledge Gap Analyzer

This module implements a 4-stage LLM reasoning pipeline that:
1. Extracts the project GOAL and TECHNICAL CONTEXT from documents
2. Identifies KEY TECHNICAL DECISIONS made
3. Infers TECHNICAL ALTERNATIVES that might have existed
4. Generates questions about WHY technical decisions were made

Filter: Only TECHNICAL questions a NEW EMPLOYEE would need.

YES: "Why Flask over FastAPI?"
YES: "Why PostgreSQL instead of MongoDB?"
YES: "Why REST API instead of GraphQL?"
YES: "What's the authentication flow?"
YES: "Why this specific API integration approach?"

NO: Strategic/business decisions
NO: Timeline/budget questions
NO: Political/organizational questions
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from services.openai_client import get_openai_client


logger = logging.getLogger(__name__)


@dataclass
class DocumentContext:
    """Represents a document with relevant metadata for analysis."""
    id: str
    title: str
    content: str
    source_type: str
    sender: Optional[str] = None
    created_at: Optional[str] = None
    project_name: Optional[str] = None

    def to_analysis_text(self, max_content_length: int = None) -> str:
        """Format document for LLM analysis.

        Args:
            max_content_length: Maximum content length. None = no limit (default).
                               GPT-4o has 128K token context, so we can handle large docs.
        """
        parts = [f"[Document: {self.title}]"]
        if self.source_type:
            parts.append(f"Type: {self.source_type}")
        if self.sender:
            parts.append(f"From: {self.sender}")
        if self.created_at:
            parts.append(f"Date: {self.created_at}")
        if self.project_name:
            parts.append(f"Project: {self.project_name}")

        # Use full content by default - no artificial truncation
        content = self.content
        if max_content_length and len(content) > max_content_length:
            content = content[:max_content_length]

        parts.append(f"Content:\n{content}")
        return "\n".join(parts)


@dataclass
class ProjectGoal:
    """Result of Stage 1: Goal and Technical Context Extraction."""
    primary_goal: str
    technical_stack: List[str] = field(default_factory=list)
    integrations: List[str] = field(default_factory=list)
    context: str = ""


@dataclass
class Decision:
    """A key technical decision extracted from documents."""
    decision_type: str  # architecture, integration, data, infrastructure, security
    description: str  # What was decided
    evidence: str  # Quote or reference from document
    impact: str  # Why this decision matters technically


@dataclass
class Alternative:
    """An inferred alternative for a technical decision."""
    decision_description: str
    alternative: str
    why_not_obvious: str  # Why this isn't an obvious question


@dataclass
class TechnicalQuestion:
    """A generated question about a technical decision."""
    question: str
    decision_context: str
    why_new_employee_needs: str
    priority: int  # 1-5
    category: str  # architecture, integration, data, infrastructure, security


@dataclass
class GoalFirstAnalysisResult:
    """Complete result of technical analysis."""
    project_goal: ProjectGoal
    decisions: List[Decision]
    alternatives: List[Alternative]
    questions: List[TechnicalQuestion]
    analysis_metadata: Dict[str, Any] = field(default_factory=dict)


class GoalFirstGapAnalyzer:
    """
    Technical Knowledge Gap Analyzer.

    This analyzer focuses ONLY on technical questions:
    - Architecture decisions (frameworks, patterns, libraries)
    - Integration decisions (APIs, third-party services)
    - Data decisions (database, schema, data flow)
    - Infrastructure decisions (deployment, hosting, scaling)
    - Security decisions (authentication, authorization, encryption)
    """

    # Stage 1: Technical Context Extraction
    STAGE_1_PROMPT = """You are analyzing project documents to understand the TECHNICAL CONTEXT.

DOCUMENTS:
{documents}

Extract ONLY technical information:
1. PRIMARY GOAL: What is this project trying to build? (technical description)
2. TECHNICAL STACK: What technologies, frameworks, libraries are mentioned?
3. INTEGRATIONS: What external services, APIs, or systems does this integrate with?
4. CONTEXT: What is the technical architecture or system design?

Focus ONLY on technical aspects. Ignore business strategy, timelines, budgets.

Respond in JSON:
{{
    "primary_goal": "Technical description of what is being built",
    "technical_stack": ["Framework 1", "Database", "Library X"],
    "integrations": ["External API 1", "Service X", "Platform Y"],
    "context": "Technical architecture context"
}}"""

    # Stage 2: Technical Decision Extraction
    STAGE_2_PROMPT = """You are identifying KEY TECHNICAL DECISIONS made in this project.

PROJECT: {goal}

DOCUMENTS:
{documents}

Find ONLY TECHNICAL decisions. Look for:

1. ARCHITECTURE DECISIONS: Framework/pattern choices
   - "Using Flask instead of FastAPI"
   - "Chose microservices over monolith"
   - "REST API vs GraphQL"
   - "MVC pattern"

2. INTEGRATION DECISIONS: External service choices
   - "Integrated with Salesforce"
   - "Using AWS S3 for storage"
   - "Azure OpenAI for LLM"
   - "OAuth 2.0 for authentication"

3. DATA DECISIONS: Database and data model choices
   - "PostgreSQL instead of MongoDB"
   - "Normalized vs denormalized schema"
   - "Redis for caching"
   - "Vector database for embeddings"

4. INFRASTRUCTURE DECISIONS: Deployment and hosting
   - "Docker containerization"
   - "Kubernetes orchestration"
   - "AWS vs Azure vs GCP"

5. SECURITY DECISIONS: Auth and security choices
   - "JWT vs session tokens"
   - "HIPAA compliance approach"
   - "Encryption at rest"

IGNORE: Business strategy, timelines, budgets, organizational politics.

Respond in JSON:
{{
    "decisions": [
        {{
            "decision_type": "architecture|integration|data|infrastructure|security",
            "description": "What technical decision was made",
            "evidence": "Quote or reference from document",
            "impact": "Why this matters technically"
        }}
    ]
}}"""

    # Stage 3: Technical Alternative Inference
    STAGE_3_PROMPT = """You are inferring what TECHNICAL ALTERNATIVES might have existed.

PROJECT: {goal}

TECHNICAL DECISIONS MADE:
{decisions}

For each decision, infer:
1. What technical alternatives could have been chosen?
2. Why would a developer ask about this choice?

ONLY include technical alternatives like:
- Different frameworks (Flask vs FastAPI vs Django)
- Different databases (PostgreSQL vs MongoDB vs MySQL)
- Different APIs (REST vs GraphQL vs gRPC)
- Different cloud services (AWS vs Azure vs GCP)
- Different architectural patterns (microservices vs monolith)

Respond in JSON:
{{
    "alternatives": [
        {{
            "decision_description": "The technical decision",
            "alternative": "What technical alternative could have been chosen",
            "why_not_obvious": "Why this technical choice matters for a new developer"
        }}
    ]
}}"""

    # Stage 4: Technical Question Generation
    STAGE_4_PROMPT = """You are generating TECHNICAL questions for a DEPARTING EMPLOYEE to answer.

PROJECT: {goal}

TECHNICAL DECISIONS AND ALTERNATIVES:
{decisions_and_alternatives}

Generate ONLY TECHNICAL questions that a NEW DEVELOPER would need answered.

GOOD QUESTION TYPES:
- "Why Flask over FastAPI for this project?"
- "Why PostgreSQL instead of a NoSQL database?"
- "What's the authentication flow and why this approach?"
- "Why this specific API integration pattern?"
- "How does the data flow between services?"
- "Why this caching strategy?"
- "What's the deployment architecture?"

BAD QUESTIONS (DO NOT GENERATE):
- Business strategy questions
- Timeline/deadline questions
- Budget/resource questions
- Organizational/political questions
- "Why was this project started?"
- "Who approved this?"

For each question, explain WHY a new developer needs this to maintain/extend the code.

Respond in JSON:
{{
    "questions": [
        {{
            "question": "Specific technical question",
            "decision_context": "What technical decision this relates to",
            "why_new_employee_needs": "Why a developer needs this to work on the codebase",
            "priority": 1-5,
            "category": "architecture|integration|data|infrastructure|security"
        }}
    ]
}}

Generate 5-15 high-quality TECHNICAL questions. Quality over quantity."""

    def __init__(self, client=None):
        """Initialize the Technical Gap Analyzer."""
        if client:
            self.client = client
        else:
            self.client = get_openai_client()

    def analyze(
        self,
        documents: List[DocumentContext],
        max_docs_per_stage: int = 30,
        temperature: float = 0.3
    ) -> GoalFirstAnalysisResult:
        """
        Run the 4-stage technical analysis.

        Args:
            documents: List of DocumentContext objects
            max_docs_per_stage: Maximum documents per stage
            temperature: LLM temperature

        Returns:
            GoalFirstAnalysisResult with technical decisions and questions
        """
        logger.info(f"Starting technical analysis on {len(documents)} documents")

        # Prepare document text
        doc_text = self._prepare_documents(documents, max_docs_per_stage)

        # Stage 1: Technical Context Extraction
        logger.info("Stage 1: Technical Context Extraction")
        project_goal = self._run_stage_1(doc_text, temperature)

        # Stage 2: Technical Decision Extraction
        logger.info("Stage 2: Technical Decision Extraction")
        decisions = self._run_stage_2(project_goal, doc_text, temperature)

        # Stage 3: Technical Alternative Inference
        logger.info("Stage 3: Technical Alternative Inference")
        alternatives = self._run_stage_3(project_goal, decisions, temperature)

        # Stage 4: Technical Question Generation
        logger.info("Stage 4: Technical Question Generation")
        questions = self._run_stage_4(project_goal, decisions, alternatives, temperature)

        result = GoalFirstAnalysisResult(
            project_goal=project_goal,
            decisions=decisions,
            alternatives=alternatives,
            questions=questions,
            analysis_metadata={
                "documents_analyzed": len(documents),
                "analysis_timestamp": datetime.utcnow().isoformat(),
                "stages_completed": 4
            }
        )

        logger.info(f"Analysis complete: {len(questions)} technical questions generated")
        return result

    def _prepare_documents(self, documents: List[DocumentContext], max_docs: int) -> str:
        """Prepare documents for LLM consumption."""
        selected = documents[:max_docs]
        return "\n\n---\n\n".join([
            doc.to_analysis_text() for doc in selected
        ])

    def _call_llm(self, prompt: str, system_message: str, temperature: float) -> Dict[str, Any]:
        """Call LLM and parse JSON response."""
        try:
            response = self.client.chat_completion(
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=4000,
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return {}

    def _run_stage_1(self, documents: str, temperature: float) -> ProjectGoal:
        """Run Stage 1: Technical Context Extraction."""
        prompt = self.STAGE_1_PROMPT.format(documents=documents)

        result = self._call_llm(
            prompt,
            "You are a senior software architect analyzing technical documentation. Focus ONLY on technical details. Respond only with valid JSON.",
            temperature
        )

        return ProjectGoal(
            primary_goal=result.get("primary_goal", ""),
            technical_stack=result.get("technical_stack", []),
            integrations=result.get("integrations", []),
            context=result.get("context", "")
        )

    def _run_stage_2(
        self,
        goal: ProjectGoal,
        documents: str,
        temperature: float
    ) -> List[Decision]:
        """Run Stage 2: Technical Decision Extraction."""
        prompt = self.STAGE_2_PROMPT.format(
            goal=goal.primary_goal,
            documents=documents
        )

        result = self._call_llm(
            prompt,
            "You are a senior software architect identifying technical decisions. Focus ONLY on technical choices. Respond only with valid JSON.",
            temperature
        )

        decisions = []
        for d in result.get("decisions", []):
            decisions.append(Decision(
                decision_type=d.get("decision_type", "architecture"),
                description=d.get("description", ""),
                evidence=d.get("evidence", ""),
                impact=d.get("impact", "")
            ))

        return decisions

    def _run_stage_3(
        self,
        goal: ProjectGoal,
        decisions: List[Decision],
        temperature: float
    ) -> List[Alternative]:
        """Run Stage 3: Technical Alternative Inference."""
        decisions_text = "\n".join([
            f"- [{d.decision_type.upper()}] {d.description}"
            for d in decisions
        ])

        prompt = self.STAGE_3_PROMPT.format(
            goal=goal.primary_goal,
            decisions=decisions_text
        )

        result = self._call_llm(
            prompt,
            "You are a senior software architect analyzing technical alternatives. Respond only with valid JSON.",
            temperature
        )

        alternatives = []
        for a in result.get("alternatives", []):
            alternatives.append(Alternative(
                decision_description=a.get("decision_description", ""),
                alternative=a.get("alternative", ""),
                why_not_obvious=a.get("why_not_obvious", "")
            ))

        return alternatives

    def _run_stage_4(
        self,
        goal: ProjectGoal,
        decisions: List[Decision],
        alternatives: List[Alternative],
        temperature: float
    ) -> List[TechnicalQuestion]:
        """Run Stage 4: Technical Question Generation."""
        # Combine decisions and alternatives
        combined = []
        for d in decisions:
            combined.append(f"DECISION: {d.description}")
            combined.append(f"  Type: {d.decision_type}")
            combined.append(f"  Impact: {d.impact}")

            # Find matching alternatives
            for a in alternatives:
                if d.description.lower() in a.decision_description.lower():
                    combined.append(f"  Alternative: {a.alternative}")
                    combined.append(f"  Why ask: {a.why_not_obvious}")
            combined.append("")

        prompt = self.STAGE_4_PROMPT.format(
            goal=goal.primary_goal,
            decisions_and_alternatives="\n".join(combined)
        )

        result = self._call_llm(
            prompt,
            "You are a senior software architect generating technical questions for knowledge transfer. Generate ONLY technical questions. Respond only with valid JSON.",
            temperature
        )

        questions = []
        for q in result.get("questions", []):
            questions.append(TechnicalQuestion(
                question=q.get("question", ""),
                decision_context=q.get("decision_context", ""),
                why_new_employee_needs=q.get("why_new_employee_needs", ""),
                priority=min(max(q.get("priority", 3), 1), 5),
                category=q.get("category", "architecture")
            ))

        # Sort by priority
        questions.sort(key=lambda q: q.priority, reverse=True)

        return questions

    def to_knowledge_gaps(
        self,
        result: GoalFirstAnalysisResult,
        project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Convert analysis result to knowledge gap format for database.

        Groups questions by technical category.
        """
        gaps = []

        # Group questions by category
        by_category: Dict[str, List[TechnicalQuestion]] = {}
        for q in result.questions:
            if q.category not in by_category:
                by_category[q.category] = []
            by_category[q.category].append(q)

        category_titles = {
            "architecture": "Architecture & Framework",
            "integration": "API & Integrations",
            "data": "Data & Database",
            "infrastructure": "Infrastructure & Deployment",
            "security": "Security & Authentication"
        }

        for category, questions in by_category.items():
            title = category_titles.get(category, f"{category.title()} Technical")
            gap = {
                "title": title,
                "description": f"Technical questions about {category} decisions. Stack: {', '.join(result.project_goal.technical_stack[:5])}",
                "category": "technical",
                "priority": max(q.priority for q in questions),
                "questions": [
                    {
                        "text": q.question,
                        "answered": False,
                        "priority": q.priority,
                        "reasoning": q.why_new_employee_needs,
                        "related_entities": [],
                        "answerable_by": ["Tech Lead", "Senior Developer", "Departing Employee"]
                    }
                    for q in questions
                ],
                "context": {
                    "project_goal": result.project_goal.primary_goal,
                    "technical_stack": result.project_goal.technical_stack,
                    "integrations": result.project_goal.integrations,
                    "analysis_timestamp": result.analysis_metadata.get("analysis_timestamp"),
                    "documents_analyzed": result.analysis_metadata.get("documents_analyzed"),
                    "source": "technical_analysis"
                },
                "project_id": project_id
            }
            gaps.append(gap)

        return gaps
