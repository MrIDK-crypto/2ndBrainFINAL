# 2nd Brain - Known Issues & Technical Debt

Last Updated: 2025-12-18

## Critical Issues (Must Fix Before Production)

### ~~0. RAG DATA LOSS - 8K Embedding Truncation~~
**Status:** ✅ FIXED (Phase 1) - 2025-12-09
**Location:** `vector_stores/pinecone_store.py`

**Problem (was):**
- Only first 8,000 chars embedded in Pinecone
- Content after 8K was completely unfindable via search

**Fix Applied:**
- Removed 8K truncation
- Documents now chunked into 2000 char pieces with 400 char overlap
- Sentence-aware splitting to avoid mid-sentence breaks
- 30K safety limit (text-embedding-3-large has 8K token limit ≈ 32K chars)
- All chunks embedded with proper metadata

**Files Modified:**
- `vector_stores/pinecone_store.py` - New `_chunk_text()` method, updated `embed_and_upsert_documents()`
- `services/embedding_service.py` - Explicit chunk params

### ~~1. TOKEN BOMB - Knowledge Gap Analysis~~
**Status:** ✅ FIXED (Phases 2 & 3) - 2025-12-09
**Location:** `services/knowledge_service.py`, `services/extraction_service.py`

**Problem (was):**
- Full document content sent to GPT for gap analysis
- 50 docs × 100K chars = 5M chars (way over 128K token limit)

**Fix Applied (Phase 2 - Pre-extraction):**
- New `services/extraction_service.py` extracts structured summaries during sync
- Uses gpt-4o-mini for cost efficiency
- Extracts: summary, key_topics, entities, decisions, processes, dates, action_items, technical_details
- Added `structured_summary` and `structured_summary_at` columns to Document model

**Fix Applied (Phase 3 - Use summaries in gap analysis):**
- `analyze_gaps()` now uses `_prepare_documents_for_analysis()` helper
- Prefers structured_summary (compact) over raw content
- Token budgeting: 400K char limit (~100K tokens)
- Prioritizes recent documents if over budget
- Falls back gracefully to truncated raw content for docs without summaries
- `analyze_gaps_multistage()` and `analyze_gaps_goalfirst()` also updated

**Files Modified:**
- `database/models.py` - Added structured_summary columns
- `services/extraction_service.py` - NEW FILE
- `api/integration_routes.py` - Integrated extraction into sync flow
- `services/knowledge_service.py` - Uses summaries, token budgeting

### ~~1.5. ENHANCED RAG - Missing Features from EnhancedRAGv2~~
**Status:** ✅ FIXED - 2025-12-09
**Location:** `services/enhanced_search_service.py`, `app_v2.py`

**Problem (was):**
- `app_v2.py` had code to load EnhancedRAGv2 but NEVER CALLED IT
- Search endpoint used basic Pinecone hybrid_search directly
- Missing: reranking, query expansion, MMR, hallucination detection
- Only 5 chunks × 500 chars used for context (2,500 chars total)

**Fix Applied - Ported EnhancedRAGv2 features to Pinecone:**

| Feature | Before | After |
|---------|--------|-------|
| Query Expansion | ❌ None | ✅ 100+ acronyms (ROI, NICU, etc.) |
| Cross-Encoder Reranking | ❌ None | ✅ ms-marco-MiniLM-L-12-v2 |
| MMR Diversity | ❌ None | ✅ Adaptive lambda (0.7 default) |
| Hallucination Detection | ❌ None | ✅ Claim extraction + verification |
| Citation Enforcement | ❌ Weak prompt | ✅ Strict rules + coverage check |
| Freshness Scoring | ❌ None | ✅ Boost recent documents |
| Context for Answer | 5 × 500 chars | 15 × 3000 chars |

**Files Created/Modified:**
- `services/enhanced_search_service.py` - NEW FILE with all features
- `app_v2.py` - Updated `/api/search` to use enhanced service

**API Response Now Includes:**
```json
{
  "query_type": "enhanced_rag",
  "expanded_query": "ROI (Return on Investment) for NICU (Neonatal Intensive Care Unit)",
  "features_used": {
    "expansion": true,
    "reranking": true,
    "mmr": true,
    "freshness": true
  },
  "hallucination_check": {
    "verified": 5,
    "total_claims": 6,
    "confidence": 0.83
  },
  "citation_coverage": 0.92
}
```

**Fallback:** Pass `{"enhanced": false}` to use basic search for comparison.

