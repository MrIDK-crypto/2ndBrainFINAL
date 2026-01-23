# Second Brain - Quick Reference Guide

## Integrations at a Glance

| Integration | Status | Auth Type | Data | Features |
|---|---|---|---|---|
| **Slack** | ✅ Implemented | Bot Token | Messages, Threads, Files | Channel selection, real-time sync |
| **Gmail** | ✅ Implemented | OAuth2 | Emails, Attachments | Label filtering, search queries |
| **Box** | ✅ Implemented | OAuth2 | Files, Docs (100+ types) | Folder filtering, incremental sync |
| **GitHub** | ✅ Implemented | OAuth2 | Code, Issues, PRs, Docs | Technical knowledge capture |
| **PowerPoint** | 🔄 UI Ready | OAuth2 | Slides, Notes, Charts | Slide extraction |
| **Excel** | 🔄 UI Ready | OAuth2 | Sheets, Tables, Charts | Data preservation |
| **PubMed** | 🔄 UI Ready | API Key (optional) | Papers, Abstracts, Citations | 35M+ biomedical docs |
| **ResearchGate** | 🔄 UI Ready | OAuth | Publications, Datasets | Academic research |
| **Google Scholar** | 🔄 UI Ready | Search API | Papers, Books, Theses | Multi-discipline search |

## Knowledge Transfer Pipeline (8 Steps)

```
1. INGEST → Connectors fetch data
2. PARSE → Extract & cleanup content
3. EMBED → Create vectors in Pinecone
4. DETECT GAPS → 6-layer NLP analysis
5. ANSWER → User/expert fills gaps (text or voice)
6. EMBED ANSWER → Immediately available for RAG
7. GENERATE TRAINING → Videos, guides, presentations
8. DEPLOY → User access via web/download
```

## Key Files & Their Purpose

### Backend Core
- `app_v2.py` - Main Flask app
- `api/integration_routes.py` - Connector management (54KB!)
- `services/knowledge_service.py` - Gap orchestration (76KB!)
- `services/intelligent_gap_detector.py` - NLP analysis (75KB!)
- `database/models.py` - SQLAlchemy ORM schema

### Connectors
- `connectors/base_connector.py` - Abstract base class
- `connectors/slack_connector.py` - Slack sync
- `connectors/gmail_connector.py` - Gmail sync
- `connectors/box_connector.py` - Box sync
- `connectors/github_connector.py` - GitHub sync

### Video & Presentation Generation
- `services/video_service.py` - Video generation orchestration
- `src/content_generation/gamma_presentation.py` - Gamma API integration
- `training_generator/generate_training_ppt.py` - PowerPoint creation

### Gap Detection Advanced
- `services/multistage_gap_analyzer.py` - 5-stage LLM reasoning
- `services/goal_first_analyzer.py` - Goal-oriented analysis
- `services/knowledge_gap_v3/` - Modern gap system

### Frontend
- `frontend/components/integrations/Integrations.tsx` - Main UI (2571 lines!)
  - Integration cards with connect/sync buttons
  - OAuth flow handling
  - Sync progress modal with real-time updates
  - Channel selection for Slack
  - Token input for Slack

## API Endpoints (Core)

### Integrations
```
GET    /api/integrations                    - List all integrations
GET    /api/integrations/{type}/auth        - Start OAuth
GET    /api/integrations/{type}/callback    - OAuth callback
POST   /api/integrations/{type}/sync        - Start sync
GET    /api/integrations/{type}/sync/status - Check sync progress
GET    /api/integrations/slack/channels     - Fetch Slack channels
PUT    /api/integrations/slack/channels     - Save selected channels
POST   /api/integrations/slack/token        - Save Slack token
```

### Documents
```
GET    /api/documents                       - List documents
POST   /api/documents/upload                - Upload document
DELETE /api/documents/{id}                  - Delete document
```

### Knowledge Gaps
```
POST   /api/knowledge/analyze               - Trigger gap detection
GET    /api/knowledge/gaps                  - List gaps
POST   /api/knowledge/gaps/{id}/answers     - Submit answer
GET    /api/knowledge/gaps/{id}/answers     - Get answers
```

### Videos
```
POST   /api/videos                          - Create video
GET    /api/videos                          - List videos
GET    /api/videos/{id}/status              - Check video progress
GET    /api/videos/{id}/download            - Download video
```

## Environment Variables (Essential)

