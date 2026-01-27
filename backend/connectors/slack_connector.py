"""
Slack Connector
Connects to Slack API to extract messages for knowledge capture.
"""

from datetime import datetime
from typing import List, Dict, Optional, Any

from .base_connector import BaseConnector, ConnectorConfig, ConnectorStatus, Document

# Note: Requires slack_sdk
# pip install slack_sdk

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False


class SlackConnector(BaseConnector):
    """
    Slack connector for extracting messages and conversations.

    Extracts:
    - Channel messages
    - Direct messages (if permitted)
    - Thread replies
    - File/link shares
    - User mentions and relationships
    """

    CONNECTOR_TYPE = "slack"
    REQUIRED_CREDENTIALS = ["access_token"]  # OAuth v2 provides access_token
    OPTIONAL_SETTINGS = {
        "channels": [],  # Channel IDs to sync (empty = all accessible)
        "include_dms": True,  # Include DMs by default
        "include_threads": True,
        "max_messages_per_channel": 1000,
        "oldest_days": 365  # How far back to sync
    }

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.client = None
        self.user_cache: Dict[str, str] = {}  # user_id -> display name

    async def connect(self) -> bool:
        """Connect to Slack API"""
        if not SLACK_AVAILABLE:
            self._set_error("Slack SDK not installed. Run: pip install slack_sdk")
            return False

        try:
            self.status = ConnectorStatus.CONNECTING

            # Support both access_token (OAuth v2) and bot_token (legacy)
            token = self.config.credentials.get("access_token") or self.config.credentials.get("bot_token")
            self.client = WebClient(token=token)

            # Test connection
            response = self.client.auth_test()

            if response["ok"]:
                self.sync_stats["team"] = response.get("team")
                self.sync_stats["user"] = response.get("user")
                self.status = ConnectorStatus.CONNECTED
                self._clear_error()
                return True
            else:
                self._set_error("Auth test failed")
                return False

        except SlackApiError as e:
            self._set_error(f"Slack API error: {e.response['error']}")
            return False
        except Exception as e:
            self._set_error(f"Failed to connect: {str(e)}")
            return False

    async def disconnect(self) -> bool:
        """Disconnect from Slack API"""
        self.client = None
        self.status = ConnectorStatus.DISCONNECTED
        return True

    async def test_connection(self) -> bool:
        """Test Slack connection"""
        if not self.client:
            return False

        try:
            response = self.client.auth_test()
            return response["ok"]
        except Exception:
            return False

    async def sync(self, since: Optional[datetime] = None) -> List[Document]:
        """Sync messages from Slack"""
        if not self.client:
            await self.connect()

        if self.status != ConnectorStatus.CONNECTED:
            return []

        self.status = ConnectorStatus.SYNCING
        documents = []

        try:
            # Get channels to sync
            channels = await self._get_channels()

            print(f"[Slack] Starting sync for {len(channels)} channels")

            # Calculate oldest timestamp
            oldest = None
            if since:
                oldest = since.timestamp()
                print(f"[Slack] Syncing since: {since}")
            elif self.config.settings.get("oldest_days"):
                days = self.config.settings["oldest_days"]
                oldest = (datetime.now().timestamp()) - (days * 24 * 60 * 60)
                print(f"[Slack] Syncing last {days} days")

            for channel in channels:
                channel_docs = await self._sync_channel(channel, oldest)
                documents.extend(channel_docs)

            # Update stats
            self.sync_stats["documents_synced"] = len(documents)
            self.sync_stats["channels_synced"] = len(channels)
            self.sync_stats["sync_time"] = datetime.now().isoformat()

            self.config.last_sync = datetime.now()
            self.status = ConnectorStatus.CONNECTED

            print(f"[Slack] Sync complete: {len(documents)} total documents")

        except Exception as e:
            print(f"[Slack] Sync failed: {str(e)}")
            import traceback
            traceback.print_exc()
            self._set_error(f"Sync failed: {str(e)}")

        return documents

    async def get_document(self, doc_id: str) -> Optional[Document]:
        """Get a specific message"""
        # Slack doesn't support fetching individual messages easily
        # Would need to know channel and timestamp
        return None

    async def _get_channels(self) -> List[Dict]:
        """Get list of channels to sync"""
        channels = []

        # If specific channels configured, use those
        configured_channels = self.config.settings.get("channels", [])

        try:
            # Get public channels
            response = self.client.conversations_list(
                types="public_channel,private_channel",
                exclude_archived=True
            )

            print(f"[Slack] Found {len(response.get('channels', []))} total channels")

            for channel in response.get("channels", []):
                print(f"[Slack] Channel: {channel['name']} (is_member={channel.get('is_member')})")
                if not configured_channels or channel["id"] in configured_channels:
                    if channel.get("is_member"):
                        channels.append({
                            "id": channel["id"],
                            "name": channel["name"],
                            "type": "channel"
                        })
                        print(f"[Slack] ✓ Added channel: {channel['name']}")

            print(f"[Slack] Total channels to sync: {len(channels)}")

            # Get DMs if enabled
            if self.config.settings.get("include_dms"):
                dm_response = self.client.conversations_list(types="im")
                for dm in dm_response.get("channels", []):
                    channels.append({
                        "id": dm["id"],
                        "name": f"DM with {dm.get('user', 'Unknown')}",
                        "type": "dm"
                    })

        except SlackApiError as e:
            print(f"[Slack] Error getting channels: {e.response['error']}")
            self._set_error(f"Failed to get channels: {e.response['error']}")

        return channels

    async def _sync_channel(self, channel: Dict, oldest: Optional[float]) -> List[Document]:
        """Sync messages from a single channel"""
        documents = []
        max_messages = self.config.settings.get("max_messages_per_channel", 1000)

        print(f"[Slack] Syncing channel: {channel['name']}")

        try:
            cursor = None

            while len(documents) < max_messages:
                # Get message history
                kwargs = {
                    "channel": channel["id"],
                    "limit": min(200, max_messages - len(documents))
                }

                if oldest:
                    kwargs["oldest"] = str(oldest)

                if cursor:
                    kwargs["cursor"] = cursor

                response = self.client.conversations_history(**kwargs)
                messages = response.get("messages", [])

                print(f"[Slack] Fetched {len(messages)} messages from {channel['name']}")

                for message in messages:
                    doc = await self._message_to_document(message, channel)
                    if doc:
                        documents.append(doc)
                    else:
                        print(f"[Slack] Skipped message (subtype={message.get('subtype')})")

                    # Get thread replies if enabled
                    if (self.config.settings.get("include_threads", True) and
                        message.get("reply_count", 0) > 0):
                        thread_docs = await self._sync_thread(channel, message["ts"])
                        documents.extend(thread_docs)

                # Check for more pages
                if response.get("has_more") and response.get("response_metadata", {}).get("next_cursor"):
                    cursor = response["response_metadata"]["next_cursor"]
                else:
                    break

            print(f"[Slack] Channel {channel['name']}: {len(documents)} documents created")

        except SlackApiError as e:
            print(f"[Slack] Error syncing channel {channel['name']}: {e.response['error']}")

        return documents

    async def _sync_thread(self, channel: Dict, thread_ts: str) -> List[Document]:
        """Sync replies in a thread"""
        documents = []

        try:
            response = self.client.conversations_replies(
                channel=channel["id"],
                ts=thread_ts
            )

            # Skip first message (it's the parent)
            for message in response.get("messages", [])[1:]:
                doc = await self._message_to_document(message, channel, is_reply=True)
                if doc:
                    documents.append(doc)

        except SlackApiError:
            pass

        return documents

    async def _message_to_document(
        self,
        message: Dict,
        channel: Dict,
        is_reply: bool = False
    ) -> Optional[Document]:
        """Convert Slack message to Document"""
        try:
            # Skip bot messages and system messages
            if message.get("subtype") in ["bot_message", "channel_join", "channel_leave"]:
                return None

            # Get user name
            user_id = message.get("user", "Unknown")
            author = await self._get_user_name(user_id)

            # Parse timestamp
            ts = float(message.get("ts", 0))
            timestamp = datetime.fromtimestamp(ts) if ts else None

            # Get message text
            text = message.get("text", "")

            # Replace user mentions with names
            text = await self._replace_user_mentions(text)

            # Create content
            content = f"""Slack Message in #{channel['name']}
From: {author}
Time: {timestamp.isoformat() if timestamp else 'Unknown'}
{"(Thread Reply)" if is_reply else ""}

{text}"""

            # Extract attachments info
            attachments = []
            for att in message.get("attachments", []):
                attachments.append({
                    "title": att.get("title"),
                    "text": att.get("text"),
                    "url": att.get("title_link")
                })

            # Extract file info
            files = []
            for file in message.get("files", []):
                files.append({
                    "name": file.get("name"),
                    "type": file.get("filetype"),
                    "url": file.get("url_private")
                })

            return Document(
                doc_id=f"slack_{channel['id']}_{message['ts']}",
                source="slack",
                content=content,
                title=f"Slack: {text[:50]}..." if len(text) > 50 else f"Slack: {text}",
                metadata={
                    "channel_id": channel["id"],
                    "channel_name": channel["name"],
                    "channel_type": channel["type"],
                    "message_ts": message.get("ts"),
                    "thread_ts": message.get("thread_ts"),
                    "is_reply": is_reply,
                    "reactions": message.get("reactions", []),
                    "attachments": attachments,
                    "files": files
                },
                timestamp=timestamp,
                author=author,
                doc_type="message"
            )

        except Exception as e:
            print(f"Error converting message: {e}")
            return None

    async def _get_user_name(self, user_id: str) -> str:
        """Get display name for a user ID"""
        if user_id in self.user_cache:
            return self.user_cache[user_id]

        try:
            response = self.client.users_info(user=user_id)
            if response["ok"]:
                user = response["user"]
                name = user.get("real_name") or user.get("name") or user_id
                self.user_cache[user_id] = name
                return name
        except SlackApiError:
            pass

        return user_id

    async def _replace_user_mentions(self, text: str) -> str:
        """Replace <@USER_ID> mentions with display names"""
        import re

        pattern = r'<@([A-Z0-9]+)>'

        async def replace(match):
            user_id = match.group(1)
            name = await self._get_user_name(user_id)
            return f"@{name}"

        # Synchronous version for simplicity
        matches = re.findall(pattern, text)
        for user_id in matches:
            name = await self._get_user_name(user_id)
            text = text.replace(f"<@{user_id}>", f"@{name}")

        return text
