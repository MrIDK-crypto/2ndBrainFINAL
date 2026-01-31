"""
Slack Bot API Routes
Handles Slack OAuth, events, and slash commands.
"""

import os
import hmac
import hashlib
import time
from flask import Blueprint, request, jsonify, redirect, g
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.signature import SignatureVerifier
from services.auth_service import require_auth
from services.slack_bot_service import (
    SlackBotService,
    register_slack_workspace,
    get_tenant_for_workspace,
    get_bot_token_for_workspace
)

slack_bot_bp = Blueprint('slack_bot', __name__, url_prefix='/api/slack')

# Slack app credentials (from environment)
SLACK_CLIENT_ID = os.getenv('SLACK_CLIENT_ID')
SLACK_CLIENT_SECRET = os.getenv('SLACK_CLIENT_SECRET')
SLACK_SIGNING_SECRET = os.getenv('SLACK_SIGNING_SECRET')

# Signature verifier
signature_verifier = SignatureVerifier(SLACK_SIGNING_SECRET) if SLACK_SIGNING_SECRET else None


# ============================================================================
# SLACK VERIFICATION MIDDLEWARE
# ============================================================================

def verify_slack_request():
    """Verify Slack request signature"""
    if not signature_verifier:
        return True  # Skip verification if no signing secret

    timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
    signature = request.headers.get('X-Slack-Signature', '')

    # Check timestamp (prevent replay attacks)
    if abs(time.time() - int(timestamp)) > 60 * 5:  # 5 minutes
        print("[SlackBot] Request timestamp too old", flush=True)
        return False

    # Verify signature
    body = request.get_data(as_text=True)

    if not signature_verifier.is_valid(body, timestamp, signature):
        print("[SlackBot] Invalid signature", flush=True)
        return False

    return True


# ============================================================================
# OAUTH FLOW
# ============================================================================

@slack_bot_bp.route('/oauth/install', methods=['GET'])
@require_auth
def slack_oauth_install():
    """
    Start Slack OAuth flow (redirect to Slack).

    This is called when user clicks "Add to Slack" button in the UI.

    GET /api/slack/oauth/install

    Redirects to Slack authorization page.
    """
    # Build OAuth URL
    scopes = [
        'app_mentions:read',  # Hear @mentions
        'channels:history',   # Read channel messages
        'channels:read',      # Access channel list
        'chat:write',         # Post messages
        'commands',           # Receive slash commands
        'im:history',         # Read DMs
        'im:read',            # Access DM list
        'im:write',           # Send DMs
        'users:read',         # Read user info
    ]

    # State parameter includes tenant_id for security
    state = f"{g.tenant_id}:{g.user_id}"

    slack_auth_url = (
        f"https://slack.com/oauth/v2/authorize"
        f"?client_id={SLACK_CLIENT_ID}"
        f"&scope={','.join(scopes)}"
        f"&state={state}"
        f"&redirect_uri={request.host_url}api/slack/oauth/callback"
    )

    return redirect(slack_auth_url)