```bash
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://[name].cognitiveservices.azure.com
AZURE_OPENAI_API_KEY=[key]
AZURE_CHAT_DEPLOYMENT=gpt-5-chat
AZURE_EMBEDDING_DEPLOYMENT=text-embedding-3-large
AZURE_WHISPER_DEPLOYMENT=whisper
AZURE_TTS_KEY=[key]
AZURE_TTS_VOICE=en-US-JennyNeural

# Pinecone
PINECONE_API_KEY=[key]
PINECONE_INDEX=[index_name]

# OAuth
GOOGLE_CLIENT_ID=[id].apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=[secret]
BOX_CLIENT_ID=[id]
BOX_CLIENT_SECRET=[secret]
SLACK_CLIENT_ID=[id]
SLACK_CLIENT_SECRET=[secret]

# Gamma (for presentations)
GAMMA_API_KEY=sk-gamma-[key]

# JWT
JWT_SECRET_KEY=[random_string]
```

## Database Schema (Key Tables)

```python
Tenant              # Multi-tenancy isolation
├─ User             # User accounts
├─ Connector        # Integration configs (Gmail, Slack, Box, GitHub)
├─ Document         # Parsed documents (from connectors)
├─ KnowledgeGap     # Detected gaps (8 categories)
├─ GapAnswer        # User answers (text or voice)
├─ Video            # Generated videos
├─ Project          # Document groupings
└─ DeletedDocument  # Soft-deleted docs

# Pinecone Vector Store (per tenant namespace)
├─ document_chunk_*     # Document embeddings
└─ gap_answer_*         # Gap answer embeddings
```

## Gap Detection: 8 Categories

1. **MISSING_RATIONALE** - Why decisions were made
2. **MISSING_AGENT** - Who is responsible
3. **MISSING_EVIDENCE** - Unsupported claims
4. **MISSING_DEFINITION** - Undefined terms
5. **MISSING_PROCESS** - How things are done
6. **MISSING_TIMELINE** - When things happen
7. **MISSING_IMPACT** - Consequences not documented
8. **MISSING_ALTERNATIVE** - Other options not explored

## Video Generation Specs

```
Resolution:    1920x1080 (HD)
Frame Rate:    24 FPS
Audio:         MP3 128kbps (Azure TTS)
Format:        MP4 (H.264)
Colors:        Dark blue + white + accents
Duration:      Varies (slide-based)
Voice:         en-US-JennyNeural (configurable)
```

## Common Issues & Solutions

| Issue | Cause | Solution |
|---|---|---|
| OAuth fails | Redirect URI mismatch | Check env vars match provider config |
| No channels in Slack | Token lacks scopes | Regenerate token with correct scopes |
| Slow video generation | Large documents | Run in background, check progress |
| Gamma API timeout | Rate limiting | Implement backoff retry |
| Gap detection empty | Small documents | Needs min 500 words for meaningful gaps |
| RAG missing answers | Not embedded | Check GapAnswer embedding step in code |

## Performance Notes

- **Embedding**: ~1000 tokens/sec (Azure)
- **Gap Detection**: ~5-10 docs/min (NLP-heavy)
- **Video Generation**: ~1-2 min/video (background thread)
- **Sync**: Varies by connector (Box slower, Slack faster)
- **RAG Search**: <100ms (Pinecone)

## Development Workflow

```bash
# Setup
cd backend && pip install -r requirements.txt
python -m spacy download en_core_web_sm
cp .env.template .env    # Fill secrets

# Run backend
python app_v2.py

# Run frontend (separate terminal)
cd frontend
npm install
npm run dev

# Test integration
curl -X GET http://localhost:5003/api/integrations \
  -H "Authorization: Bearer [token]"
```

## Feature Breakdown by Complexity

**Easy** (UI only)
- View integrations list
- View documents
- View gaps

**Medium** (API integration)
- Connect Slack (token upload)
- View sync progress
- Submit gap answer (text)

**Complex** (Full backend)
- Generate video (script → TTS → video)
- Detect gaps (6-layer NLP)
- Voice transcription (Azure Whisper)

**Research** (Unimplemented)
- PubMed connector
- ResearchGate connector
- Google Scholar connector

---

**Last Updated**: 2026-01-20  
**Total Lines**: 865 (main analysis)  
**Files Analyzed**: 50+  
**Connectors**: 4 implemented, 5 planned  
**Services**: 8 major services
