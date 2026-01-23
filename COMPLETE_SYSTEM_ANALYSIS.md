# Second Brain Codebase: Complete Analysis

## Executive Summary

The Second Brain system is an enterprise knowledge management platform that integrates multiple data sources, automatically identifies knowledge gaps, and generates training materials. It uses a sophisticated multi-layer architecture combining:

- **9+ Data Integrations** (both implemented and UI-ready)
- **Advanced Knowledge Gap Detection** (multi-stage NLP-powered analysis)
- **AI-Generated Training Videos & Presentations** (Gamma API integration)
- **Voice Transcription & Answering** (Azure Whisper)
- **Intelligent Search & RAG** (Pinecone vector database)

---

## 1. ALL INTEGRATIONS AVAILABLE

### 1.1 IMPLEMENTED INTEGRATIONS (Backend + Frontend)

#### 1. **Slack** 
- **Type**: OAuth-based token integration
- **Connector**: `/backend/connectors/slack_connector.py`
- **Frontend**: Token-based modal + channel selection
- **Data Extracted**:
  - Channel messages & threads
  - Direct messages
  - File shares & links
  - User mentions & relationships
- **Features**:
  - Real-time sync with configurable intervals
  - Channel filtering (select specific channels)
  - Threaded conversation capture
  - Settings: `channels[]`, `include_dms`, `include_threads`, `max_messages_per_channel`, `oldest_days`
- **Required Scopes**: `channels:read`, `channels:history`, `groups:read`, `groups:history`, `users:read`, `team:read`

#### 2. **Gmail**
- **Type**: OAuth2 (Google API)
- **Connector**: `/backend/connectors/gmail_connector.py`
- **Frontend**: Full OAuth flow
- **Data Extracted**:
  - Email content (subject + body)
  - Sender/recipient information
  - Thread context
  - Attachments metadata
  - Labels/folders
- **Features**:
  - Smart filtering by sender/subject
  - Label-based organization
  - Continuous sync for new emails
  - Settings: `max_results`, `labels[]`, `include_attachments`, `include_spam`, `query`
- **API Scope**: `https://www.googleapis.com/auth/gmail.readonly`

#### 3. **Box**
- **Type**: OAuth2 enterprise integration
- **Connector**: `/backend/connectors/box_connector.py`
- **Frontend**: Full OAuth flow
- **Data Extracted**:
  - Files & folders
  - Documents (PDF, Word, Excel, PowerPoint, etc.)
  - 100+ file type support
  - File versions
  - Comments & metadata
- **Features**:
  - Full and incremental sync
  - Content extraction (text, PDF, Office docs)
  - Folder filtering & exclusion
  - Webhook support for real-time updates
  - File size filtering (max 50MB default)
  - Settings: `root_folder_id`, `folder_ids[]`, `exclude_folders[]`, `file_extensions[]`, `max_file_size_mb`, `include_shared`, `include_trash`, `sync_comments`, `sync_versions`
- **Supported Files**: `.txt`, `.md`, `.csv`, `.json`, `.xml`, `.html`, `.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`, `.ppt`, `.pptx`, `.rtf`, `.odt`, `.ods`, `.odp`

#### 4. **GitHub**
- **Type**: OAuth2
- **Connector**: `/backend/connectors/github_connector.py`
- **Frontend**: UI available
- **Data Extracted**:
  - README files & documentation
  - Code comments
  - Issues & discussions
  - Pull request conversations
  - Repository wikis
- **Features**:
  - Technical knowledge capture
  - Development decision tracking
- **Supported Content**: Code, Documentation, Issues, Pull Requests, Wikis

### 1.2 PLANNED/UI-ONLY INTEGRATIONS (Frontend Ready, Backend Framework in Place)

#### 5. **Microsoft PowerPoint**
- **Status**: UI implemented, backend framework ready
- **Data Types**: Slides, Speaker Notes, Images, Charts
- **Features**:
  - Extract text from all slides
  - Capture speaker notes
  - Index embedded images and charts
  - Maintain slide structure
- **Setup**: Connect Microsoft 365 account → Select OneDrive folders → Choose files → Begin import