---

### 1.6. INTELLIGENT GAP DETECTION v2.0 - Advanced NLP
**Status:** UPDATED - 2025-12-18
**Location:** `services/intelligent_gap_detector.py`, `services/knowledge_service.py`

**Problem (was):**
- Gap analysis was pure GPT prompting (black box)
- Generic questions not grounded in specific evidence
- No pattern-based detection
- No entity relationship analysis
- No bus factor risk detection
- No contradiction detection across documents

**Solution: Multi-Layer NLP Architecture (v2.0)**

```
Layer 1: Frame-Based Extraction (150+ triggers)
    - DECISION frames (what, who_decided, why, alternatives)
    - PROCESS frames (what, steps, owner, frequency)
    - DEFINITION frames (term, meaning, context)
    - EVENT frames (what_happened, when, who_involved)
    - CONSTRAINT frames (what, why, source)
    - METRIC frames (what, value, target)
    - PROBLEM frames (what, impact, solution) - NEW
    - OWNERSHIP frames (what, who, backup) - NEW

Layer 2: Semantic Role Labeling (SRL)
    - ARG0 (Agent): Who performed the action?
    - ARG1 (Patient): What was affected?
    - ARGM-CAU (Cause): Why it happened?
    - ARGM-MNR (Manner): How it was done?
    - ARGM-TMP (Temporal): When?

Layer 3: Discourse Analysis
    - Unsupported claims detection
    - Results without causes
    - Claims without evidence

Layer 4: Knowledge Graph + Entity Normalization
    - Entity extraction (PERSON, SYSTEM, ORG, PROCESS)
    - Entity normalization (John = John Smith = J. Smith)
    - Relation extraction (OWNS, MANAGES, USES, DEPENDS_ON)
    - Missing relation detection
    - Isolated entity detection
    - Bus factor risk analysis

Layer 5: Cross-Document Verification
    - Numeric contradiction detection
    - Negation contradiction detection
    - Semantic contradiction detection (better/worse, increase/decrease)
    - Single-source knowledge risks

Layer 6: Grounded Question Generation
    - Evidence-based questions
    - Priority scoring
    - Quality scoring (0-1)
    - Fingerprint-based deduplication
```

**v2.0 Improvements:**

| Feature | v1.0 | v2.0 |
|---------|------|------|
| Trigger Patterns | ~50 | 150+ |
| Entity Normalization | No | Yes (John = J. Smith) |
| Coreference Resolution | No | Yes (rule-based) |
| Negation Handling | No | Yes |
| Contradiction Types | 1 | 3 (numeric, negation, semantic) |
| Gap Deduplication | No | Yes (fingerprints) |
| Quality Scoring | No | Yes (0-1 score) |
| spaCy | Optional | Required (Python 3.12) |

**Gap Detection Patterns (Extended):**

| Pattern | Description | Example |
|---------|-------------|---------|
| MISSING_RATIONALE | Decision without "why" | "We switched to Postgres" |
| MISSING_AGENT | Passive voice without actor | "It was decided that..." |
| MISSING_TIMELINE | Vague temporal reference | "Eventually we'll migrate" |
| UNDEFINED_MODIFIER | Ambiguous qualifier | "Significantly improved" |
| PERSON_AS_KNOWLEDGE | Knowledge locked in person | "Ask John, he knows" |
| BUS_FACTOR_RISK | Single person owns 3+ systems | "Sarah manages X, Y, Z" |
| UNSUPPORTED_CLAIM | Assertion without evidence | "This is better because..." |
| CONTRADICTION | Conflicting information | Doc A: "10 users" vs Doc B: "50 users" |
| IMPLICIT_PROCESS | Undocumented procedure | "The usual way" |
| ASSUMED_CONTEXT | Missing background | "As you know" |
| EXTERNAL_DEPENDENCY | Undocumented dependency | "Depends on John's approval" |

**User Feedback System (NEW):**

```bash
# Submit feedback on gap usefulness
POST /api/knowledge/gaps/{gap_id}/feedback
{
    "useful": true | false,
    "comment": "Optional explanation"
}

# Get gap statistics including feedback
GET /api/knowledge/gaps/stats
```

**Database Schema Updates:**
```python
# KnowledgeGap model (database/models.py)
feedback_useful = Column(Integer, default=0)
feedback_not_useful = Column(Integer, default=0)
feedback_comments = Column(JSON, default=list)
quality_score = Column(Float, default=0.0)
fingerprint = Column(String(32), index=True)
```