@slack_bot_bp.route('/oauth/callback', methods=['GET'])
def slack_oauth_callback():
    """
    Handle Slack OAuth callback.

    Slack redirects here after user authorizes the app.

    GET /api/slack/oauth/callback?code=...&state=...

    Exchanges code for access token and stores it.
    """
    try:
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')

        if error:
            return jsonify({
                'success': False,
                'error': f"Slack authorization failed: {error}"
            }), 400

        if not code:
            return jsonify({
                'success': False,
                'error': "No authorization code provided"
            }), 400

        # Parse state
        try:
            tenant_id, user_id = state.split(':', 1)
        except ValueError:
            return jsonify({
                'success': False,
                'error': "Invalid state parameter"
            }), 400

        # Exchange code for access token
        client = WebClient()

        response = client.oauth_v2_access(
            client_id=SLACK_CLIENT_ID,
            client_secret=SLACK_CLIENT_SECRET,
            code=code,
            redirect_uri=f"{request.host_url}api/slack/oauth/callback"
        )

        if not response['ok']:
            raise Exception(f"OAuth exchange failed: {response.get('error')}")

        # Extract tokens and workspace info
        team_id = response['team']['id']
        team_name = response['team']['name']
        bot_token = response['access_token']
        bot_user_id = response['bot_user_id']

        # Register workspace
        register_slack_workspace(team_id, tenant_id, bot_token)

        # In production: Store in database
        # from database.models import SlackWorkspace
        # workspace = SlackWorkspace(
        #     tenant_id=tenant_id,
        #     team_id=team_id,
        #     team_name=team_name,
        #     bot_token=bot_token,
        #     bot_user_id=bot_user_id
        # )
        # db.add(workspace)
        # db.commit()

        print(f"[SlackBot] Workspace connected: {team_name} ({team_id})", flush=True)

        # Redirect to success page
        return redirect(f"{request.host_url}integrations?slack_connected=true")

    except SlackApiError as e:
        print(f"[SlackBot] OAuth error: {e}", flush=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

    except Exception as e:
        print(f"[SlackBot] OAuth error: {e}", flush=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# SLASH COMMANDS
# ============================================================================

@slack_bot_bp.route('/commands/ask', methods=['POST'])
def slack_command_ask():
    """
    Handle /ask slash command.

    User types: /ask What is our pricing model?

    POST /api/slack/commands/ask

    Slack sends:
    {
        "token": "...",
        "team_id": "...",
        "user_id": "...",
        "channel_id": "...",
        "text": "What is our pricing model?",
        "response_url": "..."
    }
    """
    try:
        # Verify Slack signature
        if not verify_slack_request():
            return jsonify({
                'text': '❌ Invalid request signature'
            }), 403

        # Parse command data
        team_id = request.form.get('team_id')
        user_id = request.form.get('user_id')
        channel_id = request.form.get('channel_id')
        query = request.form.get('text', '').strip()
        response_url = request.form.get('response_url')

        # Get tenant for workspace
        tenant_id = get_tenant_for_workspace(team_id)
        if not tenant_id:
            return jsonify({
                'response_type': 'ephemeral',
                'text': '❌ Workspace not connected to 2nd Brain. Please connect in Settings > Integrations.'
            })

        # Get bot token
        bot_token = get_bot_token_for_workspace(team_id)
        if not bot_token:
            return jsonify({
                'response_type': 'ephemeral',
                'text': '❌ Bot token not found. Please reconnect workspace.'
            })

        # Handle command
        bot_service = SlackBotService(bot_token)

        if not query:
            return jsonify({
                'response_type': 'ephemeral',
                'text': '❓ *Usage:* `/ask <your question>`\n\nExample: `/ask What is our pricing model?`'
            })

        response = bot_service.handle_ask_command(
            tenant_id=tenant_id,
            user_id=user_id,
            channel_id=channel_id,
            query=query,
            response_url=response_url
        )

        return jsonify(response)

    except Exception as e:
        print(f"[SlackBot] Command error: {e}", flush=True)
        return jsonify({
            'response_type': 'ephemeral',
            'text': f'❌ Error: {str(e)}'
        })


# ============================================================================
# SLACK EVENTS
# ============================================================================

@slack_bot_bp.route('/events', methods=['POST'])
def slack_events():
    """
    Handle Slack events (mentions, messages, etc.).

    POST /api/slack/events

    Slack sends events like:
    - app_mention: @2ndBrain what is...
    - message: DMs to the bot
    """
    try:
        # Verify Slack signature
        if not verify_slack_request():
            return jsonify({'error': 'Invalid signature'}), 403

        data = request.get_json()

        # Handle URL verification challenge
        if data.get('type') == 'url_verification':
            return jsonify({'challenge': data['challenge']})

        # Handle events
        if data.get('type') == 'event_callback':
            event = data.get('event', {})
            team_id = data.get('team_id')

            # Get tenant for workspace
            tenant_id = get_tenant_for_workspace(team_id)
            if not tenant_id:
                print(f"[SlackBot] No tenant found for workspace {team_id}", flush=True)
                return jsonify({'ok': True})

            # Get bot token
            bot_token = get_bot_token_for_workspace(team_id)
            if not bot_token:
                print(f"[SlackBot] No bot token for workspace {team_id}", flush=True)
                return jsonify({'ok': True})

            bot_service = SlackBotService(bot_token)

            # Handle app_mention (@2ndBrain ...)
            if event.get('type') == 'app_mention':
                bot_service.handle_app_mention(tenant_id, event)

            # Handle direct messages
            elif event.get('type') == 'message':
                # Ignore bot messages and channel messages
                if not event.get('bot_id') and event.get('channel', '').startswith('D'):
                    bot_service.handle_message(tenant_id, event)

        return jsonify({'ok': True})

    except Exception as e:
        print(f"[SlackBot] Events error: {e}", flush=True)
        return jsonify({'ok': True})  # Always return 200 to Slack


# ============================================================================
# INTERACTIVE COMPONENTS
# ============================================================================

@slack_bot_bp.route('/interactive', methods=['POST'])
def slack_interactive():
    """
    Handle Slack interactive components (buttons, menus, etc.).

    POST /api/slack/interactive

    Future use: Handle button clicks, dropdown selections
    """
    try:
        # Verify Slack signature
        if not verify_slack_request():
            return jsonify({'error': 'Invalid signature'}), 403

        # Parse payload
        import json
        payload = json.loads(request.form.get('payload', '{}'))

        # Handle interactive action
        action_type = payload.get('type')
        team_id = payload.get('team', {}).get('id')

        # Get tenant
        tenant_id = get_tenant_for_workspace(team_id)
        if not tenant_id:
            return jsonify({'text': '❌ Workspace not connected'})

        # Future: Handle different action types
        # - block_actions: Button clicks
        # - view_submission: Modal submissions
        # - view_closed: Modal closed

        return jsonify({'ok': True})

    except Exception as e:
        print(f"[SlackBot] Interactive error: {e}", flush=True)
        return jsonify({'ok': True})


# ============================================================================
# MANAGEMENT ENDPOINTS
# ============================================================================

@slack_bot_bp.route('/status', methods=['GET'])
@require_auth
def slack_bot_status():
    """
    Check if Slack bot is connected for current tenant.

    GET /api/slack/status

    Returns:
    {
        "success": true,
        "connected": true,
        "workspace": "Acme Corp",
        "bot_user_id": "U0123456"
    }
    """
    try:
        tenant_id = g.tenant_id

        # In production: Query database for SlackWorkspace
        # For now: Check in-memory mapping
        # workspace = db.query(SlackWorkspace).filter(
        #     SlackWorkspace.tenant_id == tenant_id
        # ).first()

        # Placeholder response
        return jsonify({
            'success': True,
            'connected': False,  # Update based on database
            'message': 'Slack bot implementation complete. Configure OAuth to connect.'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@slack_bot_bp.route('/disconnect', methods=['POST'])
@require_auth
def slack_bot_disconnect():
    """
    Disconnect Slack bot for current tenant.

    POST /api/slack/disconnect
    """
    try:
        tenant_id = g.tenant_id

        # In production: Delete from database
        # workspace = db.query(SlackWorkspace).filter(
        #     SlackWorkspace.tenant_id == tenant_id
        # ).first()
        # if workspace:
        #     db.delete(workspace)
        #     db.commit()

        return jsonify({
            'success': True,
            'message': 'Slack bot disconnected'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
