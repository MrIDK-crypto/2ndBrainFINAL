"""
Gmail Connector
Connects to Gmail API to extract emails for knowledge capture.
"""

import base64
import re
from datetime import datetime
from typing import List, Dict, Optional, Any
from email.utils import parsedate_to_datetime

from .base_connector import BaseConnector, ConnectorConfig, ConnectorStatus, Document

# Note: These imports require google-auth and google-api-python-client
# pip install google-auth google-auth-oauthlib google-api-python-client

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False


class GmailConnector(BaseConnector):
    """
    Gmail connector for extracting emails.

    Extracts:
    - Email content (subject + body)
    - Sender/recipient information
    - Thread context
    - Attachments metadata
    - Labels/folders
    """

    CONNECTOR_TYPE = "gmail"
    REQUIRED_CREDENTIALS = ["access_token", "refresh_token"]
    OPTIONAL_SETTINGS = {
        "max_results": None,  # No limit - sync all emails
        "labels": ["INBOX", "SENT"],  # Labels to sync
        "include_attachments": False,
        "include_spam": False,
        "query": ""  # Gmail search query
    }

    # Gmail API scopes
    SCOPES = [
        'https://www.googleapis.com/auth/gmail.readonly'
    ]

    # OAuth client config - loaded from environment variables
    @classmethod
    def _get_client_config(cls) -> Dict:
        import os
        return {
            "web": {
                "client_id": os.getenv("GOOGLE_CLIENT_ID", "YOUR_CLIENT_ID.apps.googleusercontent.com"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", "YOUR_CLIENT_SECRET"),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:5003/api/connectors/gmail/callback")]
            }
        }

    # Legacy attribute for compatibility
    CLIENT_CONFIG = {
        "web": {
            "client_id": "LOADED_FROM_ENV",
            "client_secret": "LOADED_FROM_ENV",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:5003/api/connectors/gmail/callback"]
        }
    }

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.service = None

    async def connect(self) -> bool:
        """Connect to Gmail API"""
        if not GMAIL_AVAILABLE:
            self._set_error("Gmail dependencies not installed. Run: pip install google-auth google-auth-oauthlib google-api-python-client")
            return False

        try:
            self.status = ConnectorStatus.CONNECTING

            # Create credentials from stored tokens
            client_config = self._get_client_config()
            credentials = Credentials(
                token=self.config.credentials.get("access_token"),
                refresh_token=self.config.credentials.get("refresh_token"),
                token_uri=client_config["web"]["token_uri"],
                client_id=client_config["web"]["client_id"],
                client_secret=client_config["web"]["client_secret"],
                scopes=self.SCOPES
            )

            # Build Gmail service
            self.service = build('gmail', 'v1', credentials=credentials)

            # Test connection
            self.service.users().labels().list(userId='me').execute()

            self.status = ConnectorStatus.CONNECTED
            self._clear_error()
            return True

        except Exception as e:
            self._set_error(f"Failed to connect: {str(e)}")
            return False

    async def disconnect(self) -> bool:
        """Disconnect from Gmail API"""
        self.service = None
        self.status = ConnectorStatus.DISCONNECTED
        return True

    async def test_connection(self) -> bool:
        """Test Gmail connection"""
        if not self.service:
            return False

        try:
            self.service.users().labels().list(userId='me').execute()
            return True
        except Exception:
            return False

    @classmethod
    def get_auth_url(cls, redirect_uri: str, state: str) -> str:
        """Get Gmail OAuth authorization URL"""
        if not GMAIL_AVAILABLE:
            raise ImportError("Gmail dependencies not installed")

        flow = Flow.from_client_config(
            cls._get_client_config(),
            scopes=cls.SCOPES,
            redirect_uri=redirect_uri
        )

        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            state=state,
            prompt='consent'
        )

        return auth_url

    @classmethod
    async def exchange_code(cls, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange authorization code for tokens"""
        if not GMAIL_AVAILABLE:
            raise ImportError("Gmail dependencies not installed")

        flow = Flow.from_client_config(
            cls._get_client_config(),
            scopes=cls.SCOPES,
            redirect_uri=redirect_uri
        )

        flow.fetch_token(code=code)
        credentials = flow.credentials

        return {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "expiry": credentials.expiry.isoformat() if credentials.expiry else None
        }

    @classmethod
    def exchange_code_for_tokens(cls, code: str, redirect_uri: str):
        """
        Exchange authorization code for tokens (sync wrapper for callback).
        Returns (tokens_dict, error_string) tuple.
        """
        try:
            if not GMAIL_AVAILABLE:
                return None, "Gmail dependencies not installed. Run: pip install google-auth google-auth-oauthlib google-api-python-client"

            flow = Flow.from_client_config(
                cls._get_client_config(),
                scopes=cls.SCOPES,
                redirect_uri=redirect_uri
            )

            flow.fetch_token(code=code)
            credentials = flow.credentials

            tokens = {
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "expiry": credentials.expiry.isoformat() if credentials.expiry else None
            }

            return tokens, None

        except Exception as e:
            return None, str(e)

    async def sync(self, since: Optional[datetime] = None) -> List[Document]:
        """Sync emails from Gmail"""
        if not self.service:
            await self.connect()

        if self.status != ConnectorStatus.CONNECTED:
            return []

        self.status = ConnectorStatus.SYNCING
        documents = []

        try:
            # Build query
            query_parts = []

            if since:
                date_str = since.strftime("%Y/%m/%d")
                query_parts.append(f"after:{date_str}")

            if self.config.settings.get("query"):
                query_parts.append(self.config.settings["query"])

            if not self.config.settings.get("include_spam", False):
                query_parts.append("-in:spam")

            query = " ".join(query_parts) if query_parts else None

            # Get labels to sync
            labels = self.config.settings.get("labels", ["INBOX", "SENT"])

            for label in labels:
                # Get max_results setting (None = unlimited)
                max_results = self.config.settings.get("max_results")
                page_token = None
                total_fetched = 0

                while True:
                    # List messages with pagination
                    list_params = {
                        'userId': 'me',
                        'labelIds': [label],
                        'maxResults': 500  # Gmail API max per page
                    }

                    if query:
                        list_params['q'] = query

                    if page_token:
                        list_params['pageToken'] = page_token

                    results = self.service.users().messages().list(**list_params).execute()
                    messages = results.get('messages', [])

                    # Fetch each message
                    for msg_info in messages:
                        # Check if we've hit the user-defined limit
                        if max_results is not None and total_fetched >= max_results:
                            break

                        msg = self.service.users().messages().get(
                            userId='me',
                            id=msg_info['id'],
                            format='full'
                        ).execute()

                        doc = self._message_to_document(msg, label)
                        if doc:
                            documents.append(doc)
                            total_fetched += 1

                    # Check if we should continue pagination
                    page_token = results.get('nextPageToken')

                    # Stop if no more pages or hit user limit
                    if not page_token or (max_results is not None and total_fetched >= max_results):
                        break

            # Update stats
            self.sync_stats = {
                "documents_synced": len(documents),
                "labels_synced": labels,
                "sync_time": datetime.now().isoformat()
            }

            self.config.last_sync = datetime.now()
            self.status = ConnectorStatus.CONNECTED

        except Exception as e:
            self._set_error(f"Sync failed: {str(e)}")

        return documents

    async def get_document(self, doc_id: str) -> Optional[Document]:
        """Get a specific email by message ID"""
        if not self.service:
            await self.connect()

        try:
            # Extract Gmail message ID from doc_id
            msg_id = doc_id.replace("gmail_", "")

            msg = self.service.users().messages().get(
                userId='me',
                id=msg_id,
                format='full'
            ).execute()

            return self._message_to_document(msg)

        except Exception as e:
            self._set_error(f"Failed to get document: {str(e)}")
            return None

    def _message_to_document(self, message: Dict, label: str = None) -> Optional[Document]:
        """Convert Gmail message to Document"""
        try:
            headers = {h['name'].lower(): h['value'] for h in message['payload']['headers']}

            # Extract basic info
            subject = headers.get('subject', '(No Subject)')
            sender = headers.get('from', 'Unknown')
            recipient = headers.get('to', 'Unknown')
            date_str = headers.get('date', '')

            # Parse date
            timestamp = None
            if date_str:
                try:
                    timestamp = parsedate_to_datetime(date_str)
                except Exception:
                    pass

            # Extract body
            body = self._extract_body(message['payload'])

            # Clean up body
            body = self._clean_email_body(body)

            # Create content
            content = f"""Subject: {subject}
From: {sender}
To: {recipient}
Date: {date_str}

{body}"""

            # Extract sender name
            author = self._extract_name_from_email(sender)

            return Document(
                doc_id=f"gmail_{message['id']}",
                source="gmail",
                content=content,
                title=subject,
                metadata={
                    "message_id": message['id'],
                    "thread_id": message.get('threadId'),
                    "label": label,
                    "from": sender,
                    "to": recipient,
                    "snippet": message.get('snippet', '')[:200]
                },
                timestamp=timestamp,
                author=author,
                doc_type="email"
            )

        except Exception as e:
            print(f"Error converting message: {e}")
            return None

    def _extract_body(self, payload: Dict) -> str:
        """Extract email body from payload"""
        body = ""

        if 'body' in payload and payload['body'].get('data'):
            body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')

        elif 'parts' in payload:
            for part in payload['parts']:
                mime_type = part.get('mimeType', '')

                if mime_type == 'text/plain':
                    if part['body'].get('data'):
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                        break

                elif mime_type == 'text/html' and not body:
                    if part['body'].get('data'):
                        html = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                        body = self._html_to_text(html)

                elif mime_type.startswith('multipart/'):
                    body = self._extract_body(part)
                    if body:
                        break

        return body

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text"""
        # Remove script and style tags
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # Replace common tags
        html = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
        html = re.sub(r'<p[^>]*>', '\n', html, flags=re.IGNORECASE)
        html = re.sub(r'</p>', '\n', html, flags=re.IGNORECASE)
        html = re.sub(r'<div[^>]*>', '\n', html, flags=re.IGNORECASE)

        # Remove remaining tags
        html = re.sub(r'<[^>]+>', '', html)

        # Decode entities
        html = html.replace('&nbsp;', ' ')
        html = html.replace('&amp;', '&')
        html = html.replace('&lt;', '<')
        html = html.replace('&gt;', '>')
        html = html.replace('&quot;', '"')

        # Clean up whitespace
        html = re.sub(r'\n\s*\n', '\n\n', html)
        html = html.strip()

        return html

    def _clean_email_body(self, body: str) -> str:
        """Clean up email body"""
        # Remove quoted content (previous emails in thread)
        lines = body.split('\n')
        cleaned_lines = []

        for line in lines:
            # Skip quoted lines
            if line.strip().startswith('>'):
                continue
            # Skip "On X wrote:" lines
            if re.match(r'^On .+ wrote:$', line.strip()):
                break
            # Skip forwarded message headers
            if '---------- Forwarded message ----------' in line:
                break
            cleaned_lines.append(line)

        return '\n'.join(cleaned_lines).strip()

    def _extract_name_from_email(self, email_header: str) -> str:
        """Extract name from email header like 'John Smith <john@example.com>'"""
        match = re.match(r'^"?([^"<]+)"?\s*<', email_header)
        if match:
            return match.group(1).strip()
        return email_header.split('@')[0] if '@' in email_header else email_header

    # ========================================================================
    # PUSH NOTIFICATIONS (Optional - Requires Google Cloud Pub/Sub)
    # ========================================================================

    async def setup_push_notifications(self, topic_name: str) -> Optional[str]:
        """
        Set up Gmail push notifications via Google Cloud Pub/Sub.

        This enables real-time sync instead of polling.

        Args:
            topic_name: Full topic name in format:
                       "projects/YOUR_PROJECT_ID/topics/gmail-notifications"

        Returns:
            history_id if successful, None if failed

        Note:
            - Requires Google Cloud Pub/Sub topic setup
            - Free tier: 10GB/month
            - Watch expires after 7 days (need to renew)
            - See: https://developers.google.com/gmail/api/guides/push

        Setup:
            1. Create GCP project
            2. Enable Gmail API and Pub/Sub API
            3. Create Pub/Sub topic: gmail-notifications
            4. Grant Gmail publish permission:
               gcloud pubsub topics add-iam-policy-binding gmail-notifications \
                   --member=serviceAccount:gmail-api-push@system.gserviceaccount.com \
                   --role=roles/pubsub.publisher
            5. Create subscription pointing to your webhook endpoint
        """
        if not self.service:
            await self.connect()

        try:
            from utils.logger import log_info, log_error

            # Create watch request
            request_body = {
                'labelIds': ['INBOX', 'SENT'],  # Watch these labels
                'topicName': topic_name
            }

            log_info("GmailConnector", "Setting up push notifications", topic=topic_name)

            response = self.service.users().watch(
                userId='me',
                body=request_body
            ).execute()

            history_id = response.get('historyId')
            expiration = response.get('expiration')  # Unix timestamp in milliseconds

            log_info("GmailConnector", "Push notifications enabled",
                    history_id=history_id, expiration=expiration)

            return history_id

        except HttpError as e:
            from utils.logger import log_error
            log_error("GmailConnector", "Failed to set up push notifications", error=e)
            return None
        except Exception as e:
            from utils.logger import log_error
            log_error("GmailConnector", "Push setup error", error=e)
            return None

    async def handle_push_notification(self, history_id: str) -> List[Document]:
        """
        Handle Gmail push notification by fetching new emails since history_id.

        This is called when Pub/Sub delivers a notification to your webhook.

        Args:
            history_id: Starting history ID from notification

        Returns:
            List of new documents

        Example webhook handler:
            @app.route('/api/gmail/webhook', methods=['POST'])
            def gmail_webhook():
                data = request.get_json()
                message = base64.b64decode(data['message']['data'])
                notification = json.loads(message)
                history_id = notification['historyId']

                # Process new emails
                connector = GmailConnector(config)
                docs = await connector.handle_push_notification(history_id)

                return jsonify({'status': 'ok', 'processed': len(docs)})
        """
        if not self.service:
            await self.connect()

        try:
            from utils.logger import log_info

            log_info("GmailConnector", "Processing push notification", history_id=history_id)

            # Fetch history changes since history_id
            response = self.service.users().history().list(
                userId='me',
                startHistoryId=history_id,
                historyTypes=['messageAdded'],  # Only new messages
                maxResults=500
            ).execute()

            documents = []
            history = response.get('history', [])

            log_info("GmailConnector", "History entries retrieved", count=len(history))

            # Extract message IDs from history
            message_ids = []
            for record in history:
                for msg in record.get('messagesAdded', []):
                    message_ids.append(msg['message']['id'])

            # Fetch and process each new message
            for msg_id in message_ids:
                try:
                    message = self.service.users().messages().get(
                        userId='me',
                        id=msg_id,
                        format='full'
                    ).execute()

                    doc = await self._message_to_document(message)
                    if doc:
                        documents.append(doc)

                except Exception as msg_err:
                    from utils.logger import log_error
                    log_error("GmailConnector", "Failed to process message", error=msg_err, msg_id=msg_id)

            log_info("GmailConnector", "Push notification processed", new_emails=len(documents))

            return documents

        except HttpError as e:
            from utils.logger import log_error
            log_error("GmailConnector", "Push notification handling failed", error=e)
            return []
        except Exception as e:
            from utils.logger import log_error
            log_error("GmailConnector", "Push handling error", error=e)
            return []

    async def stop_push_notifications(self) -> bool:
        """
        Stop Gmail push notifications (stop watch).

        Returns:
            True if successful, False otherwise
        """
        if not self.service:
            await self.connect()

        try:
            from utils.logger import log_info

            self.service.users().stop(userId='me').execute()

            log_info("GmailConnector", "Push notifications stopped")

            return True

        except Exception as e:
            from utils.logger import log_error
            log_error("GmailConnector", "Failed to stop push notifications", error=e)
            return False