**Usage:**
```python
from services.knowledge_service import KnowledgeService

service = KnowledgeService(db)
result = service.analyze_gaps_intelligent(
    tenant_id="...",
    project_id=None,  # All projects
    max_documents=100
)

# Result includes:
# - gaps: List of detected gaps with grounded questions
# - categories_found: Gaps by category
# - context.stats: Detection statistics
# - context.quality_score: Gap quality (0-1)
# - context.fingerprint: For deduplication
```

**API Endpoints:**
```bash
# Run intelligent analysis (now default)
POST /api/knowledge/analyze
{
    "mode": "intelligent",  # Now the default mode
    "project_id": null
}

# Submit feedback
POST /api/knowledge/gaps/{id}/feedback
{
    "useful": true,
    "comment": "Very relevant question!"
}

# Get statistics
GET /api/knowledge/gaps/stats
```

**Files Created/Modified:**
- `services/intelligent_gap_detector.py` - v2.0 (2000 lines)
  - `EntityNormalizer` - NEW: Name normalization
  - `CoreferenceResolver` - NEW: Rule-based coref
  - `FrameExtractor` - Enhanced with negation handling
  - `SemanticRoleAnalyzer` - Layer 2
  - `DiscourseAnalyzer` - Layer 3
  - `KnowledgeGraphBuilder` - Layer 4 with normalization
  - `CrossDocumentVerifier` - Enhanced contradiction detection
  - `GroundedQuestionGenerator` - Quality scoring + dedup
  - `IntelligentGapDetector` - Main orchestrator
- `services/knowledge_service.py` - `analyze_gaps_intelligent()` method
- `database/models.py` - Feedback fields on KnowledgeGap
- `api/knowledge_routes.py` - Feedback + stats endpoints

**Dependencies (REQUIRED):**
```bash
# spaCy is REQUIRED for NLP processing
# Use Python 3.12 (spaCy incompatible with Python 3.14)

# Option 1: Create venv with Python 3.12
/opt/homebrew/bin/python3.12 -m venv venv312
source venv312/bin/activate
pip install spacy
python -m spacy download en_core_web_sm

# Option 2: Install in existing Python 3.12
pip install spacy
python -m spacy download en_core_web_sm
```

**Python Version Note:**
- spaCy is incompatible with Python 3.14 due to pydantic.v1 issues
- Use Python 3.12 or 3.13 for the backend
- A venv312 virtual environment has been created in the backend folder

**Research Foundations:**
- Frame Semantics (FrameNet, Baker et al.)
- Semantic Role Labeling (AllenNLP, PropBank)
- Argument Mining (Stab & Gurevych, 2017)
- Rhetorical Structure Theory (Mann & Thompson)
- Knowledge Graph Completion (TransE/RotatE)
- Entity Resolution (string similarity, clustering)

**Comparison with Previous Modes:**

| Feature | Simple | MultiStage | GoalFirst | Intelligent v2 |
|---------|--------|------------|-----------|----------------|
| GPT Calls | 1 | 5 | 4 | 0 |
| Pattern Detection | No | No | No | Yes (150+) |
| Entity Extraction | No | Partial | No | Yes (KG) |
| Entity Normalization | No | No | No | Yes |
| Coreference | No | No | No | Yes |
| Bus Factor Risk | No | No | No | Yes |
| Contradiction Check | No | No | No | Yes (3 types) |
| Grounded Evidence | No | Partial | Partial | Yes |
| Cross-Doc Analysis | No | No | No | Yes |
| Deduplication | No | No | No | Yes |
| Quality Scoring | No | No | No | Yes |
| User Feedback | No | No | No | Yes |
| Estimated Accuracy | ~40% | ~60% | ~55% | ~80-85% |

---

### ~~2. MEMORY BOMB - Excel Parsing~~
**Status:** ✅ FIXED - 2026-01-28
**Location:** `parsers/document_parser.py` line 181-215

**Problem (was):**
- Removed 100-row limit, processed ALL rows
- 500K row Excel → entire file loaded into memory as strings
- Then concatenated into one giant text blob
- Sent to embedding API (which has limits)

**Fix Applied:**
- Added MAX_ROWS_PER_SHEET = 10,000 limit per sheet
- Stops processing at limit with clear break condition
- Adds warning message to content when truncated
- Metadata includes truncated_sheets list for transparency

