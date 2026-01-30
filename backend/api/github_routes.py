"""
GitHub Integration API Routes
OAuth flow, repository listing, and code analysis.
"""

import uuid
import json
from flask import Blueprint, request, jsonify, redirect, g
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from database.models import SessionLocal, Connector, Document, DocumentType
from connectors.github_connector import GitHubConnector
from services.code_analysis_service import CodeAnalysisService
from services.auth_service import require_auth
from services.extraction_service import ExtractionService
from services.embedding_service import EmbeddingService
from tasks.embedding_tasks import embed_documents_task


github_bp = Blueprint('github', __name__, url_prefix='/api/integrations/github')


def get_db():
    """Get database session"""
    return SessionLocal()


# ============================================================================
# OAUTH FLOW
# ============================================================================

@github_bp.route('/auth', methods=['GET'])
@require_auth
def initiate_github_oauth():
    """
    Start GitHub OAuth flow.

    Returns redirect URL for frontend.
    
    Response:
    {
        "auth_url": "https://github.com/login/oauth/authorize?..."
    }
    """
    try:
        # Generate state for CSRF protection
        state = str(uuid.uuid4())

        # Store state in session for verification (in production, use Redis/cache)
        # For now, we'll verify in callback using tenant_id from JWT

        connector = GitHubConnector()
        auth_url = connector.get_authorization_url(state)

        return jsonify({
            "success": True,
            "auth_url": auth_url,
            "state": state
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@github_bp.route('/callback', methods=['GET'])
def github_oauth_callback():
    """
    Handle GitHub OAuth callback.

    Query params:
        code: Authorization code
        state: CSRF state

    Redirects to frontend with success/error.
    """
    try:
        code = request.args.get('code')
        state = request.args.get('state')

        if not code:
            return redirect(f"{request.host_url.rstrip('/')}/integrations?error=missing_code")

        # Exchange code for token
        connector = GitHubConnector()
        token_data = connector.exchange_code_for_token(code)

        access_token = token_data['access_token']

        # Get user info
        connector_with_token = GitHubConnector(access_token=access_token)
        user_info = connector_with_token.get_user_info()

        # Extract JWT from cookie or query param (frontend should pass it)
        # For now, we'll return the token and let frontend store it
        # In production, frontend should pass tenant_id in state

        # Return success to frontend
        frontend_url = request.host_url.replace(':5003', ':3006').rstrip('/')
        redirect_url = (
            f"{frontend_url}/integrations?"
            f"github_connected=true&"
            f"github_user={user_info['login']}"
        )

        # Store token temporarily (in production, use session storage)
        # For now, frontend will need to call /connect with this token

        return redirect(redirect_url)

    except Exception as e:
        frontend_url = request.host_url.replace(':5003', ':3006').rstrip('/')
        return redirect(f"{frontend_url}/integrations?error={str(e)}")


@github_bp.route('/connect', methods=['POST'])
@require_auth
def connect_github():
    """
    Save GitHub connection after OAuth.

    Request body:
    {
        "access_token": "gho_...",
        "refresh_token": "optional"
    }

    Response:
    {
        "success": true,
        "connector": {...}
    }
    """
    try:
        data = request.get_json()
        access_token = data.get('access_token')

        if not access_token:
            return jsonify({
                "success": False,
                "error": "Access token is required"
            }), 400

        # Get user info from GitHub
        connector = GitHubConnector(access_token=access_token)
        user_info = connector.get_user_info()

        # Check rate limit
        rate_limit = connector.get_rate_limit()

        db = get_db()
        try:
            # Check if connector already exists
            existing = db.query(Connector).filter(
                Connector.tenant_id == g.tenant_id,
                Connector.connector_type == 'github'
            ).first()

            if existing:
                # Update existing connector
                existing.credentials = {
                    'access_token': access_token,
                    'refresh_token': data.get('refresh_token'),
                    'github_user': user_info['login'],
                    'github_user_id': user_info['id']
                }
                existing.status = 'active'
                existing.last_sync_at = None
                existing.updated_at = datetime.now(timezone.utc)

                db.commit()
                db.refresh(existing)

                return jsonify({
                    "success": True,
                    "connector": existing.to_dict(),
                    "github_user": user_info['login'],
                    "rate_limit": rate_limit
                })

            # Create new connector
            new_connector = Connector(
                tenant_id=g.tenant_id,
                connector_type='github',
                credentials={
                    'access_token': access_token,
                    'refresh_token': data.get('refresh_token'),
                    'github_user': user_info['login'],
                    'github_user_id': user_info['id']
                },
                status='active',
                created_at=datetime.now(timezone.utc)
            )

            db.add(new_connector)
            db.commit()
            db.refresh(new_connector)

            return jsonify({
                "success": True,
                "connector": new_connector.to_dict(),
                "github_user": user_info['login'],
                "rate_limit": rate_limit
            }), 201

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# REPOSITORY LISTING
# ============================================================================

@github_bp.route('/repositories', methods=['GET'])
@require_auth
def list_repositories():
    """
    List GitHub repositories accessible to user.

    Response:
    {
        "success": true,
        "repositories": [
            {
                "id": 12345,
                "name": "my-repo",
                "full_name": "user/my-repo",
                "description": "...",
                "language": "Python",
                "private": false,
                "default_branch": "main",
                "updated_at": "..."
            }
        ]
    }
    """
    try:
        db = get_db()
        try:
            connector = db.query(Connector).filter(
                Connector.tenant_id == g.tenant_id,
                Connector.connector_type == 'github',
                Connector.status == 'active'
            ).first()

            if not connector:
                return jsonify({
                    "success": False,
                    "error": "GitHub not connected"
                }), 404

            access_token = connector.credentials.get('access_token')
            github = GitHubConnector(access_token=access_token)

            repositories = github.get_repositories()

            return jsonify({
                "success": True,
                "repositories": repositories,
                "count": len(repositories)
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# SYNC & ANALYZE REPOSITORY
# ============================================================================

@github_bp.route('/sync', methods=['POST'])
@require_auth
def sync_repository():
    """
    Sync and analyze a GitHub repository.

    Request body:
    {
        "repository": "user/repo",
        "max_files": 100,  # optional
        "max_files_to_analyze": 30  # optional
    }

    Response:
    {
        "success": true,
        "analysis": {...},
        "documents_created": 5
    }
    """
    try:
        data = request.get_json()
        repository = data.get('repository')  # Format: "owner/repo"

        if not repository or '/' not in repository:
            return jsonify({
                "success": False,
                "error": "Invalid repository format. Use 'owner/repo'"
            }), 400

        owner, repo = repository.split('/', 1)
        max_files = data.get('max_files', 100)
        max_files_to_analyze = data.get('max_files_to_analyze', 30)

        db = get_db()
        try:
            # Get GitHub connector
            connector = db.query(Connector).filter(
                Connector.tenant_id == g.tenant_id,
                Connector.connector_type == 'github',
                Connector.status == 'active'
            ).first()

            if not connector:
                return jsonify({
                    "success": False,
                    "error": "GitHub not connected"
                }), 404

            access_token = connector.credentials.get('access_token')

            # Fetch repository code
            print(f"[GitHub] Fetching code from {repository}")
            github = GitHubConnector(access_token=access_token)
            code_files = github.fetch_repository_code(
                owner=owner,
                repo=repo,
                max_files=max_files
            )

            if not code_files:
                return jsonify({
                    "success": False,
                    "error": "No code files found in repository"
                }), 404

            # Get repository info for description
            repos = github.get_repositories()
            repo_info = next(
                (r for r in repos if r['full_name'].lower() == repository.lower()),
                None
            )
            repo_description = repo_info['description'] if repo_info else None

            # Analyze repository with LLM
            print(f"[GitHub] Analyzing repository with LLM")
            analyzer = CodeAnalysisService()
            analysis = analyzer.analyze_repository(
                repo_name=repository,
                repo_description=repo_description,
                code_files=code_files,
                max_files_to_analyze=max_files_to_analyze
            )

            # Store as documents
            documents_created = []

            # 1. Main documentation document
            doc_main = Document(
                tenant_id=g.tenant_id,
                title=f"{repository} - Technical Documentation",
                content=analysis['documentation'],
                document_type=DocumentType.OTHER,
                source='github',
                sender_email=connector.credentials.get('github_user'),
                external_id=f"github_{repository.replace('/', '_')}_docs",
                metadata={
                    'repository': repository,
                    'analysis_type': 'comprehensive_documentation',
                    'stats': analysis['stats']
                },
                classification='work',
                classification_confidence=1.0,
                classified_at=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc)
            )
            db.add(doc_main)
            documents_created.append(doc_main)

            # 2. Repository overview document
            overview_content = f"""# {repository} - Repository Overview

## Purpose
{analysis['repository_overview']['purpose']}

## Architecture
{analysis['repository_overview']['architecture']}

## Technology Stack
{chr(10).join(f'- {tech}' for tech in analysis['repository_overview']['tech_stack'])}

## Design Patterns
{chr(10).join(f'- {pattern}' for pattern in analysis['repository_overview']['patterns'])}

## Components
{json.dumps(analysis['repository_overview']['components'], indent=2)}

## Statistics
- Total Files: {analysis['stats']['total_files']}
- Analyzed Files: {analysis['stats']['analyzed_files']}
- Total Lines: {analysis['stats']['total_lines']:,}
- Languages: {', '.join(f"{k} ({v})" for k, v in analysis['stats']['languages'].items())}
"""

            doc_overview = Document(
                tenant_id=g.tenant_id,
                title=f"{repository} - Overview",
                content=overview_content,
                document_type=DocumentType.OTHER,
                source='github',
                sender_email=connector.credentials.get('github_user'),
                external_id=f"github_{repository.replace('/', '_')}_overview",
                metadata={
                    'repository': repository,
                    'analysis_type': 'overview',
                    'overview': analysis['repository_overview']
                },
                classification='work',
                classification_confidence=1.0,
                classified_at=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc)
            )
            db.add(doc_overview)
            documents_created.append(doc_overview)

            # 3. Individual file analyses (top 10 most important)
            for file_analysis in analysis['file_analyses'][:10]:
                file_content = f"""# {file_analysis['file_path']}

## Summary
{file_analysis['summary']}

## Language
{file_analysis['language']}

## Key Functions/Classes
{chr(10).join(f'- {func}' for func in file_analysis['key_functions'])}

## Dependencies
{chr(10).join(f'- {dep}' for dep in file_analysis['dependencies'])}

## Business Logic
{file_analysis['business_logic']}

## API Endpoints
{chr(10).join(f'- {ep}' for ep in file_analysis.get('api_endpoints', []))}

## Data Models
{chr(10).join(f'- {model}' for model in file_analysis.get('data_models', []))}

## Important Notes
{chr(10).join(f'- {note}' for note in file_analysis['important_notes'])}
"""

                doc_file = Document(
                    tenant_id=g.tenant_id,
                    title=f"{repository} - {file_analysis['file_path']}",
                    content=file_content,
                    document_type=DocumentType.OTHER,
                    source='github',
                    sender_email=connector.credentials.get('github_user'),
                    external_id=f"github_{repository.replace('/', '_')}_{file_analysis['file_path'].replace('/', '_')}",
                    metadata={
                        'repository': repository,
                        'file_path': file_analysis['file_path'],
                        'analysis_type': 'file_analysis',
                        'language': file_analysis['language']
                    },
                    classification='work',
                    classification_confidence=1.0,
                    classified_at=datetime.now(timezone.utc),
                    created_at=datetime.now(timezone.utc)
                )
                db.add(doc_file)
                documents_created.append(doc_file)

            # Commit all documents
            db.commit()

            # Extract structured summaries
            extraction_service = ExtractionService()
            for doc in documents_created:
                db.refresh(doc)
                extraction_service.extract_and_update(doc, db)

            # Trigger embedding (async if Celery available)
            doc_ids = [doc.id for doc in documents_created]
            try:
                # Try async task
                embed_documents_task.delay(doc_ids, g.tenant_id)
                print(f"[GitHub] Queued {len(doc_ids)} documents for embedding")
            except:
                # Fallback to sync embedding
                embedding_service = EmbeddingService()
                embedding_service.embed_documents(doc_ids, g.tenant_id, db)
                print(f"[GitHub] Embedded {len(doc_ids)} documents synchronously")

            # Update connector last_sync_at
            connector.last_sync_at = datetime.now(timezone.utc)
            db.commit()

            return jsonify({
                "success": True,
                "repository": repository,
                "analysis": {
                    'overview': analysis['repository_overview'],
                    'stats': analysis['stats'],
                    'analyzed_at': analysis['analyzed_at']
                },
                "documents_created": len(documents_created),
                "document_ids": doc_ids
            })

        finally:
            db.close()

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# DISCONNECT
# ============================================================================

@github_bp.route('/disconnect', methods=['POST'])
@require_auth
def disconnect_github():
    """
    Disconnect GitHub integration.

    Response:
    {
        "success": true
    }
    """
    try:
        db = get_db()
        try:
            connector = db.query(Connector).filter(
                Connector.tenant_id == g.tenant_id,
                Connector.connector_type == 'github'
            ).first()

            if connector:
                connector.status = 'disconnected'
                connector.credentials = {}
                connector.updated_at = datetime.now(timezone.utc)
                db.commit()

            return jsonify({"success": True})

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
