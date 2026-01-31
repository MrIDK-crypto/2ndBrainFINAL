"""
2nd Brain - Enterprise Knowledge Transfer Platform
Version 2.0 - B2B SaaS Edition

Complete Flask application with:
- Multi-tenant authentication (JWT + bcrypt)
- Integration connectors (Gmail, Slack, Box)
- Document classification (AI-powered work/personal)
- Knowledge gap detection and answer persistence
- Video generation
- Advanced RAG search
"""

import os
import secrets
from pathlib import Path
from datetime import datetime

from flask import Flask, jsonify, request, g
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))

# CORS configuration
CORS(app,
     supports_credentials=True,
     resources={
         r"/api/*": {
             "origins": ["http://localhost:3000", "http://localhost:3006", "*"],
             "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
             "allow_headers": ["Content-Type", "Authorization"]
         }
     })

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

from database.models import init_database, SessionLocal

# Initialize database tables
try:
    init_database()
    print("✓ Database initialized")
except Exception as e:
    print(f"⚠ Database initialization error: {e}")

# ============================================================================
# REGISTER API BLUEPRINTS
# ============================================================================

from api.auth_routes import auth_bp
from api.integration_routes import integration_bp
from api.document_routes import document_bp
from api.knowledge_routes import knowledge_bp
from api.video_routes import video_bp
from api.chat_routes import chat_bp
from api.jobs_routes import jobs_bp
from api.slack_bot_routes import slack_bot_bp
from api.profile_routes import profile_bp
from api.github_routes import github_bp

