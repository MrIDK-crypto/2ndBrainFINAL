"""
Multi-Stage LLM Gap Analyzer
Advanced knowledge gap detection using multi-stage reasoning.

This module implements a 5-stage LLM reasoning pipeline that generates
intelligent, context-aware questions based on corpus understanding.

Stages:
1. Corpus Understanding - Build mental model of all documents
2. Expert Mind Simulation - What an expert knows but didn't write
3. New Hire Simulation - Where would a new person get stuck
4. Failure Mode Analysis - What happens when things break
5. Question Synthesis - Generate specific, actionable questions

Designed for B2B SaaS: tenant-agnostic, scalable, universal.
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
class CorpusUnderstanding:
    """Result of Stage 1: Corpus Understanding."""
    key_entities: List[Dict[str, Any]] = field(default_factory=list)
    projects: List[Dict[str, Any]] = field(default_factory=list)
    people: List[Dict[str, Any]] = field(default_factory=list)
    technologies: List[str] = field(default_factory=list)
    processes: List[str] = field(default_factory=list)
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    domain_context: str = ""
    organizational_structure: str = ""
    raw_summary: str = ""


@dataclass
class ExpertInsight:
    """Result of Stage 2: Expert Mind Simulation."""
    tacit_knowledge_gaps: List[str] = field(default_factory=list)
    tribal_knowledge: List[str] = field(default_factory=list)
    unwritten_assumptions: List[str] = field(default_factory=list)
    expertise_areas: List[str] = field(default_factory=list)
    implicit_decisions: List[str] = field(default_factory=list)


@dataclass
class NewHireBlockers:
    """Result of Stage 3: New Hire Simulation."""
    context_gaps: List[str] = field(default_factory=list)
    vocabulary_terms: List[str] = field(default_factory=list)
    relationship_gaps: List[str] = field(default_factory=list)
    process_gaps: List[str] = field(default_factory=list)
    tool_knowledge_gaps: List[str] = field(default_factory=list)
    onboarding_blockers: List[str] = field(default_factory=list)


@dataclass
class FailureModeInsight:
    """Result of Stage 4: Failure Mode Analysis."""
    documented_procedures: List[str] = field(default_factory=list)
    missing_recovery_steps: List[str] = field(default_factory=list)
    edge_cases: List[str] = field(default_factory=list)
    escalation_gaps: List[str] = field(default_factory=list)
    undocumented_workarounds: List[str] = field(default_factory=list)


@dataclass
class SynthesizedQuestion:
    """A synthesized knowledge gap question."""
    question: str
    category: str  # decision, technical, process, context, relationship, timeline, outcome, rationale
    priority: int  # 1-5
    reasoning: str  # Why this question matters
    source_stage: str  # Which stage generated this
    related_entities: List[str] = field(default_factory=list)
    answerable_by: List[str] = field(default_factory=list)  # Roles who can answer


@dataclass
class MultiStageAnalysisResult:
    """Complete result of multi-stage gap analysis."""
    corpus_understanding: CorpusUnderstanding
    expert_insights: ExpertInsight
    new_hire_blockers: NewHireBlockers
    failure_modes: FailureModeInsight
    synthesized_questions: List[SynthesizedQuestion]
    analysis_metadata: Dict[str, Any] = field(default_factory=dict)


class MultiStageGapAnalyzer:
    """
    Multi-Stage LLM Gap Analyzer for intelligent knowledge gap detection.

    This analyzer processes an entire document corpus through 5 stages
    of LLM reasoning to generate highly contextual, actionable questions
    that capture tacit knowledge before employee transitions.

    Features:
    - Tenant-agnostic design for B2B SaaS
    - Batched processing for large corpora
    - Configurable prompts for different industries
    - Deduplication of similar questions
    - Priority scoring based on business impact
    """

    # Stage 1: Corpus Understanding Prompt
    STAGE_1_PROMPT = """You are a knowledge analyst examining a corpus of organizational documents.