#### 6. **Microsoft Excel**
- **Status**: UI implemented, backend framework ready
- **Data Types**: Spreadsheets, Tables, Charts, Formulas
- **Features**:
  - Import spreadsheet data and tables
  - Preserve data relationships
  - Extract charts and visualizations
  - Support for complex workbooks
- **Setup**: Connect Microsoft 365 account → Select folders → Choose files → Configure import

#### 7. **PubMed**
- **Status**: UI implemented, backend framework ready
- **Data Types**: Papers, Abstracts, Citations, Authors, MeSH Terms
- **Features**:
  - Search 35+ million biomedical citations
  - Import full paper metadata & abstracts
  - Track citation relationships
  - Access MeSH term classifications
  - Free access (optional NCBI API key)
- **Setup**: Configure search queries → Select papers → Configure topics → Start literature sync

#### 8. **ResearchGate**
- **Status**: UI implemented, backend framework ready
- **Data Types**: Publications, Datasets, Preprints, Q&A, Profiles
- **Features**:
  - Import publications and papers
  - Access shared research datasets
  - Track research metrics and citations
  - Capture Q&A discussions
- **Setup**: Authenticate → Select publications → Configure datasets → Begin sync

#### 9. **Google Scholar**
- **Status**: UI implemented, backend framework ready
- **Data Types**: Papers, Theses, Books, Patents, Court Opinions
- **Features**:
  - Search across multiple disciplines
  - Import papers with full citations
  - Track citation counts & metrics
  - Access related articles and authors
  - Continuous monitoring
- **Setup**: Configure search preferences → Set topic alerts → Select papers → Enable monitoring

---

## 2. KNOWLEDGE TRANSFER WORKFLOW