**Impact:** Prevents server crashes on large Excel files while still processing reasonable amounts of data

---

### ~~3. SECURITY - Multi-Tenant Header Spoofing~~
**Status:** ✅ FIXED - 2026-01-29
**Location:** `app_v2.py`, `middleware/rate_limit.py`, `tests/test_tenant_isolation.py`

**Problem (was):**
```python
tenant_id = payload.get("tenant_id")  # From JWT ✅
if not tenant_id:
    tenant_id = request.headers.get("X-Tenant")  # ❌ SPOOFABLE
```

**Attack Vector (was):**
```bash
curl -H "X-Tenant: victim-tenant-id" /api/documents
```

**Fix Applied:**
1. ✅ Removed X-Tenant header fallback from `app_v2.py`
2. ✅ Removed X-Tenant from CORS allowed headers
3. ✅ Added comprehensive tenant isolation tests (`tests/test_tenant_isolation.py`)
4. ✅ Implemented per-tenant rate limiting (`middleware/rate_limit.py`)
5. ✅ Added tier-based rate limits (Free, Starter, Professional, Enterprise)

**Security Enhancements:**
- JWT-only authentication (no header spoofing possible)
- Rate limiting per tenant (prevent abuse)
- Comprehensive test coverage (11 security tests)
- Tests cover: JWT validation, document isolation, gap isolation, connector isolation, attack scenarios

**Files Created:**
- `middleware/rate_limit.py` - Rate limiting middleware with tier-based limits
- `middleware/__init__.py` - Middleware module exports
- `tests/test_tenant_isolation.py` - 11 security tests for multi-tenant isolation
- `tests/__init__.py` - Tests module init

**Files Modified:**
- `app_v2.py` - Removed X-Tenant fallback, updated CORS headers

---

## High Severity Issues

### 4. LlamaParse GPT-4o Mode - UNTESTED
**Status:** 🟠 HIGH - UNFIXED
**Location:** `parsers/llamaparse_parser.py`, `config/config.py`

**Problem:**
- Added `gpt4o_mode=True` but never tested
- May require premium LlamaParse subscription
- Free tier: NO gpt4o_mode support
- No fallback if GPT-4o mode fails
- No cost tracking (3-5x more expensive)

**Action Required:** Test with actual LlamaParse account, verify plan supports it

---

### 5. Box Sync - No Incremental Sync
**Status:** 🟠 HIGH - UNFIXED
**Location:** `connectors/box_connector.py`

**Problem:**
- Every sync downloads ALL files (even unchanged)
- Re-parses ALL files (expensive LlamaParse calls)
- Re-embeds ALL documents (expensive OpenAI calls)
- No change detection

**Cost Impact:** 100 files × 5 syncs = 500 unnecessary LlamaParse calls

**Missing:**
- File hash/etag comparison
- Last modified timestamp check
- Incremental sync logic

---

### ~~6. RAG - No Re-embedding on Changes~~
**Status:** ✅ FIXED - Already Implemented
**Location:** `services/embedding_service.py`, `vector_stores/pinecone_store.py`, `api/document_routes.py`

**Problem (was):**
- Document deleted → DB row deleted → Pinecone vectors REMAIN (orphaned)
- Document updated → Old embeddings persist → Stale search results

**Fix Applied:**
- ✅ Cascade delete to Pinecone on document deletion (both soft and hard)
- ✅ Batch delete support for bulk operations
- ✅ Database flags cleared (`embedded_at=None, embedding_generated=False`)
- ✅ External ID tracking to prevent re-sync of deleted documents
- ✅ Graceful error handling (continues if Pinecone fails)

**Implementation:**
```python
# Single delete: DELETE /api/documents/<id>?hard=true
# Bulk delete: POST /api/documents/bulk/delete
embedding_service.delete_document_embeddings(doc_ids, tenant_id, db)
  → vector_store.delete_documents()  # Delete from Pinecone
  → Document.update(embedded_at=None)  # Clear DB flags
  → DeletedDocument.create()  # Track external_id
```

---

### ~~7. Knowledge Gap Deduplication - NONE~~
**Status:** ✅ FIXED - 2025-12-18
**Location:** `services/intelligent_gap_detector.py`, `database/models.py`

**Problem (was):**
- User clicks "Find Gaps" → 20 gaps created
- User clicks again → 20 MORE duplicate gaps
- 10 clicks → 200 duplicate gaps