Your task is to build a comprehensive mental model of this organization by analyzing all provided documents.

DOCUMENTS:
{documents}

Analyze these documents and extract:

1. KEY ENTITIES: Important people, teams, systems, products mentioned
2. PROJECTS: Active or completed projects, initiatives, workstreams
3. PEOPLE: Key individuals and their apparent roles/responsibilities
4. TECHNOLOGIES: Tools, platforms, systems, technologies in use
5. PROCESSES: Business processes, workflows, procedures mentioned
6. TIMELINE: Key dates, milestones, phases mentioned
7. RELATIONSHIPS: How entities relate to each other (reports to, depends on, etc.)
8. DOMAIN CONTEXT: What industry/domain is this? What kind of work?
9. ORGANIZATIONAL STRUCTURE: How is the organization structured?

Respond in JSON:
{{
    "key_entities": [
        {{"name": "...", "type": "person|team|system|product|client", "importance": 1-5, "context": "..."}}
    ],
    "projects": [
        {{"name": "...", "status": "active|completed|planned", "key_people": [...], "description": "..."}}
    ],
    "people": [
        {{"name": "...", "role": "...", "team": "...", "responsibilities": [...]}}
    ],
    "technologies": ["..."],
    "processes": ["..."],
    "timeline": [
        {{"date": "...", "event": "...", "significance": "..."}}
    ],
    "relationships": [
        {{"from": "...", "to": "...", "relationship_type": "...", "context": "..."}}
    ],
    "domain_context": "Brief description of the organization's domain and work",
    "organizational_structure": "Description of org structure based on evidence",
    "raw_summary": "3-4 paragraph comprehensive summary of everything learned"
}}"""

    # Stage 2: Expert Mind Simulation Prompt - WORK-FOCUSED
    STAGE_2_PROMPT = """You are simulating the mind of a departing employee who has been doing this work for years.

Based on this understanding of their work:
{corpus_understanding}

And these documents:
{documents_sample}

Focus on WORK-SPECIFIC knowledge that would be lost if this person left tomorrow. NOT organizational politics or history - focus on the actual WORK.

1. TACIT WORKFLOW KNOWLEDGE: How they actually do their job
   - Shortcuts and tricks that make tasks faster
   - The real sequence of steps (not the documented one)
   - Who to CC on what types of emails
   - Which meetings actually matter vs which can be skipped

2. PROJECT-SPECIFIC CONTEXT: Knowledge about current/recent projects
   - Current status of each active project
   - Blockers and dependencies not in any tracker
   - Stakeholder preferences and communication styles
   - Deadlines that aren't official but everyone knows

3. TROUBLESHOOTING KNOWLEDGE: What to do when things break
   - Common issues and their fixes
   - Early warning signs of problems
   - Who to call for different types of issues
   - Workarounds for known system limitations

4. RELATIONSHIP KNOWLEDGE: Working effectively with others
   - Preferred contact methods for key people
   - Who influences decisions (not org chart)
   - External contacts (clients, vendors, partners)
   - Which approvals actually matter

5. IN-PROGRESS WORK: Things currently being worked on
   - Half-finished tasks and their status
   - Pending decisions awaiting input
   - Commitments made to others
   - Things promised but not yet started

Focus on knowledge that would cause REAL PROBLEMS if lost - things a replacement needs to know to continue the work.

Respond in JSON:
{{
    "tacit_knowledge_gaps": ["Specific workflow knowledge not documented - how tasks actually get done..."],
    "tribal_knowledge": ["Project-specific context that isn't in any document..."],
    "unwritten_assumptions": ["Things the replacement would get wrong without being told..."],
    "expertise_areas": ["Troubleshooting and specialized work knowledge..."],
    "implicit_decisions": ["In-progress work and pending commitments..."]
}}"""

    # Stage 3: New Hire Simulation Prompt
    STAGE_3_PROMPT = """You are a new employee on your first week at this organization.