### 2.1 Complete Data Flow Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: DATA INGESTION FROM INTEGRATIONS                    │
├─────────────────────────────────────────────────────────────┤
│ Slack/Gmail/Box/GitHub → Connector Sync → Raw Documents     │
│ └─ LlamaIndex/LlamaParse for PDF extraction                 │
│ └─ Automatic content parsing & cleanup                      │
│ └─ Metadata extraction (author, timestamp, source)          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: DOCUMENT PARSING & STORAGE                          │
├─────────────────────────────────────────────────────────────┤
│ Document Extraction Service (`document_parser.py`)          │
│ └─ Full-text extraction from PDFs/docs                      │
│ └─ Metadata enrichment                                      │
│ └─ Document classification (type, project, department)      │
│ └─ Storage in SQLite/PostgreSQL database                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: SEMANTIC EMBEDDING & INDEXING                       │
├─────────────────────────────────────────────────────────────┤
│ Embedding Service (`embedding_service.py`)                  │
│ └─ Azure OpenAI text-embedding-3-large model                │
│ └─ Chunk documents (token-aware chunking)                   │
│ └─ Upsert to Pinecone vector database                       │
│ └─ Create namespace per tenant for isolation                │
│ └─ Enable semantic search & RAG retrieval                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 4: INTELLIGENT GAP DETECTION                           │
├─────────────────────────────────────────────────────────────┤
│ Intelligent Gap Detector (`intelligent_gap_detector.py`)    │
│ Knowledge Gap v3 Orchestrator (`knowledge_gap_v3/`)         │
│ Multi-Stage Analyzer (`multistage_gap_analyzer.py`)         │
│                                                              │
│ 6-Layer Analysis:                                           │
│ ├─ Frame-Based Extraction (DECISION, PROCESS, etc.)        │
│ ├─ Semantic Role Labeling (missing agents, causes)          │
│ ├─ Discourse Analysis (unsupported claims)                  │
│ ├─ Knowledge Graph Analysis (missing relations)             │
│ ├─ Cross-Document Verification                              │
│ └─ Grounded Question Generation                             │
│                                                              │
│ NLP Techniques:                                              │
│ └─ spaCy NLP models for entity recognition                  │
│ └─ 150+ trigger patterns for gap detection                  │
│ └─ Entity normalization & coreference resolution            │
│ └─ Negation handling & contradiction detection              │
│ └─ Gap deduplication & quality scoring                      │
│                                                              │
│ Gap Categories Generated:                                   │
│ • MISSING_RATIONALE - Why decisions were made              │
│ • MISSING_AGENT - Who is responsible                        │
│ • MISSING_EVIDENCE - Unsupported claims                     │
│ • MISSING_DEFINITION - Undefined terms                      │
│ • MISSING_PROCESS - How things are done                     │
│ • MISSING_TIMELINE - When things happen                     │
│ • MISSING_IMPACT - Consequences not documented              │
│ • MISSING_ALTERNATIVE - Other options not explored          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 5: KNOWLEDGE GAP ANSWERING                             │
├─────────────────────────────────────────────────────────────┤
│ User/Expert Answers Questions:                              │
│ ├─ Web form submission                                      │
│ ├─ Voice transcription (Azure Whisper API)                  │
│ │  └─ Automatic speech-to-text                             │
│ │  └─ Language detection & confidence scoring               │
│ │  └─ Segment-level transcription                           │
│ └─ Stores to GapAnswer table in database                    │
│                                                              │
│ Answer Embedding:                                           │
│ └─ Immediately embed to Pinecone (no wait)                  │
│ └─ Makes answer searchable by chatbot instantly             │
│ └─ Format: "Q: [question]\nA: [answer]"                     │
│ └─ Metadata: gap_id, user_id, voice_flag, timestamp         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 6: TRAINING CONTENT GENERATION                         │
├─────────────────────────────────────────────────────────────┤
│ Training Guide Generation:                                  │
│ ├─ From Documents:                                          │
│ │  └─ Extract key sections                                  │
│ │  └─ Generate structured curriculum                        │
│ │  └─ Create learning objectives                            │
│ └─ From Knowledge Gaps:                                     │
│    └─ Questions + answers form modules                      │
│    └─ Organize by category/priority                         │
│    └─ Generate quiz content                                 │
│                                                              │
│ Training Video Generation:                                  │
│ ├─ PowerPoint Template Generation                           │
│ │  (`training_generator/generate_training_ppt.py`)          │
│ ├─ Slide Creation:                                          │
│ │  └─ Title slides                                          │
│ │  └─ Content slides (bulleted)                             │
│ │  └─ Section headers                                       │
│ │  └─ Summary slides                                        │
│ └─ Export as .pptx                                          │
│                                                              │
│ Gamma Presentation Generation:                              │
│ ├─ Gamma API Integration (`src/content_generation/`)        │
│ ├─ POST /v1.0/generations/from-template                     │
│ ├─ Payload:                                                 │
│ │  ├─ gammaId: Template ID                                  │
│ │  ├─ prompt: Content description                           │
│ │  └─ themeId: Design theme                                 │
│ ├─ Polling for completion                                   │
│ └─ Export as PDF or animated presentation                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 7: VIDEO/VOICEOVER GENERATION                          │
├─────────────────────────────────────────────────────────────┤
│ Video Service (`services/video_service.py`)                 │
│                                                              │
│ Input Sources:                                              │
│ ├─ Documents → Extract slides                               │
│ └─ Knowledge Gaps → Q&A format                              │
│                                                              │
│ Video Generation Steps:                                     │
│ ├─ Script Generation:                                       │
│ │  └─ Azure OpenAI summarization                            │
│ │  └─ Create speaker notes                                  │
│ ├─ Voiceover Generation:                                    │
│ │  └─ Azure Text-to-Speech (TTS)                            │
│ │  └─ Voice: en-US-JennyNeural (configurable)               │
│ │  └─ Professional audio quality                            │
│ ├─ Slide/Frame Generation:                                  │
│ │  └─ PIL (Python Imaging Library) for images               │
│ │  └─ 1920x1080 HD resolution                               │
│ │  └─ Custom branding colors                                │
│ ├─ Video Composition:                                       │
│ │  └─ MoviePy for video editing                             │
│ │  └─ ImageClip + AudioClip concatenation                   │
│ │  └─ Smooth transitions                                    │
│ │  └─ Duration: 24 FPS                                      │
│ └─ Output:                                                  │
│    └─ MP4 video file                                        │
│    └─ Progress tracking in database                         │
│    └─ URL in Video table                                    │
│                                                              │
│ Video Status Tracking:                                      │
│ ├─ "queued" → "processing" → "completed"/"error"           │
│ ├─ Progress updates (0-100%)                                │
│ └─ Background processing (doesn't block UI)                 │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 8: DEPLOYMENT & DELIVERY                               │
├─────────────────────────────────────────────────────────────┤
│ Training Materials:                                         │
│ ├─ Videos: Stored & streamed via URLs                       │
│ ├─ Presentations: PPTX downloads                            │
│ ├─ PDFs: Generated from Gamma presentations                 │
│ └─ Guides: HTML/web view                                    │
│                                                              │
│ Knowledge Retrieval (RAG):                                  │
│ ├─ User query → Embed with Azure OpenAI                     │
│ ├─ Search Pinecone (semantic similarity)                    │
│ ├─ Retrieve top-K relevant chunks                           │
│ ├─ Includes gap answers (due to embedding in step 5)        │
│ └─ LLM generates answer with context                        │
│                                                              │
│ Analytics:                                                  │
│ ├─ Track which videos watched                               │
│ ├─ Monitor gap answer submissions                           │
│ ├─ Measure training effectiveness                           │
│ └─ Feedback loops for improvement                           │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Key Data Models

#### Document Flow
```python
# From integrations
Document (
    id, tenant_id, source, source_id, title, content,
    metadata, classification, status, created_at
)

# To embeddings
Chunk (in Pinecone vector store):
    {
        'id': 'doc_uuid_chunk_0',
        'content': 'text chunk',
        'metadata': {
            'document_id': 'uuid',
            'source': 'slack|gmail|box',
            'tenant_id': 'uuid',
            'chunk_index': 0
        }
    }
```

#### Gap & Answer Flow
```python
KnowledgeGap (
    id, tenant_id, project_id, document_id,
    category, priority, description,
    status, confidence_score, created_at
)

GapAnswer (
    id, knowledge_gap_id,
    question_text, answer_text,
    user_id, is_voice_transcription,
    created_at
)
# → Immediately embedded to Pinecone as "gap_answer_*"
```

#### Video Flow
```python
Video (
    id, tenant_id, project_id,
    title, description, script,
    source_type, source_ids,
    status, progress_percent,
    voiceover_url, video_url,
    created_at, completed_at
)
```

---

## 3. VIDEO GENERATION FEATURE DETAILS

### 3.1 Azure Text-to-Speech Integration

**Configuration** (`services/video_service.py`):
```python
AZURE_TTS_KEY = os.getenv("AZURE_TTS_KEY")
AZURE_TTS_REGION = "eastus2"  # or from env
AZURE_TTS_VOICE = "en-US-JennyNeural"  # Professional female voice
```

**Features**:
- Professional-quality neural voices
- Multiple voice options available
- Configurable speech rate and pitch
- SSML support for advanced control
- Multi-language support

### 3.2 Gamma API Integration

**File**: `/backend/src/content_generation/gamma_presentation.py`

**Gamma API Credentials**:
```python
GAMMA_API_KEY = "sk-gamma-[key]"  # From Gamma.app
GAMMA_TEMPLATE_ID = "g_3g8gkijbwnm7wxk"
THEME_ID = "adfbsgcj2cfbfw6"
```

**Endpoints**:
- `POST /v1.0/generations/from-template` - Create presentation
- `GET /v1.0/generations/{generation_id}` - Check status

**Workflow**:
1. Send content prompt + template ID
2. Gamma generates presentation structure
3. Poll every 5 seconds for completion
4. Export as PDF or animated presentation
5. Store URL in Video database

**Example Content Template**:
```
PRESENTATION TITLE: [Title]
SUBTITLE: [Subtitle]

SECTIONS:
- Problem Statement: [Problems]
- Solution: [Solutions]
- Financial Impact: [ROI & Metrics]
- Implementation Timeline: [Timeline]
```

### 3.3 Video Output Specifications

**Resolution**: 1920x1080 (HD)
**Frame Rate**: 24 FPS
**Audio**: MP3 at 128kbps (from Azure TTS)
**Format**: MP4 (H.264)

**Color Scheme**:
- Background: Dark blue (Tailwind slate-900: #0F172A)
- Title: White (#FFFFFF)
- Content: Light gray (Tailwind slate-200: #E2E8F0)
- Accents: Blue (Tailwind blue-500: #3B82F6)

**Font Sizes**:
- Titles: 72pt
- Content: 48pt
- Fallback to system fonts if custom unavailable

### 3.4 Video Status Tracking

Frontend receives live updates via polling:
```python
GET /api/videos/{video_id}/status

Response:
{
    "status": "queued|processing|completed|error",
    "progress_percent": 0-100,
    "current_step": "script_generation|voiceover|video_composition|...",
    "estimated_completion": "2024-01-20T15:30:00Z"
}
```

---

## 4. KNOWLEDGE GAPS SYSTEM

### 4.1 Gap Detection Layers

**Layer 1: Frame-Based Extraction**
- Identifies frame types: DECISION, PROCESS, DEFINITION, EVENT, CONSTRAINT
- Extracts slots (required info): what, who, why, when, where
- Finds unfilled slots → gaps
- 150+ trigger patterns

**Layer 2: Semantic Role Labeling**
- Identifies agents (who), actions, beneficiaries
- Finds missing WHO, HOW, WHEN, WHERE
- Example: "System was implemented" (missing by whom, how, when)

**Layer 3: Discourse Analysis**
- Finds claims without supporting evidence
- Identifies unsupported assertions
- Example: "Performance improved 50%" (evidence missing)

**Layer 4: Knowledge Graph**
- Tracks entity relationships
- Finds missing entity connections
- Example: Person mentioned but role unclear

**Layer 5: Cross-Document Verification**
- Compares information across documents
- Finds contradictions
- Example: "Timeline varies between docs"

**Layer 6: Grounded Question Generation**
- Creates specific questions to fill gaps
- Grounds questions in document evidence
- Typically 3-5 questions per gap

### 4.2 Gap Detection Patterns

**Decision Gaps** (51+ triggers):
- `decided to`, `chose to`, `selected`, `adopted`, `migrated to`
- `settled on`, `agreed on`, `approved`, `ratified`, `confirmed`
- `pivoted to`, `switched to`, `transitioned to`, `upgraded to`
- Missing: Why made this decision, alternatives considered, impact

**Process Gaps** (30+ triggers):
- `process for`, `how to`, `procedure`, `workflow`, `steps to`
- `protocol for`, `guidelines for`, `checklist for`, `runbook for`
- `standard operating procedure`, `best practice`
- Missing: Detailed steps, responsibilities, exceptions

**Definition Gaps** (20+ triggers):
- `is defined as`, `means`, `refers to`, `known as`
- `technical term used for`, `abbreviation for`
- Missing: Context, examples, related terms

**Event/Timeline Gaps**:
- Missing: When events occur, duration, sequence

### 4.3 Gap Quality Scoring

Quality metrics (0-1 scale):
- **Confidence**: How certain is the gap real (based on NLP scores)
- **Relevance**: How important is the gap (based on patterns)
- **Actionability**: Can be answered (vs. unanswerable)
- **Deduplication**: Unique gaps (merged similar ones)

Fingerprint-based deduplication:
- Hash of gap type + description + entities
- Prevents duplicate gaps from same documents

### 4.4 Gap Answer Collection

**Methods**:
1. **Web Form**:
   - User types answer
   - Submit to `/api/knowledge/gaps/{gap_id}/answers`
   - Stores in GapAnswer table

2. **Voice Transcription**:
   - Record audio (WAV format)
   - Send to Azure Whisper API
   - Automatic transcription
   - User edits if needed
   - Submit as text answer

**Immediate Embedding**:
```python
# After answer submitted:
1. Create doc: {"id": "gap_answer_uuid", "content": "Q: [q]\nA: [a]"}
2. Embed with Azure text-embedding-3-large
3. Upsert to Pinecone (namespace: tenant_id)
4. Instantly searchable by chatbot RAG
```

---

## 5. TECHNICAL ARCHITECTURE

### 5.1 Backend Stack

**Framework**: Flask (Python web framework)
**Database**: SQLAlchemy ORM with PostgreSQL/SQLite
**Vector DB**: Pinecone (semantic search)
**LLM**: Azure OpenAI (gpt-4/gpt-5, embeddings, TTS)
**Speech**: Azure Whisper API (voice-to-text)
**Video**: MoviePy (video composition)
**NLP**: spaCy (entity recognition, tokenization)
**PDF Parsing**: LlamaIndex + LlamaParse

**Key Services**:
- `auth_service.py` - JWT authentication, multi-tenant isolation
- `embedding_service.py` - Document chunking & Pinecone upsertion
- `extraction_service.py` - PDF/doc content extraction
- `knowledge_service.py` - Gap analysis orchestration
- `video_service.py` - Video generation coordination
- `intelligent_gap_detector.py` - Advanced NLP gap detection
- `multistage_gap_analyzer.py` - 5-stage LLM reasoning
- `goal_first_analyzer.py` - Goal-oriented gap analysis

### 5.2 Frontend Stack

**Framework**: Next.js (React SSR)
**UI Library**: Tailwind CSS
**State Management**: React Context + localStorage
**HTTP Client**: Axios
**Components**: `/frontend/components/integrations/`

**Key Pages**:
- `/integrations` - Connect data sources
- `/documents` - Uploaded/synced documents
- `/knowledge-gaps` - Detected gaps + answering
- `/training-guides` - Generated training materials
- `/app/video-generation` - Create videos

### 5.3 Database Schema

**Core Tables** (in `database/models.py`):
```python
Tenant - Multi-tenancy isolation
User - User authentication
Connector - Integration credentials & status
Document - Parsed content from integrations
KnowledgeGap - Detected gaps
GapAnswer - User/expert answers
Video - Generated training videos
Project - Grouping for documents
```

**Unique Constraints**:
- `(tenant_id, connector_type)` for connectors
- `(tenant_id, source_id, source)` for documents
- Multi-tenant namespace in Pinecone

---

## 6. DATA FLOW EXAMPLES

### Example 1: Slack → Gaps → Video

```
1. User clicks "Sync" on Slack integration
2. Backend calls SlackConnector.sync()
3. Fetches messages from selected channels
4. Stores as Document records
5. Document Parser extracts text
6. Embedding Service chunks & embeds to Pinecone
7. Knowledge Gap Detection runs on new docs
8. Finds "Why was tool X chosen?" as gap
9. Generates 3 questions: "What were alternatives? Why better? Implementation cost?"
10. User answers via web form or voice
11. Answer embedded immediately
12. User creates video from gap + answers
13. Video Service:
    - Creates script from gap Q&A
    - Generates voiceover with Azure TTS
    - Renders slides with PIL
    - Composes video with MoviePy
    - Stores MP4 in storage
14. Video appears in training materials
```

### Example 2: Box Documents → Training Guide

```
1. User syncs Box folder with contracts
2. BoxConnector.sync() extracts PDFs
3. LlamaParse extracts structured text
4. Documents stored with metadata
5. Embeddings created for semantic search
6. Intelligent Gap Detector identifies:
   - "Payment terms not specified"
   - "Renewal conditions unclear"
   - "Default options for disputes missing"
7. Creates questions for legal team
8. Experts answer via web/voice
9. Answers embedded to Pinecone
10. Training Guide Generation:
    - Collects gap Q&As
    - Organizes by category (legal, terms, disputes)
    - Creates PPT structure
    - Sends to Gamma API for beautiful design
    - Exports PDF & PPTX
11. Training guide ready for new hires
```

---

## 7. CONFIGURATION & ENVIRONMENT VARIABLES

### Required Secrets
```bash
# Azure OpenAI
AZURE_OPENAI_ENDPOINT="https://[name].cognitiveservices.azure.com"
AZURE_OPENAI_API_KEY="[key]"
AZURE_API_VERSION="2024-12-01-preview"
AZURE_CHAT_DEPLOYMENT="gpt-5-chat"
AZURE_EMBEDDING_DEPLOYMENT="text-embedding-3-large"
AZURE_WHISPER_DEPLOYMENT="whisper"
AZURE_TTS_KEY="[key]"
AZURE_TTS_REGION="eastus2"
AZURE_TTS_VOICE="en-US-JennyNeural"

# Pinecone Vector DB
PINECONE_API_KEY="[key]"
PINECONE_ENVIRONMENT="[env]"
PINECONE_INDEX="[index_name]"

# Gmail OAuth
GOOGLE_CLIENT_ID="[id].apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET="[secret]"
GOOGLE_REDIRECT_URI="http://localhost:5003/api/integrations/gmail/callback"

# Box OAuth
BOX_CLIENT_ID="[id]"
BOX_CLIENT_SECRET="[secret]"
BOX_REDIRECT_URI="http://localhost:5003/api/integrations/box/callback"

# Slack
SLACK_CLIENT_ID="[id]"
SLACK_CLIENT_SECRET="[secret]"
SLACK_REDIRECT_URI="http://localhost:5003/api/integrations/slack/callback"

# Gamma Presentation API
GAMMA_API_KEY="sk-gamma-[key]"

# Database
DATABASE_URL="postgresql://user:pass@localhost:5432/secondbrain"

# JWT
JWT_SECRET_KEY="[random_secret]"
JWT_ALGORITHM="HS256"
```

---

## 8. SECURITY & MULTI-TENANCY

### Tenant Isolation

**Database Level**:
- All tables have `tenant_id` foreign key
- Queries always filter by `g.tenant_id`
- Row-level security enforced

**Vector DB Level**:
- Pinecone namespace = tenant_id
- Searches scoped to tenant namespace
- No cross-tenant data leakage

**OAuth Level**:
- JWT-based state tokens (stateless)
- No server-side state storage
- 10-minute expiration
- CSRF protection via state validation

### Credential Security

**Slack**:
- Token stored encrypted in DB
- Never logged or exposed in errors
- Validated before storage

**Gmail/Box**:
- Access token + refresh token stored
- Tokens rotated automatically
- Credentials isolated per tenant

---

## 9. PERFORMANCE & SCALING

### Rate Limiting
- Azure OpenAI: 3.5K req/min (gpt-4)
- Pinecone: 20K req/min
- Gmail API: 250 req/min
- Box API: 8 req/sec

### Batch Processing
- Document parsing: Batch of 10-50
- Embedding: Batch of 100 chunks
- Gap detection: Batch of 5-10 documents
- Video generation: Background thread queue

### Caching
- Embedding cache in memory (LRU)
- spaCy model loaded once at startup
- OAuth state tokens with TTL
- Connector status cached 5 minutes

---

## 10. LIMITATIONS & UNIMPLEMENTED

### UI-Only Integrations (Framework Ready)
- PubMed, ResearchGate, Google Scholar
- Frontend fully designed
- Backend framework exists
- Awaiting connector implementation

### Not Yet Implemented
- Webhooks for real-time sync (Slack, Box)
- Multi-account support per integration
- Incremental sync for all connectors
- Duplicate document detection
- Content moderation
- Access control per document

### Known Issues
- Large PDFs (>50MB) may timeout
- Gamma API rate limits (unknown)
- Azure Whisper latency for long audio (>30min)
- Video rendering slow on large files

---

## 11. QUICK START FOR DEVELOPMENT

### Install Dependencies
```bash
cd backend
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### Environment Setup
```bash
cp .env.template .env
# Fill in all Azure, Pinecone, OAuth credentials
```

### Run Backend
```bash
python app_v2.py  # Main Flask app
# Or: python api/app.py
```

### Run Frontend
```bash
cd frontend
npm install
npm run dev
# Accessible at http://localhost:3000
```

### Test Integration
```bash
# Slack OAuth callback
http://localhost:3000/integrations?success=slack

# Gmail OAuth callback
http://localhost:3000/integrations?success=gmail

# Create video
curl -X POST http://localhost:5003/api/videos \
  -H "Authorization: Bearer [token]" \
  -d '{"title": "Training", "source_type": "documents", "source_ids": ["id1"]}'
```

---

## 12. CONCLUSION

**Second Brain** is a sophisticated knowledge management platform that:

1. **Ingests** data from 9+ sources (Slack, Gmail, Box, GitHub, and 5 research platforms)
2. **Analyzes** documents with 6-layer NLP to detect knowledge gaps
3. **Captures** answers via web forms or voice transcription
4. **Embeds** all content (documents + answers) for semantic search
5. **Generates** training videos with AI voiceovers
6. **Creates** professional presentations via Gamma API
7. **Delivers** searchable knowledge base with RAG-powered chatbot
8. **Tracks** learning effectiveness and updates

The platform excels at **knowledge capture, gap identification, and automated training generation**, making it ideal for enterprise onboarding, compliance documentation, and organizational learning.