**Fix Applied:**
- Fingerprint-based deduplication using MD5 hash of (category + normalized question + evidence)
- `fingerprint` column added to KnowledgeGap model with index
- Gaps with identical fingerprints are merged, not duplicated
- Quality scores aggregated across duplicate detections

---

## Medium Severity Issues

### 8. No Background Job Queue
**Status:** 🟡 MEDIUM - UNFIXED
**Location:** System-wide

**Problem:**
- Sync, embedding, gap analysis run synchronously
- HTTP request hangs for 30+ minutes on large datasets
- Browser times out, user thinks it failed

**Missing:**
- Celery/RQ job queue
- Progress tracking
- Webhook/polling for completion

---

### 9. No Retry Logic
**Status:** 🟡 MEDIUM - UNFIXED
**Location:** System-wide

**Problem:**
- OpenAI 429 (rate limit) → immediate FAIL
- Pinecone timeout → immediate FAIL
- No retries, no exponential backoff, no circuit breaker

---

### 10. SQLite in Production
**Status:** 🟡 MEDIUM - UNFIXED
**Location:** `database/models.py`

**Problem:**
- All tenants in single SQLite file
- Concurrent writes → potential locks
- No connection pooling
- Not horizontally scalable

**For Production:** Migrate to PostgreSQL

---

## Fixed Issues