You've been given access to these documents and this organizational context:
{corpus_understanding}

Sample documents you've read:
{documents_sample}

As a new hire, identify where you would get STUCK or CONFUSED:

1. CONTEXT GAPS: "I don't understand WHY we do this..."
   - Missing historical context
   - Unclear motivations behind current practices
   - References to past events you don't know about

2. VOCABULARY TERMS: "What does [X] mean in this context?"
   - Acronyms that aren't defined
   - Internal jargon and terminology
   - Names that mean nothing to you

3. RELATIONSHIP GAPS: "Who should I talk to about [X]?"
   - Unclear reporting structures
   - Unknown stakeholders for different topics
   - Missing escalation paths

4. PROCESS GAPS: "How do I actually DO this?"
   - Steps that are skipped in documentation
   - Assumed knowledge about procedures
   - Missing handoff points

5. TOOL KNOWLEDGE GAPS: "How do I use [system/tool]?"
   - Systems mentioned but not explained
   - Configuration details not documented
   - Access and permissions unclear

6. ONBOARDING BLOCKERS: Critical things that would slow down a new hire
   - Information they need on day 1 that's hard to find
   - Dependencies that aren't obvious
   - Setup/access requirements that aren't listed

Respond in JSON:
{{
    "context_gaps": ["Things a new hire wouldn't understand WHY..."],
    "vocabulary_terms": ["Undefined terms and jargon..."],
    "relationship_gaps": ["Unclear ownership and responsibilities..."],
    "process_gaps": ["Undocumented procedural steps..."],
    "tool_knowledge_gaps": ["Tool/system knowledge that's assumed..."],
    "onboarding_blockers": ["Critical gaps for new hire success..."]
}}"""

    # Stage 4: Failure Mode Analysis Prompt
    STAGE_4_PROMPT = """You are a systems reliability engineer analyzing this organization's documentation for failure handling gaps.

Organizational context:
{corpus_understanding}

Sample documents:
{documents_sample}

Analyze what happens when things GO WRONG:

1. DOCUMENTED PROCEDURES: What failure scenarios ARE documented?
   - Error handling that's explicitly covered
   - Known issue workarounds that are written down

2. MISSING RECOVERY STEPS: What failures have NO documented recovery?
   - Systems that could fail but have no runbook
   - Processes that could break with no backup plan
   - Data issues with no resolution path

3. EDGE CASES: What unusual situations are not accounted for?
   - Timing edge cases (midnight, holidays, etc.)
   - Scale edge cases (too many, too few, etc.)
   - Combination scenarios not covered

4. ESCALATION GAPS: Who do you call when things break?
   - Missing on-call information
   - Unclear severity levels
   - Unknown decision-makers for crisis situations

5. UNDOCUMENTED WORKAROUNDS: Known issues with tribal knowledge fixes
   - "Everyone knows you just restart the service"
   - Manual interventions that happen regularly
   - Temporary fixes that became permanent

Respond in JSON:
{{
    "documented_procedures": ["Failure scenarios that ARE covered..."],
    "missing_recovery_steps": ["Failures with no documented recovery..."],
    "edge_cases": ["Unusual situations not accounted for..."],
    "escalation_gaps": ["Missing escalation information..."],
    "undocumented_workarounds": ["Known workarounds not in docs..."]
}}"""

    # Stage 5: Question Synthesis Prompt - FOCUSED ON TACIT KNOWLEDGE EXTRACTION
    STAGE_5_PROMPT = """You are preparing knowledge transfer questions for a departing employee. Your goal is to extract TACIT KNOWLEDGE that would be LOST if they leave without documenting it.

CRITICAL: This is NOT about organizational decisions or tool choices. This is about extracting the knowledge in someone's HEAD that they use every day to do their job but never wrote down.

