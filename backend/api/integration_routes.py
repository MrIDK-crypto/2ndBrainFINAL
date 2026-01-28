"""
Integration API Routes
REST endpoints for managing external integrations (Gmail, Slack, Box, etc.)
"""

import os
import secrets
import jwt
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, g, redirect

from database.models import (
    SessionLocal, Connector, Document, Tenant, DeletedDocument,
    ConnectorType, ConnectorStatus, DocumentStatus, DocumentClassification,
    generate_uuid, utc_now
)
from database.config import JWT_SECRET_KEY, JWT_ALGORITHM
from services.auth_service import require_auth, get_token_from_header, JWTUtils
from services.embedding_service import get_embedding_service
from services.extraction_service import get_extraction_service


# Create blueprint
integration_bp = Blueprint('integrations', __name__, url_prefix='/api/integrations')


# ============================================================================
# SECURE OAUTH STATE MANAGEMENT (JWT-based, stateless)
# ============================================================================

def create_oauth_state(tenant_id: str, user_id: str, connector_type: str, extra_data: dict = None) -> str:
    """
    Create a secure, signed OAuth state token.
    This eliminates the need for server-side state storage (Redis/memory).

    The state is a JWT containing:
    - tenant_id: The tenant making the request
    - user_id: The user initiating the OAuth
    - connector_type: Which connector (gmail, slack, box)
    - exp: Expiration (10 minutes)
    - nonce: Random value for uniqueness
    """
    payload = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "connector_type": connector_type,
        "nonce": secrets.token_urlsafe(16),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        "type": "oauth_state"
    }
    if extra_data:
        payload["data"] = extra_data

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_oauth_state(state: str) -> tuple:
    """
    Verify and decode an OAuth state token.

    Returns:
        (payload, error) - payload dict if valid, None and error message if invalid
    """
    try:
        payload = jwt.decode(state, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

        if payload.get("type") != "oauth_state":
            return None, "Invalid state type"

        return payload, None
    except jwt.ExpiredSignatureError:
        return None, "OAuth state expired. Please try again."
    except jwt.InvalidTokenError as e:
        return None, f"Invalid OAuth state: {str(e)}"


# Legacy oauth_states dict - kept for backward compatibility during transition
# TODO: Remove after all OAuth flows are migrated to JWT-based state
oauth_states = {}

# Sync progress tracking (use Redis in production for multi-instance)
sync_progress = {}


def get_db():
    """Get database session"""
    return SessionLocal()


# ============================================================================
# LIST INTEGRATIONS
# ============================================================================

@integration_bp.route('', methods=['GET'])
@require_auth
def list_integrations():
    """
    List all integrations for the current tenant.

    Response:
    {
        "success": true,
        "integrations": [
            {
                "type": "gmail",
                "name": "Gmail",
                "status": "connected",
                "last_sync_at": "2024-01-15T10:30:00Z",
                ...
            }
        ]
    }
    """
    try:
        db = get_db()
        try:
            # Get existing connectors for tenant
            connectors = db.query(Connector).filter(
                Connector.tenant_id == g.tenant_id,
                Connector.is_active == True
            ).all()

            # Build response with all connector types
            connector_map = {c.connector_type: c for c in connectors}

            integrations = []

            # Gmail
            gmail = connector_map.get(ConnectorType.GMAIL)
            integrations.append({
                "type": "gmail",
                "name": "Gmail",
                "description": "Sync emails from your Gmail account",
                "icon": "mail",
                "auth_type": "oauth",
                "status": gmail.status.value if gmail else "not_configured",
                "connector_id": gmail.id if gmail else None,
                "last_sync_at": gmail.last_sync_at.isoformat() if gmail and gmail.last_sync_at else None,
                "total_items_synced": gmail.total_items_synced if gmail else 0,
                "error_message": gmail.error_message if gmail else None
            })

            # Slack
            slack = connector_map.get(ConnectorType.SLACK)
            integrations.append({
                "type": "slack",
                "name": "Slack",
                "description": "Sync messages from Slack workspaces",
                "icon": "slack",
                "auth_type": "oauth",
                "status": slack.status.value if slack else "not_configured",
                "connector_id": slack.id if slack else None,
                "last_sync_at": slack.last_sync_at.isoformat() if slack and slack.last_sync_at else None,
                "total_items_synced": slack.total_items_synced if slack else 0,
                "error_message": slack.error_message if slack else None
            })

            # Box
            box = connector_map.get(ConnectorType.BOX)
            integrations.append({
                "type": "box",
                "name": "Box",
                "description": "Sync files and documents from Box",
                "icon": "box",
                "auth_type": "oauth",
                "status": box.status.value if box else "not_configured",
                "connector_id": box.id if box else None,
                "last_sync_at": box.last_sync_at.isoformat() if box and box.last_sync_at else None,
                "total_items_synced": box.total_items_synced if box else 0,
                "error_message": box.error_message if box else None
            })

            # GitHub (optional)
            github = connector_map.get(ConnectorType.GITHUB)
            integrations.append({
                "type": "github",
                "name": "GitHub",
                "description": "Sync code, issues, and PRs from GitHub",
                "icon": "github",
                "auth_type": "oauth",
                "status": github.status.value if github else "not_configured",
                "connector_id": github.id if github else None,
                "last_sync_at": github.last_sync_at.isoformat() if github and github.last_sync_at else None,
                "total_items_synced": github.total_items_synced if github else 0,
                "error_message": github.error_message if github else None
            })

            return jsonify({
                "success": True,
                "integrations": integrations,
                "connected_count": sum(1 for i in integrations if i["status"] == "connected")
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# GMAIL INTEGRATION
# ============================================================================

@integration_bp.route('/gmail/auth', methods=['GET'])
@require_auth
def gmail_auth():
    """
    Start Gmail OAuth flow.

    Response:
    {
        "success": true,
        "auth_url": "https://accounts.google.com/...",
        "state": "..."
    }
    """
    try:
        from connectors.gmail_connector import GmailConnector

        # Generate JWT-based state (works across multiple workers)
        redirect_uri = os.getenv(
            "GOOGLE_REDIRECT_URI",
            "http://localhost:5003/api/integrations/gmail/callback"
        )

        state = create_oauth_state(
            tenant_id=g.tenant_id,
            user_id=g.user_id,
            connector_type="gmail",
            extra_data={"redirect_uri": redirect_uri}
        )
        print(f"[GmailAuth] JWT state created for tenant: {g.tenant_id}")

        # Get auth URL
        auth_url = GmailConnector.get_auth_url(redirect_uri, state)

        return jsonify({
            "success": True,
            "auth_url": auth_url,
            "state": state
        })

    except ImportError:
        return jsonify({
            "success": False,
            "error": "Gmail dependencies not installed. Run: pip install google-auth google-auth-oauthlib google-api-python-client"
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@integration_bp.route('/gmail/callback', methods=['GET'])
def gmail_callback():
    """
    Gmail OAuth callback handler.
    Called by Google after user authorization.
    """
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

    try:
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')

        if error:
            return redirect(f"{FRONTEND_URL}/integrations?error={error}")

        if not code or not state:
            return redirect(f"{FRONTEND_URL}/integrations?error=missing_params")

        # Verify JWT-based state
        state_data, error_msg = verify_oauth_state(state)
        if error_msg or not state_data or state_data.get("connector_type") != "gmail":
            print(f"[Gmail Callback] Invalid state: {error_msg}")
            return redirect(f"{FRONTEND_URL}/integrations?error=invalid_state")

        from connectors.gmail_connector import GmailConnector

        # Exchange code for tokens
        redirect_uri = state_data.get("data", {}).get("redirect_uri")
        if not redirect_uri:
            redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:5003/api/integrations/gmail/callback")
        tokens, error = GmailConnector.exchange_code_for_tokens(code, redirect_uri)

        if error:
            return redirect(f"{FRONTEND_URL}/integrations?error={error}")

        # Save connector to database
        db = get_db()
        try:
            tenant_id = state_data.get("tenant_id")
            user_id = state_data.get("user_id")

            # Check if connector already exists
            connector = db.query(Connector).filter(
                Connector.tenant_id == tenant_id,
                Connector.connector_type == ConnectorType.GMAIL
            ).first()

            is_first_connection = connector is None

            if connector:
                # Update existing
                connector.access_token = tokens["access_token"]
                connector.refresh_token = tokens["refresh_token"]
                connector.status = ConnectorStatus.CONNECTED
                connector.is_active = True  # Re-enable connector on reconnect
                connector.error_message = None
                connector.updated_at = utc_now()
                print(f"[Gmail Callback] Updated existing connector for tenant: {tenant_id}")
            else:
                # Create new
                connector = Connector(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    connector_type=ConnectorType.GMAIL,
                    name="Gmail",
                    status=ConnectorStatus.CONNECTED,
                    access_token=tokens["access_token"],
                    refresh_token=tokens["refresh_token"],
                    token_scopes=["https://www.googleapis.com/auth/gmail.readonly"]
                )
                db.add(connector)
                print(f"[Gmail Callback] Created new connector for tenant: {tenant_id}")

            db.commit()

            # Auto-sync on first connection
            if is_first_connection:
                import threading
                connector_id = connector.id
                tenant_id = state_data["tenant_id"]
                user_id = state_data["user_id"]

                def run_initial_sync():
                    _run_connector_sync(
                        connector_id=connector_id,
                        connector_type="gmail",
                        since=None,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        full_sync=True
                    )

                thread = threading.Thread(target=run_initial_sync)
                thread.daemon = True
                thread.start()

                print(f"[Gmail Callback] Started auto-sync for first-time connection")

            return redirect(f"{FRONTEND_URL}/integrations?success=gmail")

        finally:
            db.close()

    except Exception as e:
        return redirect(f"{FRONTEND_URL}/integrations?error={str(e)}")


# ============================================================================
# SLACK INTEGRATION
# ============================================================================

@integration_bp.route('/slack/auth', methods=['GET'])
@require_auth
def slack_auth():
    """
    Start Slack OAuth flow.
    """
    try:
        # Generate JWT-based state (works across multiple workers)
        state = create_oauth_state(
            tenant_id=g.tenant_id,
            user_id=g.user_id,
            connector_type="slack"
        )

        # Build Slack OAuth URL
        client_id = os.getenv("SLACK_CLIENT_ID", "")
        redirect_uri = os.getenv(
            "SLACK_REDIRECT_URI",
            "http://localhost:5003/api/integrations/slack/callback"
        )

        # Check if credentials are configured
        if not client_id:
            return jsonify({
                "success": False,
                "error": "Slack integration not configured. Please set SLACK_CLIENT_ID and SLACK_CLIENT_SECRET in your environment."
            }), 400

        # Comprehensive scopes for reading all messages
        # channels:read - View basic channel info
        # channels:history - View messages in public channels
        # channels:join - Join public channels (to access all channels)
        # groups:read - View private channels info
        # groups:history - View messages in private channels the bot is in
        # im:history - View direct messages
        # mpim:history - View group direct messages
        # users:read - View user info (for resolving @mentions)
        # team:read - View workspace info
        scopes = "channels:read,channels:history,channels:join,groups:read,groups:history,im:history,mpim:history,users:read,team:read"

        auth_url = (
            f"https://slack.com/oauth/v2/authorize"
            f"?client_id={client_id}"
            f"&scope={scopes}"
            f"&redirect_uri={redirect_uri}"
            f"&state={state}"
        )

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


@integration_bp.route('/slack/channels', methods=['GET'])
@require_auth
def slack_channels():
    """
    Get list of Slack channels for selection.
    User can choose which channels to sync.
    """
    try:
        import requests

        db = get_db()
        try:
            connector = db.query(Connector).filter(
                Connector.tenant_id == g.tenant_id,
                Connector.connector_type == ConnectorType.SLACK,
                Connector.status == ConnectorStatus.CONNECTED
            ).first()

            if not connector:
                return jsonify({
                    "success": False,
                    "error": "Slack not connected"
                }), 400

            # Get channels from Slack API
            response = requests.get(
                "https://slack.com/api/conversations.list",
                headers={"Authorization": f"Bearer {connector.access_token}"},
                params={
                    "types": "public_channel,private_channel",
                    "exclude_archived": "true",
                    "limit": 200
                }
            )

            data = response.json()

            if not data.get("ok"):
                return jsonify({
                    "success": False,
                    "error": data.get("error", "Failed to fetch channels")
                }), 400

            # Get currently selected channels from settings
            current_settings = connector.settings or {}
            selected_channels = current_settings.get("channels", [])

            channels = []
            for ch in data.get("channels", []):
                channels.append({
                    "id": ch["id"],
                    "name": ch["name"],
                    "is_private": ch.get("is_private", False),
                    "is_member": ch.get("is_member", False),
                    "member_count": ch.get("num_members", 0),
                    "selected": ch["id"] in selected_channels or len(selected_channels) == 0
                })

            return jsonify({
                "success": True,
                "channels": channels,
                "total": len(channels),
                "selected_count": len(selected_channels) if selected_channels else len(channels)
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@integration_bp.route('/slack/channels', methods=['PUT'])
@require_auth
def update_slack_channels():
    """
    Update which Slack channels to sync.
    """
    try:
        data = request.get_json()
        channel_ids = data.get("channels", [])

        db = get_db()
        try:
            connector = db.query(Connector).filter(
                Connector.tenant_id == g.tenant_id,
                Connector.connector_type == ConnectorType.SLACK,
                Connector.is_active == True
            ).first()

            if not connector:
                return jsonify({
                    "success": False,
                    "error": "Slack not connected"
                }), 400

            # Update settings
            current_settings = connector.settings or {}
            current_settings["channels"] = channel_ids
            connector.settings = current_settings
            connector.updated_at = utc_now()

            db.commit()

            return jsonify({
                "success": True,
                "message": f"Updated to sync {len(channel_ids)} channels",
                "channels": channel_ids
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@integration_bp.route('/slack/token', methods=['POST'])
@require_auth
def slack_token():
    """
    Connect Slack using a Bot User OAuth Token directly.
    This is simpler than OAuth flow for internal/development apps.

    Request body:
    {
        "access_token": "xoxb-..."
    }
    """
    try:
        import requests as req

        data = request.get_json()
        access_token = data.get("access_token", "")

        if not access_token.startswith("xoxb-"):
            return jsonify({
                "success": False,
                "error": "Invalid token format. Token should start with 'xoxb-'"
            }), 400

        # Test the token by calling auth.test
        test_response = req.get(
            "https://slack.com/api/auth.test",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        test_data = test_response.json()

        if not test_data.get("ok"):
            return jsonify({
                "success": False,
                "error": f"Invalid token: {test_data.get('error', 'unknown error')}"
            }), 400

        team_name = test_data.get("team", "Slack")
        team_id = test_data.get("team_id", "")

        # Save connector
        db = get_db()
        try:
            connector = db.query(Connector).filter(
                Connector.tenant_id == g.tenant_id,
                Connector.connector_type == ConnectorType.SLACK
            ).first()

            if connector:
                connector.access_token = access_token
                connector.status = ConnectorStatus.CONNECTED
                connector.is_active = True  # Re-enable connector on reconnect
                connector.name = team_name
                connector.error_message = None
                connector.settings = {
                    "team_id": team_id,
                    "team_name": team_name,
                    "connected_via": "token"
                }
                connector.updated_at = utc_now()
            else:
                connector = Connector(
                    tenant_id=g.tenant_id,
                    user_id=g.user_id,
                    connector_type=ConnectorType.SLACK,
                    name=team_name,
                    status=ConnectorStatus.CONNECTED,
                    access_token=access_token,
                    settings={
                        "team_id": team_id,
                        "team_name": team_name,
                        "connected_via": "token"
                    }
                )
                db.add(connector)

            db.commit()

            return jsonify({
                "success": True,
                "message": f"Connected to {team_name}",
                "team_name": team_name
            })

        finally:
            db.close()

    except Exception as e:
        print(f"[Slack Token] Error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@integration_bp.route('/slack/callback', methods=['GET'])
def slack_callback():
    """
    Slack OAuth callback handler.
    """
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

    try:
        import requests

        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')

        print(f"[Slack Callback] code={code[:20] if code else None}..., state={state}, error={error}")

        if error:
            return redirect(f"{FRONTEND_URL}/integrations?error={error}")

        if not code or not state:
            return redirect(f"{FRONTEND_URL}/integrations?error=missing_params")

        # Verify JWT-based state
        state_data, error_msg = verify_oauth_state(state)
        if error_msg or not state_data or state_data.get("connector_type") != "slack":
            print(f"[Slack Callback] Invalid state: {error_msg}")
            return redirect(f"{FRONTEND_URL}/integrations?error=invalid_state")

        # Exchange code for tokens
        client_id = os.getenv("SLACK_CLIENT_ID", "")
        client_secret = os.getenv("SLACK_CLIENT_SECRET", "")
        redirect_uri = os.getenv(
            "SLACK_REDIRECT_URI",
            "http://localhost:5003/api/integrations/slack/callback"
        )

        print(f"[Slack Callback] Exchanging code for token with redirect_uri={redirect_uri}")

        response = requests.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri
            }
        )

        data = response.json()
        print(f"[Slack Callback] Token response: ok={data.get('ok')}, error={data.get('error')}")

        if not data.get("ok"):
            error_msg = data.get('error', 'unknown')
            print(f"[Slack Callback] OAuth failed: {error_msg}")
            return redirect(f"{FRONTEND_URL}/integrations?error={error_msg}")

        # Save connector
        db = get_db()
        try:
            connector = db.query(Connector).filter(
                Connector.tenant_id == state_data["tenant_id"],
                Connector.connector_type == ConnectorType.SLACK
            ).first()

            access_token = data.get("access_token")
            team_name = data.get("team", {}).get("name", "Slack")
            is_first_connection = connector is None

            if connector:
                connector.access_token = access_token
                connector.status = ConnectorStatus.CONNECTED
                connector.is_active = True  # Re-enable connector on reconnect
                connector.name = team_name
                connector.error_message = None
                connector.settings = {
                    "team_id": data.get("team", {}).get("id"),
                    "team_name": team_name,
                    "bot_user_id": data.get("bot_user_id")
                }
                connector.updated_at = utc_now()
            else:
                connector = Connector(
                    tenant_id=state_data["tenant_id"],
                    user_id=state_data["user_id"],
                    connector_type=ConnectorType.SLACK,
                    name=team_name,
                    status=ConnectorStatus.CONNECTED,
                    access_token=access_token,
                    token_scopes=data.get("scope", "").split(","),
                    settings={
                        "team_id": data.get("team", {}).get("id"),
                        "team_name": team_name,
                        "bot_user_id": data.get("bot_user_id")
                    }
                )
                db.add(connector)

            db.commit()
            print(f"[Slack Callback] Successfully saved connector for team: {team_name}")

            # Auto-sync on first connection
            if is_first_connection:
                import threading
                connector_id = connector.id
                tenant_id = state_data["tenant_id"]
                user_id = state_data["user_id"]

                def run_initial_sync():
                    _run_connector_sync(
                        connector_id=connector_id,
                        connector_type="slack",
                        since=None,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        full_sync=True
                    )

                thread = threading.Thread(target=run_initial_sync)
                thread.daemon = True
                thread.start()

                print(f"[Slack Callback] Started auto-sync for first-time connection")

            return redirect(f"{FRONTEND_URL}/integrations?success=slack")

        finally:
            db.close()

    except Exception as e:
        print(f"[Slack Callback] Exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return redirect(f"{FRONTEND_URL}/integrations?error={str(e)}")


# ============================================================================
# BOX INTEGRATION
# ============================================================================

@integration_bp.route('/box/auth', methods=['GET'])
@require_auth
def box_auth():
    """
    Start Box OAuth flow.
    """
    try:
        print("[BoxAuth] Starting Box OAuth flow...")
        from connectors.box_connector import BoxConnector

        # Generate JWT-based state (works across multiple workers)
        redirect_uri = os.getenv(
            "BOX_REDIRECT_URI",
            "http://localhost:5003/api/integrations/box/callback"
        )
        print(f"[BoxAuth] Redirect URI: {redirect_uri}")

        state = create_oauth_state(
            tenant_id=g.tenant_id,
            user_id=g.user_id,
            connector_type="box",
            extra_data={"redirect_uri": redirect_uri}
        )
        print(f"[BoxAuth] JWT state created for tenant: {g.tenant_id}")

        # Get auth URL
        print("[BoxAuth] Getting auth URL from BoxConnector...")
        auth_url = BoxConnector.get_auth_url(redirect_uri, state)
        print(f"[BoxAuth] Auth URL generated: {auth_url[:100]}...")

        return jsonify({
            "success": True,
            "auth_url": auth_url,
            "state": state
        })

    except ImportError as e:
        print(f"[BoxAuth] ImportError: {e}")
        return jsonify({
            "success": False,
            "error": "Box SDK not installed. Run: pip install boxsdk"
        }), 500
    except Exception as e:
        import traceback
        print(f"[BoxAuth] Exception: {e}")
        print(f"[BoxAuth] Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@integration_bp.route('/box/callback', methods=['GET'])
def box_callback():
    """
    Box OAuth callback handler.
    """
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

    try:
        from connectors.box_connector import BoxConnector

        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')

        if error:
            return redirect(f"{FRONTEND_URL}/integrations?error={error}")

        if not code or not state:
            return redirect(f"{FRONTEND_URL}/integrations?error=missing_params")

        # Verify JWT-based state
        state_data, error = verify_oauth_state(state)
        if error or not state_data or state_data.get("connector_type") != "box":
            print(f"[BoxCallback] Invalid state: {error}")
            return redirect(f"{FRONTEND_URL}/integrations?error=invalid_state")

        # Exchange code for tokens
        redirect_uri = state_data.get("data", {}).get("redirect_uri")
        tokens, error = BoxConnector.exchange_code_for_tokens(code, redirect_uri)

        if error:
            return redirect(f"{FRONTEND_URL}/integrations?error={error}")

        # Save connector
        db = get_db()
        try:
            connector = db.query(Connector).filter(
                Connector.tenant_id == state_data["tenant_id"],
                Connector.connector_type == ConnectorType.BOX
            ).first()

            is_first_connection = connector is None

            if connector:
                connector.access_token = tokens["access_token"]
                connector.refresh_token = tokens["refresh_token"]
                connector.status = ConnectorStatus.CONNECTED
                connector.is_active = True  # Re-enable connector on reconnect
                connector.error_message = None
                connector.updated_at = utc_now()
            else:
                connector = Connector(
                    tenant_id=state_data["tenant_id"],
                    user_id=state_data["user_id"],
                    connector_type=ConnectorType.BOX,
                    name="Box",
                    status=ConnectorStatus.CONNECTED,
                    access_token=tokens["access_token"],
                    refresh_token=tokens["refresh_token"]
                )
                db.add(connector)

            db.commit()

            # Auto-sync on first connection
            if is_first_connection:
                import threading
                connector_id = connector.id
                tenant_id = state_data["tenant_id"]
                user_id = state_data["user_id"]

                def run_initial_sync():
                    _run_connector_sync(
                        connector_id=connector_id,
                        connector_type="box",
                        since=None,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        full_sync=True
                    )

                thread = threading.Thread(target=run_initial_sync)
                thread.daemon = True
                thread.start()

                print(f"[Box Callback] Started auto-sync for first-time connection")

            return redirect(f"{FRONTEND_URL}/integrations?success=box")

        finally:
            db.close()

    except Exception as e:
        return redirect(f"{FRONTEND_URL}/integrations?error={str(e)}")


@integration_bp.route('/box/folders', methods=['GET'])
@require_auth
def box_folders():
    """
    Get Box folder structure for configuration.
    """
    try:
        from connectors.box_connector import BoxConnector

        db = get_db()
        try:
            connector = db.query(Connector).filter(
                Connector.tenant_id == g.tenant_id,
                Connector.connector_type == ConnectorType.BOX,
                Connector.status == ConnectorStatus.CONNECTED
            ).first()

            if not connector:
                return jsonify({
                    "success": False,
                    "error": "Box not connected"
                }), 400

            # Create connector instance and get folder tree
            from connectors.base_connector import ConnectorConfig

            config = ConnectorConfig(
                connector_type="box",
                credentials={
                    "access_token": connector.access_token,
                    "refresh_token": connector.refresh_token
                },
                settings=connector.settings or {}
            )

            box = BoxConnector(config)

            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                connected = loop.run_until_complete(box.connect())
                if not connected:
                    return jsonify({
                        "success": False,
                        "error": "Failed to connect to Box"
                    }), 400

                folder_id = request.args.get('folder_id', '0')
                depth = int(request.args.get('depth', '2'))

                folders = loop.run_until_complete(
                    box.get_folder_structure(folder_id, depth)
                )

                return jsonify({
                    "success": True,
                    "folders": folders
                })

            finally:
                loop.close()

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# GITHUB INTEGRATION
# ============================================================================

@integration_bp.route('/github/auth', methods=['GET'])
@require_auth
def github_auth():
    """
    Start GitHub OAuth flow.
    """
    try:
        print("[GitHubAuth] Starting GitHub OAuth flow...")

        client_id = os.getenv("GITHUB_CLIENT_ID", "")
        redirect_uri = os.getenv(
            "GITHUB_REDIRECT_URI",
            "http://localhost:5003/api/integrations/github/callback"
        )

        if not client_id:
            return jsonify({
                "success": False,
                "error": "GitHub Client ID not configured"
            }), 500

        print(f"[GitHubAuth] Client ID: {client_id[:10]}...")
        print(f"[GitHubAuth] Redirect URI: {redirect_uri}")

        # Create JWT state
        state = create_oauth_state(
            tenant_id=g.tenant_id,
            user_id=g.user_id,
            connector_type="github",
            extra_data={"redirect_uri": redirect_uri}
        )
        print(f"[GitHubAuth] JWT state created for tenant: {g.tenant_id}")

        # Build GitHub OAuth URL
        auth_url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&state={state}"
            f"&scope=repo,read:user,read:org"  # Scopes for reading repos and user info
        )

        print(f"[GitHubAuth] Auth URL generated: {auth_url[:100]}...")

        return jsonify({
            "success": True,
            "auth_url": auth_url,
            "state": state
        })

    except Exception as e:
        import traceback
        print(f"[GitHubAuth] Exception: {e}")
        print(f"[GitHubAuth] Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@integration_bp.route('/github/callback', methods=['GET'])
def github_callback():
    """
    GitHub OAuth callback handler.
    """
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

    try:
        import requests

        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')

        print(f"[GitHub Callback] code={code[:20] if code else None}..., state={state}, error={error}")

        if error:
            return redirect(f"{FRONTEND_URL}/integrations?error={error}")

        if not code or not state:
            return redirect(f"{FRONTEND_URL}/integrations?error=missing_params")

        # Verify JWT state
        state_data, error_msg = verify_oauth_state(state)
        if error_msg or not state_data or state_data.get("connector_type") != "github":
            print(f"[GitHub Callback] Invalid state: {error_msg}")
            return redirect(f"{FRONTEND_URL}/integrations?error=invalid_state")

        tenant_id = state_data.get("tenant_id")
        user_id = state_data.get("user_id")
        redirect_uri = state_data.get("data", {}).get("redirect_uri")

        print(f"[GitHub Callback] JWT state verified for tenant: {tenant_id}")

        # Exchange code for token
        client_id = os.getenv("GITHUB_CLIENT_ID", "")
        client_secret = os.getenv("GITHUB_CLIENT_SECRET", "")

        print(f"[GitHub Callback] Exchanging code for token...")

        response = requests.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri
            },
            headers={"Accept": "application/json"}
        )

        data = response.json()
        print(f"[GitHub Callback] Token response: {list(data.keys())}")

        if "error" in data:
            error_msg = data.get('error_description', data.get('error', 'unknown'))
            print(f"[GitHub Callback] OAuth failed: {error_msg}")
            return redirect(f"{FRONTEND_URL}/integrations?error={error_msg}")

        access_token = data.get("access_token")
        if not access_token:
            return redirect(f"{FRONTEND_URL}/integrations?error=no_access_token")

        # Get user info
        user_response = requests.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json"
            }
        )
        user_data = user_response.json()
        github_username = user_data.get("login", "GitHub")

        # Save connector
        db = get_db()
        try:
            connector = db.query(Connector).filter(
                Connector.tenant_id == tenant_id,
                Connector.connector_type == ConnectorType.GITHUB
            ).first()

            is_first_connection = connector is None

            if connector:
                connector.access_token = access_token
                connector.status = ConnectorStatus.CONNECTED
                connector.is_active = True
                connector.name = f"GitHub ({github_username})"
                connector.error_message = None
                connector.settings = {
                    "username": github_username,
                    "user_id": user_data.get("id")
                }
                connector.updated_at = utc_now()
            else:
                connector = Connector(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    connector_type=ConnectorType.GITHUB,
                    name=f"GitHub ({github_username})",
                    status=ConnectorStatus.CONNECTED,
                    access_token=access_token,
                    token_scopes=data.get("scope", "").split(","),
                    settings={
                        "username": github_username,
                        "user_id": user_data.get("id")
                    }
                )
                db.add(connector)

            db.commit()
            print(f"[GitHub Callback] Successfully saved connector for user: {github_username}")

            # Auto-sync on first connection
            if is_first_connection:
                import threading
                connector_id = connector.id
                sync_tenant_id = tenant_id
                sync_user_id = user_id

                def run_initial_sync():
                    _run_connector_sync(
                        connector_id=connector_id,
                        connector_type="github",
                        since=None,
                        tenant_id=sync_tenant_id,
                        user_id=sync_user_id,
                        full_sync=True
                    )

                thread = threading.Thread(target=run_initial_sync)
                thread.daemon = True
                thread.start()

                print(f"[GitHub Callback] Started auto-sync for first-time connection")

            return redirect(f"{FRONTEND_URL}/integrations?success=github")

        finally:
            db.close()

    except Exception as e:
        print(f"[GitHub Callback] Exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return redirect(f"{FRONTEND_URL}/integrations?error={str(e)}")


# ============================================================================
# ONEDRIVE (MICROSOFT 365) INTEGRATION
# ============================================================================

@integration_bp.route('/onedrive/auth', methods=['GET'])
@require_auth
def onedrive_auth():
    """
    Start OneDrive/Microsoft 365 OAuth flow.
    """
    try:
        print("[OneDriveAuth] Starting OneDrive OAuth flow...")
        from connectors.onedrive_connector import OneDriveConnector

        # Generate state
        state = secrets.token_urlsafe(32)
        redirect_uri = os.getenv(
            "MICROSOFT_REDIRECT_URI",
            "http://localhost:5003/api/integrations/onedrive/callback"
        )
        print(f"[OneDriveAuth] Redirect URI: {redirect_uri}")

        # Store state
        oauth_states[state] = {
            "type": "onedrive",
            "tenant_id": g.tenant_id,
            "user_id": g.user_id,
            "redirect_uri": redirect_uri,
            "created_at": utc_now().isoformat()
        }
        print(f"[OneDriveAuth] State stored for tenant: {g.tenant_id}")

        # Get auth URL
        print("[OneDriveAuth] Getting auth URL from OneDriveConnector...")
        auth_url = OneDriveConnector.get_auth_url(redirect_uri, state)
        print(f"[OneDriveAuth] Auth URL generated: {auth_url[:100]}...")

        return jsonify({
            "success": True,
            "auth_url": auth_url,
            "state": state
        })

    except ImportError as e:
        print(f"[OneDriveAuth] ImportError: {e}")
        return jsonify({
            "success": False,
            "error": "MSAL not installed. Run: pip install msal"
        }), 500
    except Exception as e:
        import traceback
        print(f"[OneDriveAuth] Exception: {e}")
        print(f"[OneDriveAuth] Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@integration_bp.route('/onedrive/callback', methods=['GET'])
def onedrive_callback():
    """
    OneDrive OAuth callback handler.
    """
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

    try:
        from connectors.onedrive_connector import OneDriveConnector

        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')

        if error:
            return redirect(f"{FRONTEND_URL}/integrations?error={error}")

        if not code or not state:
            return redirect(f"{FRONTEND_URL}/integrations?error=missing_params")

        # Verify state
        state_data = oauth_states.pop(state, None)
        if not state_data or state_data["type"] != "onedrive":
            return redirect(f"{FRONTEND_URL}/integrations?error=invalid_state")

        # Exchange code for tokens
        redirect_uri = state_data["redirect_uri"]
        tokens, error = OneDriveConnector.exchange_code_for_tokens(code, redirect_uri)

        if error:
            return redirect(f"{FRONTEND_URL}/integrations?error={error}")

        # Save connector
        db = get_db()
        try:
            connector = db.query(Connector).filter(
                Connector.tenant_id == state_data["tenant_id"],
                Connector.connector_type == ConnectorType.ONEDRIVE
            ).first()

            is_first_connection = connector is None

            if connector:
                connector.access_token = tokens["access_token"]
                connector.refresh_token = tokens["refresh_token"]
                connector.status = ConnectorStatus.CONNECTED
                connector.is_active = True
                connector.error_message = None
                connector.updated_at = utc_now()
            else:
                connector = Connector(
                    tenant_id=state_data["tenant_id"],
                    user_id=state_data["user_id"],
                    connector_type=ConnectorType.ONEDRIVE,
                    name="OneDrive",
                    status=ConnectorStatus.CONNECTED,
                    access_token=tokens["access_token"],
                    refresh_token=tokens["refresh_token"]
                )
                db.add(connector)

            db.commit()
            print(f"[OneDrive Callback] Successfully saved connector")

            # Auto-sync on first connection
            if is_first_connection:
                import threading
                connector_id = connector.id
                tenant_id = state_data["tenant_id"]
                user_id = state_data["user_id"]

                def run_initial_sync():
                    _run_connector_sync(
                        connector_id=connector_id,
                        connector_type="onedrive",
                        since=None,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        full_sync=True
                    )

                thread = threading.Thread(target=run_initial_sync)
                thread.daemon = True
                thread.start()

                print(f"[OneDrive Callback] Started auto-sync for first-time connection")

            return redirect(f"{FRONTEND_URL}/integrations?success=onedrive")

        finally:
            db.close()

    except Exception as e:
        return redirect(f"{FRONTEND_URL}/integrations?error={str(e)}")


# ============================================================================
# SYNC OPERATIONS
# ============================================================================

@integration_bp.route('/<connector_type>/sync', methods=['POST'])
@require_auth
def sync_connector(connector_type: str):
    """
    Trigger sync for a connector.

    URL params:
        connector_type: gmail, slack, or box

    Request body (optional):
    {
        "full_sync": false,  // If true, sync all data
        "since": "2024-01-01T00:00:00Z"  // Only sync after this date
    }

    Response:
    {
        "success": true,
        "job_id": "...",
        "message": "Sync started"
    }
    """
    try:
        # Map string to enum
        type_map = {
            "gmail": ConnectorType.GMAIL,
            "slack": ConnectorType.SLACK,
            "box": ConnectorType.BOX,
            "github": ConnectorType.GITHUB
        }

        if connector_type not in type_map:
            return jsonify({
                "success": False,
                "error": f"Invalid connector type: {connector_type}"
            }), 400

        data = request.get_json() or {}
        full_sync = data.get('full_sync', False)
        since_str = data.get('since')

        since = None
        if since_str and not full_sync:
            since = datetime.fromisoformat(since_str.replace('Z', '+00:00'))

        db = get_db()
        try:
            connector = db.query(Connector).filter(
                Connector.tenant_id == g.tenant_id,
                Connector.connector_type == type_map[connector_type],
                Connector.status == ConnectorStatus.CONNECTED
            ).first()

            if not connector:
                return jsonify({
                    "success": False,
                    "error": f"{connector_type.title()} not connected"
                }), 400

            # Update status
            connector.status = ConnectorStatus.SYNCING
            db.commit()

            # In production, use Celery for background processing
            # For now, run sync in thread
            import threading

            # Capture values before starting thread (g is not available in thread)
            tenant_id = g.tenant_id
            user_id = g.user_id
            connector_id = connector.id

            def run_sync():
                _run_connector_sync(
                    connector_id,
                    connector_type,
                    since,
                    tenant_id,
                    user_id,
                    full_sync
                )

            thread = threading.Thread(target=run_sync)
            thread.start()

            return jsonify({
                "success": True,
                "message": f"{connector_type.title()} sync started",
                "connector_id": connector.id
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


def _run_connector_sync(
    connector_id: str,
    connector_type: str,
    since: datetime,
    tenant_id: str,
    user_id: str,
    full_sync: bool = False
):
    """Background sync function with progress tracking"""
    import time

    # Initialize progress
    progress_key = f"{tenant_id}:{connector_type}"
    sync_progress[progress_key] = {
        "status": "syncing",
        "progress": 5,
        "documents_found": 0,
        "documents_parsed": 0,
        "documents_embedded": 0,
        "current_file": None,
        "error": None,
        "started_at": utc_now().isoformat()
    }

    db = get_db()
    try:
        connector = db.query(Connector).filter(
            Connector.id == connector_id
        ).first()

        if not connector:
            sync_progress[progress_key]["status"] = "error"
            sync_progress[progress_key]["error"] = "Connector not found"
            return

        try:
            # Get connector class
            if connector_type == "gmail":
                from connectors.gmail_connector import GmailConnector
                ConnectorClass = GmailConnector
            elif connector_type == "slack":
                # Use basic SlackConnector (no filtering, captures all messages)
                from connectors.slack_connector import SlackConnector
                ConnectorClass = SlackConnector
            elif connector_type == "box":
                from connectors.box_connector import BoxConnector
                ConnectorClass = BoxConnector
            elif connector_type == "github":
                from connectors.github_connector import GitHubConnector
                ConnectorClass = GitHubConnector
            elif connector_type == "onedrive":
                from connectors.onedrive_connector import OneDriveConnector
                ConnectorClass = OneDriveConnector
            else:
                sync_progress[progress_key]["status"] = "error"
                sync_progress[progress_key]["error"] = f"Unknown connector type: {connector_type}"
                return

            # Create connector instance
            from connectors.base_connector import ConnectorConfig

            config = ConnectorConfig(
                connector_type=connector_type,
                user_id=user_id,
                credentials={
                    "access_token": connector.access_token,
                    "refresh_token": connector.refresh_token
                },
                settings=connector.settings or {}
            )

            instance = ConnectorClass(config)

            # Update progress - connecting
            sync_progress[progress_key]["progress"] = 10
            sync_progress[progress_key]["current_file"] = "Connecting to service..."

            # Run sync
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                # Check if this is the first sync (no documents exist for this connector)
                existing_doc_count = db.query(Document).filter(
                    Document.tenant_id == tenant_id,
                    Document.connector_id == connector.id
                ).count()

                # Force full sync if no EMBEDDED documents exist yet (first successful sync)
                embedded_doc_count = db.query(Document).filter(
                    Document.tenant_id == tenant_id,
                    Document.connector_id == connector.id,
                    Document.embedded_at.isnot(None)
                ).count()

                if embedded_doc_count == 0:
                    full_sync = True
                    since = None
                    print(f"[Sync] First sync detected for {connector_type} (no embedded docs), doing full sync")

                    # Clear any deleted document records on first sync (fresh start)
                    deleted_count = db.query(DeletedDocument).filter(
                        DeletedDocument.tenant_id == tenant_id,
                        DeletedDocument.connector_id == connector.id
                    ).delete()
                    if deleted_count > 0:
                        db.commit()
                        print(f"[Sync] Cleared {deleted_count} deleted document records for fresh start")
                # Use last sync time if not doing full sync
                elif not since and connector.last_sync_at and not full_sync:
                    since = connector.last_sync_at

                # Update progress - fetching
                sync_progress[progress_key]["progress"] = 20
                sync_progress[progress_key]["current_file"] = "Fetching documents..."

                documents = loop.run_until_complete(instance.sync(since))

                # Get list of deleted external_ids to skip (user permanently deleted these)
                deleted_external_ids = set(
                    d.external_id for d in db.query(DeletedDocument.external_id).filter(
                        DeletedDocument.tenant_id == tenant_id,
                        DeletedDocument.connector_id == connector.id
                    ).all()
                )
                print(f"[Sync] Deleted document IDs: {len(deleted_external_ids)}")

                # Get list of existing external_ids to avoid duplicates
                # CRITICAL: Only skip documents that:
                # 1. Are fully embedded (embedded_at != None)
                # 2. AND have actual content (to allow re-processing of empty content docs)
                existing_docs_query = db.query(Document).filter(
                    Document.tenant_id == tenant_id,
                    Document.connector_id == connector.id,
                    Document.external_id != None,
                    Document.embedded_at != None  # Only skip if already embedded
                ).all()

                # Additionally filter out docs with empty/minimal content (likely failed extractions)
                existing_external_ids = set(
                    doc.external_id for doc in existing_docs_query
                    if doc.content and len(doc.content.strip()) > 100  # Must have real content
                )
                print(f"[Sync] Existing embedded document IDs with content: {len(existing_external_ids)}")

                # Check un-embedded existing documents for debugging
                un_embedded_existing = db.query(Document).filter(
                    Document.tenant_id == tenant_id,
                    Document.connector_id == connector.id,
                    Document.external_id != None,
                    Document.embedded_at == None  # Not embedded
                ).all()
                un_embedded_ids = [doc.external_id for doc in un_embedded_existing]
                print(f"[Sync] Un-embedded existing documents: {len(un_embedded_existing)} - {un_embedded_ids[:5]}")

                # Delete documents with empty content so they can be re-synced
                empty_content_docs = [doc for doc in un_embedded_existing if not doc.content or len(doc.content.strip()) < 100]
                if empty_content_docs:
                    print(f"[Sync] Deleting {len(empty_content_docs)} documents with empty content for re-sync")
                    for doc in empty_content_docs:
                        db.delete(doc)
                    db.commit()

                # Filter out deleted and existing documents
                original_count = len(documents) if documents else 0
                documents = [
                    doc for doc in (documents or [])
                    if doc.doc_id not in deleted_external_ids and doc.doc_id not in existing_external_ids
                ]
                skipped_deleted = original_count - len(documents) - len([
                    d for d in (documents or []) if d.doc_id in existing_external_ids
                ])

                # Update progress - documents found
                sync_progress[progress_key]["documents_found"] = len(documents)
                sync_progress[progress_key]["documents_skipped"] = original_count - len(documents)
                sync_progress[progress_key]["progress"] = 40
                sync_progress[progress_key]["status"] = "parsing"

                print(f"[Sync] Found {original_count} docs, skipping {original_count - len(documents)} (deleted or existing), processing {len(documents)}")

                # Save documents to database with progress updates
                total_docs = len(documents) if documents else 1
                for i, doc in enumerate(documents):
                    # Update progress
                    parse_progress = 40 + int((i / total_docs) * 30)
                    sync_progress[progress_key]["progress"] = parse_progress
                    sync_progress[progress_key]["documents_parsed"] = i + 1
                    sync_progress[progress_key]["current_file"] = doc.title[:50] if doc.title else f"Document {i+1}"

                    # Map connector Document attributes to database Document fields
                    # Connector Document uses: doc_id, source, content, title, metadata, timestamp, author
                    # Database Document expects: external_id, source_type, content, title, metadata, source_created_at, etc.
                    db_doc = Document(
                        tenant_id=tenant_id,
                        connector_id=connector.id,
                        external_id=doc.doc_id,  # Fixed: was source_id, now doc_id
                        source_type=doc.source,  # Fixed: was source_type, now source
                        title=doc.title,
                        content=doc.content,
                        metadata=doc.metadata,
                        sender=doc.author,
                        source_created_at=doc.timestamp,  # Fixed: was created_at, now timestamp
                        source_updated_at=doc.timestamp,  # Fixed: was updated_at, now timestamp
                        status=DocumentStatus.PENDING,
                        classification=DocumentClassification.UNKNOWN
                    )
                    db.add(db_doc)

                    # Small delay to make progress visible
                    time.sleep(0.05)

                # Commit documents to DB first
                db.commit()

                # Update progress - embedding phase
                sync_progress[progress_key]["status"] = "embedding"
                sync_progress[progress_key]["progress"] = 75
                sync_progress[progress_key]["current_file"] = "Creating embeddings..."

                # REAL EMBEDDING: Embed documents to Pinecone
                try:
                    print(f"[Sync] Starting embedding for {len(documents)} new documents...")

                    # Query ALL un-embedded documents for this connector (including from previous failed syncs)
                    un_embedded_docs = db.query(Document).filter(
                        Document.tenant_id == tenant_id,
                        Document.connector_id == connector.id,
                        Document.embedded_at == None
                    ).all()

                    doc_ids = [doc.id for doc in un_embedded_docs]
                    print(f"[Sync] Found {len(doc_ids)} total un-embedded documents (including from previous syncs)")

                    if doc_ids:
                        # Get fresh document objects (with tenant_id filter for defense-in-depth)
                        docs_to_embed = db.query(Document).filter(
                            Document.id.in_(doc_ids),
                            Document.tenant_id == tenant_id  # Security: ensure tenant isolation
                        ).all()

                        # STEP 1: Extract structured summaries (for Knowledge Gap analysis)
                        sync_progress[progress_key]["current_file"] = "Extracting document summaries..."
                        sync_progress[progress_key]["progress"] = 85
                        try:
                            extraction_service = get_extraction_service()
                            extract_result = extraction_service.extract_documents(
                                documents=docs_to_embed,
                                db=db,
                                force=False
                            )
                            sync_progress[progress_key]["documents_extracted"] = extract_result.get('extracted', 0)
                            print(f"[Sync] Extracted summaries for {extract_result.get('extracted', 0)} documents")
                        except Exception as extract_error:
                            print(f"[Sync] Extraction error (non-fatal): {extract_error}")
                            sync_progress[progress_key]["extraction_error"] = str(extract_error)

                        # STEP 2: Embed to Pinecone (for RAG search)
                        sync_progress[progress_key]["current_file"] = "Embedding documents..."
                        sync_progress[progress_key]["progress"] = 90

                        print(f"[Sync] Calling embedding_service.embed_documents() with {len(docs_to_embed)} documents")
                        embedding_service = get_embedding_service()
                        embed_result = embedding_service.embed_documents(
                            documents=docs_to_embed,
                            tenant_id=tenant_id,
                            db=db,
                            force_reembed=False
                        )

                        sync_progress[progress_key]["documents_embedded"] = embed_result.get('embedded', 0)
                        sync_progress[progress_key]["chunks_created"] = embed_result.get('chunks', 0)

                        print(f"[Sync] Embedding result: embedded={embed_result.get('embedded', 0)}, chunks={embed_result.get('chunks', 0)}, skipped={embed_result.get('skipped', 0)}")
                        if embed_result.get('errors'):
                            print(f"[Sync] Embedding errors: {embed_result['errors']}")
                        if embed_result.get('embedded', 0) == 0 and len(docs_to_embed) > 0:
                            print(f"[Sync] WARNING: 0 documents embedded but {len(docs_to_embed)} were provided!")
                    else:
                        print(f"[Sync] No un-embedded documents found - all documents are already embedded or processed")

                except Exception as embed_error:
                    print(f"[Sync] Embedding error (non-fatal): {embed_error}")
                    # Don't fail the sync, just log the error
                    sync_progress[progress_key]["embedding_error"] = str(embed_error)

                sync_progress[progress_key]["progress"] = 95

                # Update connector
                connector.status = ConnectorStatus.CONNECTED
                connector.last_sync_at = utc_now()
                connector.last_sync_status = "success"
                connector.last_sync_items_count = len(documents)
                connector.total_items_synced += len(documents)
                connector.error_message = None

                db.commit()

                # Mark complete
                sync_progress[progress_key]["status"] = "completed"
                sync_progress[progress_key]["progress"] = 100
                sync_progress[progress_key]["current_file"] = None

            finally:
                loop.close()

        except Exception as e:
            connector.status = ConnectorStatus.ERROR
            connector.last_sync_status = "error"
            connector.last_sync_error = str(e)
            connector.error_message = str(e)
            db.commit()

            # Update progress with error
            sync_progress[progress_key]["status"] = "error"
            sync_progress[progress_key]["error"] = str(e)

    finally:
        db.close()


@integration_bp.route('/<connector_type>/sync/status', methods=['GET'])
@require_auth
def get_sync_status(connector_type: str):
    """
    Get the current sync status for a connector.

    Response:
    {
        "success": true,
        "status": {
            "status": "syncing" | "parsing" | "embedding" | "completed" | "error",
            "progress": 0-100,
            "documents_found": 10,
            "documents_parsed": 5,
            "documents_embedded": 3,
            "current_file": "document.pdf",
            "error": null
        }
    }
    """
    try:
        progress_key = f"{g.tenant_id}:{connector_type}"

        if progress_key not in sync_progress:
            # No active sync, check connector status
            type_map = {
                "gmail": ConnectorType.GMAIL,
                "slack": ConnectorType.SLACK,
                "box": ConnectorType.BOX,
                "github": ConnectorType.GITHUB
            }

            if connector_type not in type_map:
                return jsonify({
                    "success": False,
                    "error": f"Invalid connector type: {connector_type}"
                }), 400

            db = get_db()
            try:
                connector = db.query(Connector).filter(
                    Connector.tenant_id == g.tenant_id,
                    Connector.connector_type == type_map[connector_type],
                    Connector.is_active == True
                ).first()

                if connector and connector.status == ConnectorStatus.SYNCING:
                    return jsonify({
                        "success": True,
                        "status": {
                            "status": "syncing",
                            "progress": 10,
                            "documents_found": 0,
                            "documents_parsed": 0,
                            "documents_embedded": 0,
                            "current_file": "Initializing...",
                            "error": None
                        }
                    })

                return jsonify({
                    "success": True,
                    "status": {
                        "status": "idle",
                        "progress": 0,
                        "documents_found": 0,
                        "documents_parsed": 0,
                        "documents_embedded": 0,
                        "current_file": None,
                        "error": None
                    }
                })
            finally:
                db.close()

        return jsonify({
            "success": True,
            "status": sync_progress[progress_key]
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# DISCONNECT
# ============================================================================

@integration_bp.route('/<connector_type>/disconnect', methods=['POST'])
@require_auth
def disconnect_connector(connector_type: str):
    """
    Disconnect an integration.
    """
    try:
        type_map = {
            "gmail": ConnectorType.GMAIL,
            "slack": ConnectorType.SLACK,
            "box": ConnectorType.BOX,
            "github": ConnectorType.GITHUB
        }

        if connector_type not in type_map:
            return jsonify({
                "success": False,
                "error": f"Invalid connector type: {connector_type}"
            }), 400

        db = get_db()
        try:
            connector = db.query(Connector).filter(
                Connector.tenant_id == g.tenant_id,
                Connector.connector_type == type_map[connector_type]
            ).first()

            if not connector:
                return jsonify({
                    "success": False,
                    "error": f"{connector_type.title()} not connected"
                }), 400

            # Revoke tokens if possible (best effort)
            # ... token revocation logic ...

            # Soft delete connector
            connector.is_active = False
            connector.status = ConnectorStatus.DISCONNECTED
            connector.access_token = None
            connector.refresh_token = None

            db.commit()

            return jsonify({
                "success": True,
                "message": f"{connector_type.title()} disconnected"
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# STATUS
# ============================================================================

@integration_bp.route('/<connector_type>/status', methods=['GET'])
@require_auth
def connector_status(connector_type: str):
    """
    Get detailed status for a connector.
    """
    try:
        type_map = {
            "gmail": ConnectorType.GMAIL,
            "slack": ConnectorType.SLACK,
            "box": ConnectorType.BOX,
            "github": ConnectorType.GITHUB
        }

        if connector_type not in type_map:
            return jsonify({
                "success": False,
                "error": f"Invalid connector type: {connector_type}"
            }), 400

        db = get_db()
        try:
            connector = db.query(Connector).filter(
                Connector.tenant_id == g.tenant_id,
                Connector.connector_type == type_map[connector_type],
                Connector.is_active == True
            ).first()

            if not connector:
                return jsonify({
                    "success": True,
                    "status": "not_configured",
                    "connector": None
                })

            return jsonify({
                "success": True,
                "status": connector.status.value,
                "connector": connector.to_dict(include_tokens=False)
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# SETTINGS
# ============================================================================

@integration_bp.route('/<connector_type>/settings', methods=['PUT'])
@require_auth
def update_connector_settings(connector_type: str):
    """
    Update connector settings.

    Request body:
    {
        "settings": {
            "folder_ids": ["123", "456"],
            "max_file_size_mb": 100,
            ...
        }
    }
    """
    try:
        type_map = {
            "gmail": ConnectorType.GMAIL,
            "slack": ConnectorType.SLACK,
            "box": ConnectorType.BOX,
            "github": ConnectorType.GITHUB
        }

        if connector_type not in type_map:
            return jsonify({
                "success": False,
                "error": f"Invalid connector type: {connector_type}"
            }), 400

        data = request.get_json()
        if not data or 'settings' not in data:
            return jsonify({
                "success": False,
                "error": "Settings required"
            }), 400

        db = get_db()
        try:
            connector = db.query(Connector).filter(
                Connector.tenant_id == g.tenant_id,
                Connector.connector_type == type_map[connector_type],
                Connector.is_active == True
            ).first()

            if not connector:
                return jsonify({
                    "success": False,
                    "error": f"{connector_type.title()} not configured"
                }), 400

            # Merge settings
            current_settings = connector.settings or {}
            connector.settings = {**current_settings, **data['settings']}
            connector.updated_at = utc_now()

            db.commit()

            return jsonify({
                "success": True,
                "connector": connector.to_dict()
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