### ✅ Character Caps in Knowledge Gap Prompts
**Fixed:** 2025-12-09
**Location:** `services/knowledge_service.py`, `services/goal_first_analyzer.py`, `services/multistage_gap_analyzer.py`
**Note:** Caps removed but token bomb issue created (see #1)

### ✅ Excel 100-Row Limit
**Fixed:** 2025-12-09
**Location:** `parsers/document_parser.py`
**Note:** Limit removed but memory bomb issue created (see #2) - LATER RE-FIXED with 10K limit (2026-01-28)

### ✅ Database Performance Indexes
**Fixed:** 2026-01-28
**Location:** `database/models.py`
**Details:** Added 4 new indexes on Document table:
- ix_document_sender: Speeds up sender_email queries
- ix_document_embedded: Speeds up embedding status checks
- ix_document_confidence: Speeds up sorting by classification confidence
- ix_document_created: Speeds up date-based queries

### ✅ Frontend Document Fetch Optimization
**Fixed:** 2026-01-28
**Location:** `frontend/components/documents/Documents.tsx`
**Details:** Reduced document fetch limit from 500 to 50
- Reduces initial JSON response size from ~2.5MB to ~250KB
- Prevents browser lag on large datasets
- Note: Pagination still needed for full document list access

### ✅ Box SDK Installation
**Fixed:** 2025-12-09
**Note:** `pip install box-sdk-gen`

### ✅ bcrypt Module Missing
**Fixed:** 2025-12-09
**Note:** `pip install bcrypt`

---

## Architecture Decisions

### Token Limits Reference
- GPT-4o: 128K tokens (~500K chars input)
- GPT-4o-mini: 128K tokens
- text-embedding-3-large: 8K tokens per request
- LlamaParse: Varies by plan

### Cost Reference (Approximate)
- GPT-4o: $5/1M input tokens, $15/1M output tokens
- GPT-4o-mini: $0.15/1M input, $0.60/1M output
- text-embedding-3-large: $0.13/1M tokens
- LlamaParse: $0.003/page (standard), $0.01/page (premium/gpt4o)
- Pinecone: $0.33/GB storage, queries included

---

## Priority Order for Fixes

### Before Demo/Beta:
1. ✅ Token bomb fix (smart sampling for gap analysis) - FIXED 2025-12-09
2. ✅ Excel memory fix (add limits back with warning) - FIXED 2026-01-28
3. Multi-tenant security fix (remove header spoofing)
4. Test LlamaParse gpt4o_mode

### Performance Improvements (Partially Complete):
- ✅ Database indexes added (2026-01-28)
- ✅ Frontend fetch limit reduced (2026-01-28)
- ⚠️ Pagination still needed for documents page
- ⚠️ Background jobs still needed for long-running operations

### Before Production:
5. Background job queue (Celery/RQ)
6. Incremental Box sync
7. ✅ Pinecone cleanup on delete - Already Implemented
8. ✅ Gap deduplication - FIXED 2025-12-18
9. Retry logic

### For Scale:
10. PostgreSQL migration
11. Caching layer
12. Rate limiting per tenant
13. Cost tracking/billing

---

## Implementation Plan: Unified Content Fix (2025-12-09)

### Overview
Fix both RAG data loss (8K truncation) and Knowledge Gap token bomb with unified approach:
1. Proper chunking - embed ALL content
2. Pre-extraction - structured summaries during sync
3. Smart gap analysis - use summaries instead of full content

### Phase 1: Fix RAG Chunking ✅ COMPLETE
**Goal:** Embed 100% of document content, not just first 8K

**Files modified:**
- `vector_stores/pinecone_store.py` - New `_chunk_text()`, updated embedding
- `services/embedding_service.py` - Explicit chunk params

**Changes:**
1. ✅ Removed `text[:8000]` truncation before embedding
2. ✅ Chunk ENTIRE document first, then embed each chunk
3. ✅ Use 2000 char chunks with 400 char overlap (better accuracy)
4. ✅ Sentence-aware splitting to avoid mid-sentence breaks
5. ✅ Fixed infinite loop bug in chunking

### Phase 2: Add Pre-Extraction During Sync ✅ COMPLETE
**Goal:** Extract structured summary from each document during sync

**Files modified:**
- `database/models.py` - Added `structured_summary`, `structured_summary_at` columns
- `api/integration_routes.py` - Integrated extraction into sync flow
- `services/extraction_service.py` - NEW FILE for extraction logic

**Schema added:**
```python
structured_summary = Column(JSON, nullable=True)
structured_summary_at = Column(DateTime(timezone=True))
# {
#   "summary": "2-3 sentence overview",
#   "key_topics": ["topic1", "topic2"],
#   "entities": {"people": [], "systems": [], "organizations": []},
#   "decisions": ["decision1"],
#   "processes": ["process1"],
#   "dates": [{"date": "2024-01-15", "event": "milestone"}],
#   "action_items": ["item1"],
#   "word_count": 5000,
#   "extracted_at": "2024-12-09T..."
# }
```

### Phase 3: Update Knowledge Gap Analysis ✅ COMPLETE
**Goal:** Use structured summaries instead of full content

**Files modified:**
- `services/knowledge_service.py` - Added helpers, updated all 3 analyzers

**Changes:**
1. ✅ Added `_prepare_document_for_analysis()` helper - uses summary when available
2. ✅ Added `_prepare_documents_for_analysis()` helper - token budgeting
3. ✅ Updated `analyze_gaps()` to use helpers
4. ✅ Updated `analyze_gaps_multistage()` to use summaries in DocumentContext
5. ✅ Updated `analyze_gaps_goalfirst()` to use summaries in GFDocumentContext
6. ✅ Prioritizes recent documents if over budget
7. ✅ Falls back to truncated raw content for docs without summaries

---

## How to Test (Manual)

### Test Phase 1 (RAG Chunking)
```bash
# 1. Sync a large document (>8K chars) from Box
# 2. Search for content that appears AFTER the 8K mark in the document
# 3. Should now return results (before: no results)

# Check logs for chunking:
# "[Pinecone] Created N chunks for document X"
```

### Test Phase 2 (Pre-Extraction)
```bash
# 1. Sync new documents from Box
# 2. Check logs for:
#    "[ExtractionService] Extracting: DocTitle..."
#    "[ExtractionService] Extracted N topics, M decisions"

# 3. Verify in database:
sqlite3 knowledge_vault.db "SELECT id, title, structured_summary FROM documents LIMIT 5"
# Should see JSON in structured_summary column
```

### Test Phase 3 (Knowledge Gap Analysis)
```bash
# 1. Run gap analysis via API or UI
# 2. Check logs for:
#    "[KnowledgeGap] Document preparation stats:"
#    "  - Documents with SUMMARY: N"

# 3. Should complete without token error even with 200+ docs
# 4. Questions should be relevant (referencing actual content)
```

### Configuration (Current)
```python
# Chunk settings (pinecone_store.py)
CHUNK_SIZE = 2000  # chars per chunk
CHUNK_OVERLAP = 400  # overlap between chunks

# Extraction settings (extraction_service.py)
EXTRACTION_MODEL = "gpt-4o-mini"  # Cheaper for bulk extraction
MAX_EXTRACTION_CONTENT = 50000  # Max chars to send for extraction

# Gap analysis settings (knowledge_service.py)
MAX_GAP_ANALYSIS_CHARS = 400000  # ~100K tokens max
```