You have analyzed their documentation:

CORPUS UNDERSTANDING:
{corpus_understanding}

EXPERT INSIGHTS (what's in their head but not written):
{expert_insights}

NEW HIRE BLOCKERS (what a replacement would struggle with):
{new_hire_blockers}

FAILURE MODES (what breaks and how to fix it):
{failure_modes}

Generate questions that extract PROJECT-SPECIFIC TACIT KNOWLEDGE:

GOOD QUESTIONS (examples of what we want):
- "For the [specific project], what are the next 3 steps that need to happen and who is waiting on them?"
- "Walk me through exactly how you [do specific task] - not the documented way, the real way."
- "What are the unwritten rules about working with [specific client/stakeholder]?"
- "If [specific system] breaks, what's the first thing you check that isn't in any runbook?"
- "Who should I actually talk to about [specific topic], not who's officially responsible?"
- "What would go wrong if [specific task/project] wasn't handed off properly?"
- "What have you learned about [specific project] that surprised you or wasn't obvious at first?"

BAD QUESTIONS (DO NOT generate these):
- "Why was [tool X] selected over [tool Y]?" - USELESS, doesn't help with work
- "What is the organizational structure?" - Too generic
- "What are the company values?" - Not actionable
- "How did the team get started?" - Historical, not operational

QUESTION CATEGORIES:
- PROCESS: "How do you actually do [X]?" - The real workflow, shortcuts, gotchas
- RELATIONSHIP: "Who do you talk to for [X]?" - Key contacts, stakeholders, influencers
- CONTEXT: "What should I know about [X] that isn't documented?" - Hidden context
- TECHNICAL: "How does [X] actually work?" - Implementation details, quirks
- TIMELINE: "What needs to happen by when for [X]?" - Deadlines, dependencies
- OUTCOME: "What happens if [X] goes wrong?" - Consequences, recovery
- DECISION: "What's currently being decided about [X]?" - Open decisions, not past ones
- RATIONALE: "Why do we do [X] this way instead of the obvious way?" - Workarounds, learned lessons

RULES FOR EVERY QUESTION:
1. MUST reference a specific project, system, person, or task from the documents
2. MUST be something a replacement would need to know to do the job
3. MUST be answerable only by someone with hands-on experience
4. MUST NOT be about tool selection, organizational history, or company strategy
5. MUST help someone take over the actual WORK, not understand the company

Respond in JSON:
{{
    "questions": [
        {{
            "question": "Project-specific question about work that needs to continue...",
            "category": "process|relationship|context|technical|timeline|outcome|decision|rationale",
            "priority": 1-5,
            "reasoning": "What would be lost if this isn't answered - be specific",
            "source_stage": "corpus|expert|newhire|failure",
            "related_entities": ["Specific project", "Specific person", "Specific system"],
            "answerable_by": ["Person with this specific experience"]
        }}
    ]
}}

Generate 12-20 high-quality questions.

PRIORITY SCORING:
5 = Work would STOP without this knowledge (critical handoff)
4 = Work would be significantly delayed or have errors
3 = Important context that prevents mistakes
2 = Nice to know, improves efficiency
1 = Background context

Focus on what would cause the MOST PROBLEMS if the employee left tomorrow without answering."""

    def __init__(self, client=None):
        """
        Initialize the Multi-Stage Gap Analyzer.

        Args:
            client: Optional OpenAI client wrapper. If not provided, creates one.
        """
        if client:
            self.client = client
        else:
            self.client = get_openai_client()

    def analyze(
        self,
        documents: List[DocumentContext],
        max_docs_per_stage: int = 30,
        temperature: float = 0.4
    ) -> MultiStageAnalysisResult:
        """
        Run the full 5-stage analysis on a document corpus.

        Args:
            documents: List of DocumentContext objects to analyze
            max_docs_per_stage: Maximum documents to include per stage
            temperature: LLM temperature for generation

        Returns:
            MultiStageAnalysisResult with all stages and synthesized questions
        """
        logger.info(f"Starting multi-stage analysis on {len(documents)} documents")

        # Prepare document text
        full_doc_text = self._prepare_documents(documents, max_docs_per_stage)
        sample_doc_text = self._prepare_documents(documents[:min(10, len(documents))], 10)

        # Stage 1: Corpus Understanding
        logger.info("Stage 1: Corpus Understanding")
        corpus_understanding = self._run_stage_1(full_doc_text, temperature)

        # Stage 2: Expert Mind Simulation
        logger.info("Stage 2: Expert Mind Simulation")
        expert_insights = self._run_stage_2(
            corpus_understanding, sample_doc_text, temperature
        )

        # Stage 3: New Hire Simulation
        logger.info("Stage 3: New Hire Simulation")
        new_hire_blockers = self._run_stage_3(
            corpus_understanding, sample_doc_text, temperature
        )

        # Stage 4: Failure Mode Analysis
        logger.info("Stage 4: Failure Mode Analysis")
        failure_modes = self._run_stage_4(
            corpus_understanding, sample_doc_text, temperature
        )

        # Stage 5: Question Synthesis
        logger.info("Stage 5: Question Synthesis")
        synthesized_questions = self._run_stage_5(
            corpus_understanding, expert_insights,
            new_hire_blockers, failure_modes, temperature
        )

        # Build result
        result = MultiStageAnalysisResult(
            corpus_understanding=corpus_understanding,
            expert_insights=expert_insights,
            new_hire_blockers=new_hire_blockers,
            failure_modes=failure_modes,
            synthesized_questions=synthesized_questions,
            analysis_metadata={
                "documents_analyzed": len(documents),
                "analysis_timestamp": datetime.utcnow().isoformat(),
                "stages_completed": 5
            }
        )

        logger.info(f"Analysis complete: {len(synthesized_questions)} questions generated")
        return result

    def _prepare_documents(
        self,
        documents: List[DocumentContext],
        max_docs: int
    ) -> str:
        """Prepare documents for LLM consumption."""
        selected = documents[:max_docs]
        return "\n\n---\n\n".join([
            doc.to_analysis_text() for doc in selected
        ])

    def _call_llm(
        self,
        prompt: str,
        system_message: str,
        temperature: float
    ) -> Dict[str, Any]:
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

    def _run_stage_1(
        self,
        documents: str,
        temperature: float
    ) -> CorpusUnderstanding:
        """Run Stage 1: Corpus Understanding."""
        prompt = self.STAGE_1_PROMPT.format(documents=documents)

        result = self._call_llm(
            prompt,
            "You are an expert knowledge analyst. Respond only with valid JSON.",
            temperature
        )

        return CorpusUnderstanding(
            key_entities=result.get("key_entities", []),
            projects=result.get("projects", []),
            people=result.get("people", []),
            technologies=result.get("technologies", []),
            processes=result.get("processes", []),
            timeline=result.get("timeline", []),
            relationships=result.get("relationships", []),
            domain_context=result.get("domain_context", ""),
            organizational_structure=result.get("organizational_structure", ""),
            raw_summary=result.get("raw_summary", "")
        )

    def _run_stage_2(
        self,
        corpus_understanding: CorpusUnderstanding,
        documents_sample: str,
        temperature: float
    ) -> ExpertInsight:
        """Run Stage 2: Expert Mind Simulation."""
        # Summarize corpus understanding for prompt
        corpus_summary = json.dumps({
            "domain": corpus_understanding.domain_context,
            "key_entities": corpus_understanding.key_entities[:10],
            "projects": corpus_understanding.projects[:5],
            "technologies": corpus_understanding.technologies[:10],
            "summary": corpus_understanding.raw_summary
        }, indent=2)

        prompt = self.STAGE_2_PROMPT.format(
            corpus_understanding=corpus_summary,
            documents_sample=documents_sample
        )

        result = self._call_llm(
            prompt,
            "You are simulating an expert with years of institutional knowledge. Respond only with valid JSON.",
            temperature
        )

        return ExpertInsight(
            tacit_knowledge_gaps=result.get("tacit_knowledge_gaps", []),
            tribal_knowledge=result.get("tribal_knowledge", []),
            unwritten_assumptions=result.get("unwritten_assumptions", []),
            expertise_areas=result.get("expertise_areas", []),
            implicit_decisions=result.get("implicit_decisions", [])
        )

    def _run_stage_3(
        self,
        corpus_understanding: CorpusUnderstanding,
        documents_sample: str,
        temperature: float
    ) -> NewHireBlockers:
        """Run Stage 3: New Hire Simulation."""
        corpus_summary = json.dumps({
            "domain": corpus_understanding.domain_context,
            "org_structure": corpus_understanding.organizational_structure,
            "people": corpus_understanding.people[:10],
            "processes": corpus_understanding.processes[:10]
        }, indent=2)

        prompt = self.STAGE_3_PROMPT.format(
            corpus_understanding=corpus_summary,
            documents_sample=documents_sample
        )

        result = self._call_llm(
            prompt,
            "You are a confused new employee trying to understand the organization. Respond only with valid JSON.",
            temperature
        )

        return NewHireBlockers(
            context_gaps=result.get("context_gaps", []),
            vocabulary_terms=result.get("vocabulary_terms", []),
            relationship_gaps=result.get("relationship_gaps", []),
            process_gaps=result.get("process_gaps", []),
            tool_knowledge_gaps=result.get("tool_knowledge_gaps", []),
            onboarding_blockers=result.get("onboarding_blockers", [])
        )

    def _run_stage_4(
        self,
        corpus_understanding: CorpusUnderstanding,
        documents_sample: str,
        temperature: float
    ) -> FailureModeInsight:
        """Run Stage 4: Failure Mode Analysis."""
        corpus_summary = json.dumps({
            "technologies": corpus_understanding.technologies,
            "processes": corpus_understanding.processes,
            "projects": [p.get("name") for p in corpus_understanding.projects[:10]]
        }, indent=2)

        prompt = self.STAGE_4_PROMPT.format(
            corpus_understanding=corpus_summary,
            documents_sample=documents_sample
        )

        result = self._call_llm(
            prompt,
            "You are a reliability engineer analyzing failure modes. Respond only with valid JSON.",
            temperature
        )

        return FailureModeInsight(
            documented_procedures=result.get("documented_procedures", []),
            missing_recovery_steps=result.get("missing_recovery_steps", []),
            edge_cases=result.get("edge_cases", []),
            escalation_gaps=result.get("escalation_gaps", []),
            undocumented_workarounds=result.get("undocumented_workarounds", [])
        )

    def _run_stage_5(
        self,
        corpus_understanding: CorpusUnderstanding,
        expert_insights: ExpertInsight,
        new_hire_blockers: NewHireBlockers,
        failure_modes: FailureModeInsight,
        temperature: float
    ) -> List[SynthesizedQuestion]:
        """Run Stage 5: Question Synthesis."""
        # Prepare summaries
        corpus_summary = f"""
Domain: {corpus_understanding.domain_context}
Organization: {corpus_understanding.organizational_structure}
Key Projects: {', '.join(p.get('name', '') for p in corpus_understanding.projects[:10])}
Technologies: {', '.join(corpus_understanding.technologies[:15])}
Key People: {', '.join(p.get('name', '') + ' (' + p.get('role', '') + ')' for p in corpus_understanding.people[:10])}
Summary: {corpus_understanding.raw_summary[:1000]}
"""

        expert_summary = f"""
Tacit Knowledge Gaps:
{chr(10).join('- ' + g for g in expert_insights.tacit_knowledge_gaps[:10])}

Tribal Knowledge:
{chr(10).join('- ' + k for k in expert_insights.tribal_knowledge[:10])}

Unwritten Assumptions:
{chr(10).join('- ' + a for a in expert_insights.unwritten_assumptions[:10])}

Implicit Decisions:
{chr(10).join('- ' + d for d in expert_insights.implicit_decisions[:10])}
"""

        newhire_summary = f"""
Context Gaps:
{chr(10).join('- ' + g for g in new_hire_blockers.context_gaps[:10])}

Undefined Terms:
{chr(10).join('- ' + t for t in new_hire_blockers.vocabulary_terms[:10])}

Process Gaps:
{chr(10).join('- ' + p for p in new_hire_blockers.process_gaps[:10])}

Onboarding Blockers:
{chr(10).join('- ' + b for b in new_hire_blockers.onboarding_blockers[:10])}
"""

        failure_summary = f"""
Missing Recovery Steps:
{chr(10).join('- ' + s for s in failure_modes.missing_recovery_steps[:10])}

Edge Cases:
{chr(10).join('- ' + e for e in failure_modes.edge_cases[:10])}

Escalation Gaps:
{chr(10).join('- ' + g for g in failure_modes.escalation_gaps[:10])}

Undocumented Workarounds:
{chr(10).join('- ' + w for w in failure_modes.undocumented_workarounds[:10])}
"""

        prompt = self.STAGE_5_PROMPT.format(
            corpus_understanding=corpus_summary,
            expert_insights=expert_summary,
            new_hire_blockers=newhire_summary,
            failure_modes=failure_summary
        )

        result = self._call_llm(
            prompt,
            "You are a knowledge transfer specialist. Generate specific, high-impact questions. Respond only with valid JSON.",
            temperature
        )

        questions = []
        for q in result.get("questions", []):
            questions.append(SynthesizedQuestion(
                question=q.get("question", ""),
                category=q.get("category", "context"),
                priority=min(max(q.get("priority", 3), 1), 5),
                reasoning=q.get("reasoning", ""),
                source_stage=q.get("source_stage", "synthesis"),
                related_entities=q.get("related_entities", []),
                answerable_by=q.get("answerable_by", [])
            ))

        # Sort by priority (highest first)
        questions.sort(key=lambda q: q.priority, reverse=True)

        return questions

    def to_knowledge_gaps(
        self,
        result: MultiStageAnalysisResult,
        project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Convert analysis result to knowledge gap format for database storage.

        Args:
            result: MultiStageAnalysisResult from analyze()
            project_id: Optional project ID to associate gaps with

        Returns:
            List of gap dictionaries ready for database insertion
        """
        gaps = []

        # Group questions by category for better organization
        by_category: Dict[str, List[SynthesizedQuestion]] = {}
        for q in result.synthesized_questions:
            if q.category not in by_category:
                by_category[q.category] = []
            by_category[q.category].append(q)

        for category, questions in by_category.items():
            # Create one gap per category with multiple questions
            gap = {
                "title": f"{category.title()} Knowledge Gap",
                "description": f"Questions about {category} knowledge identified through multi-stage analysis.",
                "category": category,
                "priority": max(q.priority for q in questions),
                "questions": [
                    {
                        "text": q.question,
                        "answered": False,
                        "priority": q.priority,
                        "reasoning": q.reasoning,
                        "related_entities": q.related_entities,
                        "answerable_by": q.answerable_by
                    }
                    for q in questions
                ],
                "context": {
                    "corpus_summary": result.corpus_understanding.raw_summary[:500],
                    "analysis_timestamp": result.analysis_metadata.get("analysis_timestamp"),
                    "documents_analyzed": result.analysis_metadata.get("documents_analyzed"),
                    "source": "multi_stage_llm_analysis"
                },
                "project_id": project_id
            }
            gaps.append(gap)

        return gaps