app.register_blueprint(auth_bp)
app.register_blueprint(integration_bp)
app.register_blueprint(document_bp)
app.register_blueprint(knowledge_bp)
app.register_blueprint(video_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(jobs_bp)
app.register_blueprint(slack_bot_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(github_bp)

print("✓ API blueprints registered")

# ============================================================================
# LEGACY COMPATIBILITY - Import existing routes
# ============================================================================

# Import existing RAG and search functionality
try:
    BASE_DIR = Path(__file__).parent

    # Azure OpenAI Configuration
    AZURE_OPENAI_ENDPOINT = os.getenv(
        "AZURE_OPENAI_ENDPOINT",
        "https://rishi-mihfdoty-eastus2.cognitiveservices.azure.com"
    )
    AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
    AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-12-01-preview")
    AZURE_CHAT_DEPLOYMENT = os.getenv("AZURE_CHAT_DEPLOYMENT", "gpt-4o")

    # Tenant data directories
    TENANT_DATA_DIRS = {
        "beat": BASE_DIR / "club_data",
        "enron": BASE_DIR / "data"
    }

    # RAG instances per tenant
    tenant_rag_instances = {}

    def get_rag_for_tenant(tenant_id: str):
        """Get or create RAG instance for tenant"""
        print(f"[RAG DEBUG] Getting RAG for tenant: {tenant_id}", flush=True)

        if tenant_id in tenant_rag_instances:
            print(f"[RAG DEBUG] Found cached RAG for tenant {tenant_id}", flush=True)
            return tenant_rag_instances[tenant_id]

        # Check for tenant-specific data
        tenant_dir = TENANT_DATA_DIRS.get(tenant_id)
        print(f"[RAG DEBUG] TENANT_DATA_DIRS lookup: {tenant_dir}", flush=True)

        if not tenant_dir:
            # Check database for tenant data directory
            db = SessionLocal()
            try:
                from database.models import Tenant
                tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
                print(f"[RAG DEBUG] DB tenant lookup: {tenant}", flush=True)
                if tenant and tenant.data_directory:
                    tenant_dir = Path(tenant.data_directory)
                    print(f"[RAG DEBUG] Using DB tenant_dir: {tenant_dir}", flush=True)
            finally:
                db.close()

        if not tenant_dir:
            print(f"[RAG DEBUG] No tenant_dir found, returning None", flush=True)
            return None

        # Try to load RAG
        try:
            from rag.enhanced_rag_v2 import EnhancedRAGv2
            embedding_index_path = str(tenant_dir / "embedding_index.pkl")
            print(f"[RAG DEBUG] Checking index path: {embedding_index_path}", flush=True)
            print(f"[RAG DEBUG] Index exists: {Path(embedding_index_path).exists()}", flush=True)

            if Path(embedding_index_path).exists():
                print(f"[RAG DEBUG] Loading RAG from {embedding_index_path}", flush=True)
                rag = EnhancedRAGv2(
                    embedding_index_path=embedding_index_path,
                    openai_api_key=AZURE_OPENAI_API_KEY,
                    use_reranker=True,
                    use_mmr=True,
                    cache_results=True
                )
                tenant_rag_instances[tenant_id] = rag
                print(f"[RAG DEBUG] RAG loaded successfully!", flush=True)
                return rag
            else:
                print(f"[RAG DEBUG] Index file not found at {embedding_index_path}", flush=True)
        except Exception as e:
            print(f"Error loading RAG for tenant {tenant_id}: {e}", flush=True)
            import traceback
            traceback.print_exc()

        print(f"[RAG DEBUG] Returning None", flush=True)
        return None

    print("✓ RAG system configured")

except Exception as e:
    print(f"⚠ RAG system not loaded: {e}")

# ============================================================================
# ROOT & HEALTH CHECK
# ============================================================================

@app.route('/', methods=['GET'])
def root():
    """Root endpoint - API info"""
    return jsonify({
        "name": "2nd Brain API",
        "version": "2.0.0",
        "description": "Enterprise Knowledge Transfer Platform",
        "endpoints": {
            "health": "/api/health",
            "auth": {
                "signup": "POST /api/auth/signup",
                "login": "POST /api/auth/login",
                "me": "GET /api/auth/me"
            },
            "integrations": "GET /api/integrations",
            "documents": "GET /api/documents",
            "knowledge_gaps": "GET /api/knowledge/gaps",
            "search": "POST /api/search"
        }
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Enhanced health check endpoint.

    Checks:
    - Database connectivity (required)
    - Pinecone availability (optional, if CHECK_PINECONE=true)
    - Azure OpenAI availability (optional, if CHECK_AZURE_OPENAI=true)

    Used by Render for health monitoring.
    Returns 200 if healthy, 503 if critical services fail.
    """
    from utils.logger import log_warning
    from sqlalchemy import text
    import time

    start_time = time.time()
    health_status = {
        "status": "healthy",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {},
        "features": {
            "auth": True,
            "integrations": True,
            "classification": True,
            "knowledge_gaps": True,
            "video_generation": True,
            "rag_search": AZURE_OPENAI_API_KEY is not None
        }
    }

    # 1. Database check (CRITICAL)
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        health_status["checks"]["database"] = "ok"
    except Exception as e:
        health_status["checks"]["database"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"
        log_warning("HealthCheck", "Database check failed", error=str(e))

    # 2. Pinecone check (optional - can be slow)
    if os.getenv("CHECK_PINECONE") == "true":
        try:
            from vector_stores.pinecone_store import PineconeVectorStore
            store = PineconeVectorStore()
            store.index.describe_index_stats()
            health_status["checks"]["pinecone"] = "ok"
        except Exception as e:
            health_status["checks"]["pinecone"] = f"warning: {str(e)}"
            log_warning("HealthCheck", "Pinecone check failed", error=str(e))

    # 3. Azure OpenAI check (optional - only if critical)
    if os.getenv("CHECK_AZURE_OPENAI") == "true":
        try:
            from azure_openai_config import get_azure_client
            client = get_azure_client()
            # Simple check - just verify client exists
            health_status["checks"]["azure_openai"] = "ok" if client else "warning: no client"
        except Exception as e:
            health_status["checks"]["azure_openai"] = f"warning: {str(e)}"
            log_warning("HealthCheck", "Azure OpenAI check failed", error=str(e))

    # Response time
    health_status["response_time_ms"] = round((time.time() - start_time) * 1000, 2)

    # Return 200 if healthy, 503 if unhealthy
    status_code = 200 if health_status["status"] == "healthy" else 503

    return jsonify(health_status), status_code

# ============================================================================
# SEARCH ENDPOINT (Enhanced RAG with Reranking, MMR, Query Expansion)
# ============================================================================

@app.route('/api/search', methods=['POST'])
def search():
    """
    Enhanced RAG search endpoint with:
    - Query expansion (100+ acronyms)
    - Cross-encoder reranking
    - MMR diversity selection
    - Hallucination detection
    - Strict citation enforcement

    Request body:
    {
        "query": "How do we handle customer complaints?",
        "top_k": 10,
        "include_sources": true,
        "enhanced": true  // Enable enhanced features (default: true)
    }
    """
    from services.auth_service import get_token_from_header, JWTUtils
    from vector_stores.pinecone_store import get_hybrid_store

    # Get tenant from auth token
    auth_header = request.headers.get("Authorization", "")
    token = get_token_from_header(auth_header)
    tenant_id = None

    if token:
        payload, error = JWTUtils.decode_access_token(token)
        if payload:
            tenant_id = payload.get("tenant_id")
            print(f"[SEARCH] Tenant from JWT: {tenant_id}", flush=True)

    # Security: ONLY allow tenant_id from JWT, never from headers
    if not tenant_id:
        return jsonify({
            "success": False,
            "error": "Authentication required. Valid JWT token must be provided."
        }), 401

    data = request.get_json() or {}
    query = data.get('query', '')
    conversation_history = data.get('conversation_history', [])  # NEW: conversation context
    top_k = data.get('top_k', 10)
    include_sources = data.get('include_sources', True)
    use_enhanced = data.get('enhanced', True)  # Enhanced mode on by default

    if not query:
        return jsonify({
            "success": False,
            "error": "Query required"
        }), 400

    print(f"[SEARCH] Conversation history length: {len(conversation_history)}", flush=True)

    try:
        vector_store = get_hybrid_store()

        # Check if knowledge base is empty first
        stats = vector_store.get_stats(tenant_id)
        vector_count = stats.get('vector_count', 0)

        if vector_count == 0:
            return jsonify({
                "success": True,
                "query": query,
                "answer": "Welcome! Your knowledge base is empty. To get started:\n\n1. Go to **Integrations** and connect your Gmail, Slack, or Box\n2. Sync your data to import documents\n3. Review documents in the **Documents** page\n4. Once you have confirmed documents, come back here to search!\n\nI'll be ready to answer your questions once you've added some content.",
                "confidence": 1.0,
                "query_type": "onboarding",
                "sources": [],
                "source_count": 0,
                "is_empty_knowledge_base": True
            })

        # Use Enhanced Search Service
        if use_enhanced:
            from services.enhanced_search_service import get_enhanced_search_service

            print(f"[SEARCH] Using ENHANCED search for tenant {tenant_id}: '{query}'", flush=True)

            enhanced_service = get_enhanced_search_service()
            result = enhanced_service.search_and_answer(
                query=query,
                tenant_id=tenant_id,
                vector_store=vector_store,
                top_k=top_k,
                validate=True,
                conversation_history=conversation_history  # Pass conversation history
            )

            # Format sources for response
            sources = []
            if include_sources:
                for src in result.get('sources', []):
                    sources.append({
                        "doc_id": src.get('doc_id', ''),
                        "title": src.get('title', 'Untitled'),
                        "content_preview": (src.get('content', '') or src.get('content_preview', ''))[:300],
                        "score": src.get('rerank_score', src.get('score', 0)),
                        "metadata": src.get('metadata', {})
                    })

            # Build response
            response_data = {
                "success": True,
                "query": query,
                "expanded_query": result.get('expanded_query'),
                "answer": result.get('answer', ''),
                "confidence": result.get('confidence', 0),
                "query_type": "enhanced_rag",
                "sources": sources,
                "source_count": len(sources),
                "search_time": result.get('search_time', 0),
                "features_used": result.get('features_used', {}),
                "context_chars": result.get('context_chars', 0)
            }

            # Add validation results if available
            if result.get('hallucination_check'):
                response_data['hallucination_check'] = {
                    'verified': result['hallucination_check'].get('verified', 0),
                    'total_claims': result['hallucination_check'].get('total_claims', 0),
                    'confidence': result['hallucination_check'].get('confidence', 1.0)
                }

            if result.get('citation_check'):
                response_data['citation_coverage'] = result['citation_check'].get('cited_ratio', 1.0)

            print(f"[SEARCH] Enhanced search complete: {len(sources)} sources, "
                  f"confidence={result.get('confidence', 0):.2f}, "
                  f"features={result.get('features_used', {})}", flush=True)

            return jsonify(response_data)

        else:
            # Fallback to basic search (for debugging/comparison)
            print(f"[SEARCH] Using BASIC search for tenant {tenant_id}: '{query}'", flush=True)

            results = vector_store.hybrid_search(
                query=query,
                tenant_id=tenant_id,
                top_k=top_k
            )

            if not results:
                return jsonify({
                    "success": True,
                    "query": query,
                    "answer": "I couldn't find any relevant information for your query. Try rephrasing or asking about a different topic.",
                    "confidence": 0.3,
                    "query_type": "no_results",
                    "sources": [],
                    "source_count": 0
                })

            # Basic answer generation (legacy)
            from openai import AzureOpenAI
            openai_client = AzureOpenAI(
                azure_endpoint=AZURE_OPENAI_ENDPOINT,
                api_key=AZURE_OPENAI_API_KEY,
                api_version="2024-12-01-preview"
            )

            context_parts = []
            for i, result in enumerate(results[:8]):  # Increased from 5 to 8
                title = result.get('title', 'Untitled')
                content = result.get('content', '')[:2000]  # Increased from 500
                context_parts.append(f"[Source {i+1}] {title}:\n{content}")

            context = "\n\n---\n\n".join(context_parts)

            response = openai_client.chat.completions.create(
                model=AZURE_CHAT_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": "You are a helpful knowledge assistant. Answer based on the provided sources. Cite sources like [Source 1]."},
                    {"role": "user", "content": f"Sources:\n{context}\n\nQuestion: {query}\n\nAnswer with citations:"}
                ],
                max_tokens=1500,
                temperature=0.2
            )

            answer = response.choices[0].message.content

            sources = []
            if include_sources:
                for result in results:
                    sources.append({
                        "doc_id": result.get('doc_id', ''),
                        "title": result.get('title', 'Untitled'),
                        "content_preview": result.get('content', '')[:300],
                        "score": result.get('score', 0),
                        "metadata": result.get('metadata', {})
                    })

            return jsonify({
                "success": True,
                "query": query,
                "answer": answer,
                "confidence": results[0].get('score', 0.5) if results else 0,
                "query_type": "basic_rag",
                "sources": sources,
                "source_count": len(sources)
            })

    except Exception as e:
        import traceback
        print(f"[SEARCH] Error: {e}", flush=True)
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# ============================================================================
# PROJECTS ENDPOINT
# ============================================================================

@app.route('/api/projects', methods=['GET'])
def list_projects():
    """List projects for tenant"""
    from services.auth_service import get_token_from_header, JWTUtils
    from database.models import Project

    # Get tenant
    token = get_token_from_header(request.headers.get("Authorization", ""))
    tenant_id = None

    if token:
        payload, _ = JWTUtils.decode_access_token(token)
        if payload:
            tenant_id = payload.get("tenant_id")

    if not tenant_id:
        # Try legacy endpoint
        return jsonify({
            "success": True,
            "projects": []
        })

    db = SessionLocal()
    try:
        projects = db.query(Project).filter(
            Project.tenant_id == tenant_id,
            Project.is_archived == False
        ).all()

        return jsonify({
            "success": True,
            "projects": [p.to_dict() for p in projects]
        })
    finally:
        db.close()

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({
        "success": False,
        "error": "Endpoint not found"
    }), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({
        "success": False,
        "error": "Internal server error"
    }), 500

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5003))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   🧠 2nd Brain - Enterprise Knowledge Transfer Platform      ║
║                                                              ║
║   Version: 2.0.0 (B2B SaaS Edition)                         ║
║   Port: {port}                                                ║
║                                                              ║
║   Endpoints:                                                 ║
║   - POST /api/auth/signup     - User registration           ║
║   - POST /api/auth/login      - User login                  ║
║   - GET  /api/integrations    - List integrations           ║
║   - GET  /api/documents       - List documents              ║
║   - POST /api/documents/classify - Classify documents       ║
║   - GET  /api/knowledge/gaps  - Knowledge gaps              ║
║   - POST /api/knowledge/transcribe - Voice transcription    ║
║   - POST /api/videos          - Create video                ║
║   - POST /api/search          - RAG search                  ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")

    app.run(host='0.0.0.0', port=port, debug=debug)
