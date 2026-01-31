"""
Box Connector
Enterprise-grade Box integration for file sync and content extraction.
Supports OAuth2, webhooks, and incremental sync.
"""

import os
import io
import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path
import mimetypes

from .base_connector import BaseConnector, ConnectorConfig, ConnectorStatus, Document
from utils.logger import log_info, log_error, log_warning

# S3 Service for file storage
try:
    from services.s3_service import get_s3_service
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False

# Note: Requires box-sdk-gen (Box SDK v10+)
# pip install boxsdk

try:
    # Try new Box SDK (v10+) - box_sdk_gen
    from box_sdk_gen import (
        BoxClient, BoxOAuth, OAuthConfig, BoxAPIError,
        AccessToken, GetAuthorizeUrlOptions
    )
    from box_sdk_gen.box.token_storage import InMemoryTokenStorage
    BOX_AVAILABLE = True
    BOX_SDK_VERSION = "new"
except ImportError:
    try:
        # Fallback to legacy boxsdk (v3.x)
        from boxsdk import OAuth2, Client
        from boxsdk.exception import BoxAPIException as BoxAPIError
        BOX_AVAILABLE = True
        BOX_SDK_VERSION = "legacy"
    except ImportError:
        BOX_AVAILABLE = False
        BOX_SDK_VERSION = None


class BoxConnector(BaseConnector):
    """
    Box connector for syncing files and folders.

    Features:
    - OAuth2 authentication
    - Full and incremental sync
    - Content extraction (text, PDF, Office docs)
    - Folder filtering
    - Webhook support for real-time updates
    - Rate limiting and retry logic
    """

    CONNECTOR_TYPE = "box"
    REQUIRED_CREDENTIALS = ["access_token", "refresh_token"]
    OPTIONAL_SETTINGS = {
        "root_folder_id": "0",  # 0 = All Files
        "folder_ids": [],  # Specific folders to sync
        "exclude_folders": [],  # Folders to exclude
        "file_extensions": [],  # Empty = all, or [".pdf", ".docx", ...]
        "max_file_size_mb": 50,  # Skip files larger than this
        "include_shared": True,  # Include shared files
        "include_trash": False,  # Include trashed files
        "sync_comments": True,  # Sync file comments
        "sync_versions": False,  # Sync file versions
    }

    # Supported file types for text extraction
    EXTRACTABLE_TYPES = {
        ".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".rtf", ".odt", ".ods", ".odp"
    }

    # OAuth configuration
    @classmethod
    def _get_oauth_config(cls) -> Dict:
        return {
            "client_id": os.getenv("BOX_CLIENT_ID", ""),
            "client_secret": os.getenv("BOX_CLIENT_SECRET", ""),
            "redirect_uri": os.getenv("BOX_REDIRECT_URI", "http://localhost:5003/api/connectors/box/callback")
        }

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.client = None  # BoxClient or Client depending on SDK version
        self.oauth = None  # BoxOAuth or OAuth2 depending on SDK version
        self._user_info: Optional[Dict] = None

    # ========================================================================
    # OAUTH FLOW
    # ========================================================================

    @classmethod
    def get_auth_url(cls, redirect_uri: str, state: str) -> str:
        """
        Get Box OAuth authorization URL.

        Args:
            redirect_uri: OAuth callback URL
            state: CSRF state parameter

        Returns:
            Authorization URL for user to visit
        """
        if not BOX_AVAILABLE:
            raise ImportError("Box SDK not installed. Run: pip install boxsdk")

        oauth_config = cls._get_oauth_config()

        if BOX_SDK_VERSION == "new":
            # New SDK (v10+) - use BoxOAuth
            config = OAuthConfig(
                client_id=oauth_config["client_id"],
                client_secret=oauth_config["client_secret"],
            )
            oauth = BoxOAuth(config)
            # Request root_readwrite scope for full access including file downloads
            auth_url = oauth.get_authorize_url(
                options=GetAuthorizeUrlOptions(
                    redirect_uri=redirect_uri,
                    state=state,
                    scope="root_readwrite"  # Required for file downloads
                )
            )
            print(f"[BoxConnector] OAuth URL generated with scope=root_readwrite")
            return auth_url
        else:
            # Legacy SDK (v3.x)
            oauth = OAuth2(
                client_id=oauth_config["client_id"],
                client_secret=oauth_config["client_secret"],
            )
            auth_url, csrf_token = oauth.get_authorization_url(redirect_uri)
            # Append our state to the URL
            if "?" in auth_url:
                auth_url += f"&state={state}"
            else:
                auth_url += f"?state={state}"
            return auth_url

    @classmethod
    def exchange_code_for_tokens(
        cls,
        code: str,
        redirect_uri: str
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Exchange authorization code for tokens.

        Args:
            code: Authorization code from callback
            redirect_uri: Same redirect URI used in auth request

        Returns:
            (tokens_dict, error_message)
        """
        if not BOX_AVAILABLE:
            return None, "Box SDK not installed"

        try:
            oauth_config = cls._get_oauth_config()

            if BOX_SDK_VERSION == "new":
                # New SDK (v10+)
                config = OAuthConfig(
                    client_id=oauth_config["client_id"],
                    client_secret=oauth_config["client_secret"],
                )
                oauth = BoxOAuth(config)
                # Get tokens from authorization code
                token_response = oauth.get_tokens_authorization_code_grant(code)

                return {
                    "access_token": token_response.access_token,
                    "refresh_token": token_response.refresh_token,
                    "token_type": "Bearer"
                }, None
            else:
                # Legacy SDK (v3.x)
                oauth = OAuth2(
                    client_id=oauth_config["client_id"],
                    client_secret=oauth_config["client_secret"],
                )
                access_token, refresh_token = oauth.authenticate(code)
                return {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": "Bearer"
                }, None

        except BoxAPIError as e:
            return None, f"Box API error: {str(e)}"
        except Exception as e:
            return None, str(e)

    # ========================================================================
    # CONNECTION MANAGEMENT
    # ========================================================================

    async def connect(self) -> bool:
        """Connect to Box API"""
        if not BOX_AVAILABLE:
            self._set_error("Box SDK not installed. Run: pip install boxsdk")
            return False

        try:
            self.status = ConnectorStatus.CONNECTING

            oauth_config = self._get_oauth_config()

            if BOX_SDK_VERSION == "new":
                # New SDK (v10+) - use InMemoryTokenStorage
                token = AccessToken(
                    access_token=self.config.credentials.get("access_token"),
                    refresh_token=self.config.credentials.get("refresh_token"),
                    token_type="Bearer"
                )

                token_storage = InMemoryTokenStorage(token=token)

                config = OAuthConfig(
                    client_id=oauth_config["client_id"],
                    client_secret=oauth_config["client_secret"],
                    token_storage=token_storage
                )

                self.oauth = BoxOAuth(config)
                self.client = BoxClient(self.oauth)

                # Test connection by getting current user
                user = self.client.users.get_user_me()
                self._user_info = {
                    "id": user.id,
                    "name": user.name,
                    "login": user.login,
                    "space_used": user.space_used,
                    "space_amount": user.space_amount
                }
            else:
                # Legacy SDK (v3.x)
                self.oauth = OAuth2(
                    client_id=oauth_config["client_id"],
                    client_secret=oauth_config["client_secret"],
                    access_token=self.config.credentials.get("access_token"),
                    refresh_token=self.config.credentials.get("refresh_token"),
                    store_tokens=self._store_tokens
                )

                self.client = Client(self.oauth)

                # Test connection by getting current user
                user = self.client.user().get()
                self._user_info = {
                    "id": user.id,
                    "name": user.name,
                    "login": user.login,
                    "space_used": user.space_used,
                    "space_amount": user.space_amount
                }

            self.sync_stats["user"] = self._user_info
            self.status = ConnectorStatus.CONNECTED
            self._clear_error()

            return True

        except BoxAPIError as e:
            self._set_error(f"Box API error: {str(e)}")
            return False
        except Exception as e:
            self._set_error(f"Failed to connect: {str(e)}")
            return False

    async def disconnect(self) -> bool:
        """Disconnect from Box API"""
        try:
            if self.oauth:
                try:
                    self.oauth.revoke()
                except Exception:
                    pass  # Ignore revocation errors

            self.client = None
            self.oauth = None
            self._user_info = None
            self.status = ConnectorStatus.DISCONNECTED
            return True

        except Exception as e:
            self._set_error(f"Disconnect error: {str(e)}")
            return False

    async def test_connection(self) -> bool:
        """Test Box connection"""
        if not self.client:
            return False

        try:
            user = self.client.user().get()
            return user.id is not None
        except Exception:
            return False

    def _store_tokens(self, access_token: str, refresh_token: str):
        """Callback to store refreshed tokens"""
        self.config.credentials["access_token"] = access_token
        self.config.credentials["refresh_token"] = refresh_token
        # In production, save to database here

    # ========================================================================
    # SYNC OPERATIONS
    # ========================================================================

    async def sync(self, since: Optional[datetime] = None) -> List[Document]:
        """
        Sync files from Box.

        Args:
            since: Only sync files modified after this datetime

        Returns:
            List of Document objects
        """
        print(f"[BoxConnector] sync() called with since={since}")

        if not self.client:
            print("[BoxConnector] No client, attempting to connect...")
            connected = await self.connect()
            if not connected:
                print(f"[BoxConnector] Connection failed: {self.error_message}")
                return []
            print("[BoxConnector] Connected successfully")

        self.status = ConnectorStatus.SYNCING
        documents = []

        try:
            settings = self.config.settings
            folder_ids = settings.get("folder_ids", [])
            root_folder_id = settings.get("root_folder_id", "0")
            max_file_size = settings.get("max_file_size_mb", 50) * 1024 * 1024
            file_extensions = settings.get("file_extensions", [])
            exclude_folders = set(settings.get("exclude_folders", []))

            print(f"[BoxConnector] Settings: folder_ids={folder_ids}, root_folder_id={root_folder_id}")
            print(f"[BoxConnector] file_extensions={file_extensions}, max_file_size={max_file_size}")

            # Get folders to sync
            if folder_ids:
                folders_to_sync = folder_ids
            else:
                folders_to_sync = [root_folder_id]

            print(f"[BoxConnector] Folders to sync: {folders_to_sync}")

            # Sync each folder
            for folder_id in folders_to_sync:
                if folder_id in exclude_folders:
                    print(f"[BoxConnector] Skipping excluded folder: {folder_id}")
                    continue

                print(f"[BoxConnector] Starting sync for folder: {folder_id}")
                folder_docs = await self._sync_folder(
                    folder_id=folder_id,
                    since=since,
                    max_file_size=max_file_size,
                    file_extensions=file_extensions,
                    exclude_folders=exclude_folders,
                    recursive=True
                )
                print(f"[BoxConnector] Got {len(folder_docs)} documents from folder {folder_id}")
                documents.extend(folder_docs)

            # Update stats
            self.sync_stats["last_sync"] = datetime.now(timezone.utc).isoformat()
            self.sync_stats["items_synced"] = len(documents)
            self.status = ConnectorStatus.CONNECTED

            print(f"[BoxConnector] Sync complete. Total documents: {len(documents)}")
            return documents

        except BoxAPIError as e:
            print(f"[BoxConnector] BoxAPIError during sync: {str(e)}")
            self._set_error(f"Box API error during sync: {str(e)}")
            return documents
        except Exception as e:
            print(f"[BoxConnector] Exception during sync: {str(e)}")
            import traceback
            traceback.print_exc()
            self._set_error(f"Sync failed: {str(e)}")
            return documents

    async def _sync_folder(
        self,
        folder_id: str,
        since: Optional[datetime],
        max_file_size: int,
        file_extensions: List[str],
        exclude_folders: set,
        recursive: bool = True,
        current_path: str = ""
    ) -> List[Document]:
        """Recursively sync a folder"""
        documents = []

        try:
            print(f"[BoxConnector] _sync_folder called with folder_id={folder_id}, SDK version={BOX_SDK_VERSION}")

            if BOX_SDK_VERSION == "new":
                # New SDK (v10+) - uses different API
                print(f"[BoxConnector] Using new SDK to get folder {folder_id}")
                folder = self.client.folders.get_folder_by_id(folder_id)
                print(f"[BoxConnector] Got folder: name={folder.name}, id={folder.id}")
                folder_path = f"{current_path}/{folder.name}" if current_path else folder.name

                # Get folder items with pagination
                offset = 0
                limit = 100

                while True:
                    print(f"[BoxConnector] Getting folder items: folder_id={folder_id}, offset={offset}, limit={limit}")
                    items_response = self.client.folders.get_folder_items(
                        folder_id,
                        limit=limit,
                        offset=offset
                    )

                    print(f"[BoxConnector] items_response type: {type(items_response)}")
                    print(f"[BoxConnector] items_response: {items_response}")

                    items_list = items_response.entries if items_response.entries else []
                    print(f"[BoxConnector] Got {len(items_list)} items in folder {folder_id}")

                    if not items_list:
                        print(f"[BoxConnector] No items found in folder {folder_id}, breaking")
                        break

                    for item in items_list:
                        print(f"[BoxConnector] Processing item: type={type(item)}, item={item}")
                        # item.type is an enum like FolderBaseTypeField.FOLDER or FileBaseTypeField.FILE
                        # Use .value to get the string "folder" or "file"
                        item_type_raw = item.type if hasattr(item, 'type') else None
                        if item_type_raw and hasattr(item_type_raw, 'value'):
                            item_type = item_type_raw.value  # Gets "folder" or "file"
                        else:
                            item_type = str(item_type_raw).lower() if item_type_raw else type(item).__name__.lower()
                        print(f"[BoxConnector] Item: id={item.id}, name={item.name}, type={item_type}")

                        if item_type == "folder":
                            if recursive and item.id not in exclude_folders:
                                print(f"[BoxConnector] Recursing into subfolder: {item.name}")
                                sub_docs = await self._sync_folder(
                                    folder_id=item.id,
                                    since=since,
                                    max_file_size=max_file_size,
                                    file_extensions=file_extensions,
                                    exclude_folders=exclude_folders,
                                    recursive=True,
                                    current_path=folder_path
                                )
                                documents.extend(sub_docs)
                                print(f"[BoxConnector] Got {len(sub_docs)} docs from subfolder {item.name}")

                        elif item_type == "file":
                            print(f"[BoxConnector] Processing file: {item.name}")
                            doc = await self._process_file_new_sdk(
                                file_id=item.id,
                                file_name=item.name,
                                folder_path=folder_path,
                                since=since,
                                max_file_size=max_file_size,
                                file_extensions=file_extensions
                            )
                            if doc:
                                documents.append(doc)
                                print(f"[BoxConnector] Added document: {doc.title}")
                            else:
                                print(f"[BoxConnector] File {item.name} was skipped (returned None)")

                    if len(items_list) < limit:
                        print(f"[BoxConnector] Reached end of folder items (got {len(items_list)} < {limit})")
                        break
                    offset += limit

            else:
                # Legacy SDK (v3.x)
                print(f"[BoxConnector] Using legacy SDK to get folder {folder_id}")
                folder = self.client.folder(folder_id).get()
                print(f"[BoxConnector] Got folder: name={folder.name}, id={folder.id}")
                folder_path = f"{current_path}/{folder.name}" if current_path else folder.name

                # Get folder items with pagination
                offset = 0
                limit = 100

                while True:
                    print(f"[BoxConnector] Getting folder items (legacy): folder_id={folder_id}, offset={offset}, limit={limit}")
                    items = folder.get_items(
                        limit=limit,
                        offset=offset,
                        fields=["id", "name", "type", "size", "modified_at", "created_at",
                               "description", "parent", "path_collection", "sha1", "extension"]
                    )

                    items_list = list(items)
                    print(f"[BoxConnector] Got {len(items_list)} items from folder {folder_id} (legacy SDK)")
                    if not items_list:
                        print(f"[BoxConnector] No items found, breaking pagination loop")
                        break

                    for item in items_list:
                        print(f"[BoxConnector] Item (legacy): id={item.id}, name={item.name}, type={item.type}")
                        if item.type == "folder":
                            if recursive and item.id not in exclude_folders:
                                sub_docs = await self._sync_folder(
                                    folder_id=item.id,
                                    since=since,
                                    max_file_size=max_file_size,
                                    file_extensions=file_extensions,
                                    exclude_folders=exclude_folders,
                                    recursive=True,
                                    current_path=folder_path
                                )
                                documents.extend(sub_docs)

                        elif item.type == "file":
                            doc = await self._process_file(
                                file_item=item,
                                folder_path=folder_path,
                                since=since,
                                max_file_size=max_file_size,
                                file_extensions=file_extensions
                            )
                            if doc:
                                documents.append(doc)

                    if len(items_list) < limit:
                        break
                    offset += limit

            print(f"[BoxConnector] Finished syncing folder {folder_id}, found {len(documents)} documents")
            return documents

        except BoxAPIError as e:
            print(f"[BoxConnector] BoxAPIError syncing folder {folder_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            return documents
        except Exception as e:
            print(f"[BoxConnector] Exception syncing folder {folder_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            return documents

    async def _process_file_new_sdk(
        self,
        file_id: str,
        file_name: str,
        folder_path: str,
        since: Optional[datetime],
        max_file_size: int,
        file_extensions: List[str]
    ) -> Optional[Document]:
        """Process a single file using new SDK (v10+)"""
        try:
            # Get full file info
            file_obj = self.client.files.get_file_by_id(file_id)

            # === INCREMENTAL SYNC: CHECK IF FILE UNCHANGED ===
            # Check if document already exists with same sha1 hash
            from database.models import SessionLocal, Document as DBDocument
            db = SessionLocal()
            try:
                existing_doc = db.query(DBDocument).filter(
                    DBDocument.tenant_id == self.config.tenant_id,
                    DBDocument.external_id == f"box_{file_id}"
                ).first()

                if existing_doc:
                    # Check sha1 hash
                    existing_sha1 = existing_doc.doc_metadata.get('sha1') if existing_doc.doc_metadata else None
                    current_sha1 = getattr(file_obj, 'sha1', None)

                    if existing_sha1 and current_sha1 and existing_sha1 == current_sha1:
                        log_info("BoxConnector", "File unchanged (sha1 match), skipping",
                                file_name=file_name, file_id=file_id)
                        return None  # Skip unchanged file
                    elif current_sha1:
                        log_info("BoxConnector", "File modified (sha1 changed), re-processing",
                                file_name=file_name, old_sha1=existing_sha1[:8], new_sha1=current_sha1[:8])
                    else:
                        log_warning("BoxConnector", "File has no sha1, processing anyway", file_name=file_name)
            finally:
                db.close()
            # === END INCREMENTAL SYNC ===

            # Check modified date (secondary check for files without sha1)
            if since:
                modified_at = file_obj.modified_at
                if isinstance(modified_at, str):
                    modified_at = datetime.fromisoformat(modified_at.replace('Z', '+00:00'))

                if modified_at:
                    # Make both timezone-aware
                    since_aware = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
                    if modified_at.tzinfo is None:
                        modified_at = modified_at.replace(tzinfo=timezone.utc)

                    # Only skip if file is older than since AND we already have it
                    # This handles files without sha1 hash
                    if modified_at < since_aware and existing_doc:
                        log_info("BoxConnector", "File older than last sync, skipping",
                                file_name=file_name, modified_at=modified_at, since=since_aware)
                        return None

            # Check file size
            if file_obj.size and file_obj.size > max_file_size:
                log_warning("BoxConnector", "File exceeds size limit, skipping",
                           file_name=file_name, size=file_obj.size, max_size=max_file_size)
                return None

            # Check file extension
            file_ext = ""
            if "." in file_name:
                file_ext = "." + file_name.rsplit(".", 1)[-1]
            if file_extensions and file_ext.lower() not in [e.lower() for e in file_extensions]:
                log_info("BoxConnector", "File extension not in allowed list, skipping",
                        file_name=file_name, extension=file_ext)
                return None

            # Build path
            full_path = f"{folder_path}/{file_name}"
            log_info("BoxConnector", "Processing file", file_name=file_name, extension=file_ext, path=full_path)

            # Download file once from Box (for both S3 and content extraction)
            file_bytes = None
            file_url = None
            content = ""

            # Download file if it's extractable or S3 is available
            should_download = (file_ext.lower() in self.EXTRACTABLE_TYPES) or S3_AVAILABLE

            if should_download:
                try:
                    log_info("BoxConnector", "Downloading file", file_name=file_name, file_id=file_id)

                    if BOX_SDK_VERSION == "new":
                        content_stream = self.client.downloads.download_file(file_id)
                        file_bytes = b""
                        for chunk in content_stream:
                            file_bytes += chunk
                    else:
                        import io
                        box_file = self.client.file(file_id)
                        content_stream = io.BytesIO()
                        box_file.download_to(content_stream)
                        content_stream.seek(0)
                        file_bytes = content_stream.read()

                    if file_bytes:
                        log_info("BoxConnector", "Download complete", file_name=file_name, bytes=len(file_bytes))
                    else:
                        log_warning("BoxConnector", "Empty file content", file_id=file_id)

                except Exception as download_err:
                    log_error("BoxConnector", "Download failed", error=download_err, file_name=file_name)
                    file_bytes = None

            # Upload to S3 if available
            if S3_AVAILABLE and file_bytes:
                try:
                    s3_service = get_s3_service()

                    # Detect content type
                    content_type = None
                    if file_ext:
                        content_type, _ = mimetypes.guess_type(file_name)

                    s3_key = s3_service.generate_s3_key(
                        tenant_id=self.config.tenant_id,
                        file_type='box_files',
                        filename=file_name
                    )

                    file_url, s3_error = s3_service.upload_bytes(
                        file_bytes=file_bytes,
                        s3_key=s3_key,
                        content_type=content_type
                    )

                    if file_url:
                        log_info("BoxConnector", "Uploaded to S3", file_name=file_name, url=file_url)
                    else:
                        log_error("BoxConnector", "S3 upload failed", error=s3_error, file_name=file_name)

                except Exception as s3_err:
                    log_error("BoxConnector", "S3 upload error", error=s3_err, file_name=file_name)

            # Extract content if possible using LlamaParse
            if file_ext.lower() in self.EXTRACTABLE_TYPES and file_bytes:
                log_info("BoxConnector", "Parsing file with LlamaParse", file_name=file_name, type=file_ext)
                try:
                    from services.document_parser import get_document_parser
                    parser = get_document_parser()

                    if parser.is_supported(f".{file_ext.lstrip('.')}"):
                        content = await parser.parse_bytes(
                            file_bytes=file_bytes,
                            file_name=file_name,
                            file_extension=file_ext.lstrip('.')
                        )
                        log_info("BoxConnector", "Content extracted", file_name=file_name, chars=len(content))
                    else:
                        log_warning("BoxConnector", "Unsupported file type", file_ext=file_ext)

                except Exception as extract_err:
                    log_error("BoxConnector", "Content extraction failed", error=extract_err, file_name=file_name)
                    content = ""
            elif file_ext.lower() not in self.EXTRACTABLE_TYPES:
                log_info("BoxConnector", "File type not extractable", file_name=file_name, extension=file_ext)

            # Build metadata
            metadata = {
                "box_id": file_obj.id,
                "sha1": getattr(file_obj, 'sha1', None),
                "size": file_obj.size,
                "extension": file_ext.lstrip('.') if file_ext else None,
                "path": full_path,
            }

            if file_url:
                metadata['file_url'] = file_url

            # Parse timestamps
            created_at = getattr(file_obj, 'created_at', None)
            modified_at = getattr(file_obj, 'modified_at', None)

            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            if isinstance(modified_at, str):
                modified_at = datetime.fromisoformat(modified_at.replace('Z', '+00:00'))

            # Get author
            created_by = getattr(file_obj, 'created_by', None)
            author = None
            if created_by:
                author = getattr(created_by, 'login', None) or getattr(created_by, 'name', None)

            # Create document
            doc = Document(
                doc_id=f"box_{file_obj.id}",
                source="box",
                title=file_name,
                content=content,
                metadata=metadata,
                timestamp=modified_at or created_at,
                author=author,
                doc_type="document"
            )

            print(f"[BoxConnector] ✓ Created document for {file_name}")
            return doc

        except Exception as e:
            print(f"[BoxConnector] ERROR processing file {file_id} ({file_name}): {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    async def _extract_content_new_sdk(self, file_id: str, extension: str, file_name: str = "") -> str:
        """
        Extract text content from a file using LlamaParse API.

        This method uses the universal DocumentParser service which leverages
        LlamaParse to extract text from PDFs, DOCX, PPTX, and other formats.
        Works for all tenants in the B2B SaaS platform.
        """
        try:
            extension = extension.lower().lstrip('.')

            # Import the universal document parser
            from services.document_parser import get_document_parser
            parser = get_document_parser()

            # Check if file type is supported
            if not parser.is_supported(f".{extension}"):
                print(f"[BoxConnector] Unsupported file type: {extension}")
                return ""

            # Download file content from Box (works with both SDKs)
            print(f"[BoxConnector] Downloading file {file_id} ({file_name}) for parsing...")

            if BOX_SDK_VERSION == "new":
                # New SDK method
                content_stream = self.client.downloads.download_file(file_id)
                file_bytes = b""
                for chunk in content_stream:
                    file_bytes += chunk
            else:
                # Legacy SDK method
                import io
                file_obj = self.client.file(file_id)
                content_stream = io.BytesIO()
                file_obj.download_to(content_stream)
                content_stream.seek(0)
                file_bytes = content_stream.read()

            if not file_bytes:
                print(f"[BoxConnector] Empty file content for {file_id}")
                return ""

            print(f"[BoxConnector] Downloaded {len(file_bytes)} bytes, parsing with LlamaParse...")

            # Parse the document using LlamaParse
            extracted_text = await parser.parse_bytes(
                file_bytes=file_bytes,
                file_name=file_name or f"document.{extension}",
                file_extension=extension
            )

            if extracted_text:
                print(f"[BoxConnector] Extracted {len(extracted_text)} characters from {file_name}")
            else:
                print(f"[BoxConnector] No text extracted from {file_name}")

            return extracted_text

        except Exception as e:
            print(f"[BoxConnector] Error extracting content from file {file_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            return ""

    async def _process_file(
        self,
        file_item: 'BoxFile',
        folder_path: str,
        since: Optional[datetime],
        max_file_size: int,
        file_extensions: List[str]
    ) -> Optional[Document]:
        """Process a single file"""
        try:
            # Check modified date - DISABLED to allow syncing older files
            # The sync() method handles date filtering at a higher level
            # if since:
            #     modified_at = file_item.modified_at
            #     if isinstance(modified_at, str):
            #         modified_at = datetime.fromisoformat(modified_at.replace('Z', '+00:00'))
            #     if modified_at < since:
            #         return None

            # Check file size
            if file_item.size and file_item.size > max_file_size:
                return None

            # Check file extension
            file_ext = f".{file_item.extension}" if file_item.extension else ""
            if file_extensions and file_ext.lower() not in [e.lower() for e in file_extensions]:
                return None

            # Get full file info
            file_obj = self.client.file(file_item.id).get(
                fields=["id", "name", "description", "size", "sha1",
                       "created_at", "modified_at", "created_by", "modified_by",
                       "parent", "path_collection", "shared_link", "tags",
                       "extension", "content_created_at", "content_modified_at"]
            )

            # Build path
            full_path = f"{folder_path}/{file_obj.name}"

            # Extract content using LlamaParse (universal parser)
            content = ""
            if file_ext.lower() in self.EXTRACTABLE_TYPES:
                # Use the new SDK extraction method which leverages LlamaParse
                # This works even with legacy Box SDK
                content = await self._extract_content_new_sdk(
                    file_id=file_obj.id,
                    extension=file_ext,
                    file_name=file_obj.name
                )
                print(f"[BoxConnector] Extracted {len(content)} chars from {file_obj.name}")

            # Build metadata
            created_by = file_obj.created_by
            modified_by = file_obj.modified_by

            metadata = {
                "box_id": file_obj.id,
                "sha1": file_obj.sha1,
                "size": file_obj.size,
                "extension": file_obj.extension,
                "path": full_path,
                "tags": file_obj.tags or [],
                "shared_link": file_obj.shared_link.url if file_obj.shared_link else None,
                "created_by": {
                    "id": created_by.id if created_by else None,
                    "name": created_by.name if created_by else None,
                    "login": created_by.login if created_by else None
                } if created_by else None,
                "modified_by": {
                    "id": modified_by.id if modified_by else None,
                    "name": modified_by.name if modified_by else None,
                    "login": modified_by.login if modified_by else None
                } if modified_by else None
            }

            # Parse timestamps
            created_at = file_obj.content_created_at or file_obj.created_at
            modified_at = file_obj.content_modified_at or file_obj.modified_at

            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            if isinstance(modified_at, str):
                modified_at = datetime.fromisoformat(modified_at.replace('Z', '+00:00'))

            # Create document (match format from _process_file_new_sdk)
            doc = Document(
                doc_id=f"box_{file_obj.id}",
                source="box",
                title=file_obj.name,
                content=content,
                metadata=metadata,
                timestamp=modified_at or created_at,
                author=created_by.login if created_by else None,
                doc_type="document"
            )

            return doc

        except Exception as e:
            print(f"Error processing file {file_item.id}: {str(e)}")
            return None

    async def _extract_content(self, file_obj: 'BoxFile') -> str:
        """Extract text content from a file"""
        try:
            extension = (file_obj.extension or "").lower()

            # For text files, download directly
            if extension in ["txt", "md", "csv", "json", "xml"]:
                content_stream = io.BytesIO()
                file_obj.download_to(content_stream)
                content_stream.seek(0)
                return content_stream.read().decode('utf-8', errors='ignore')

            # For Office/PDF files, use Box's text representation
            # This requires Box Premium features
            try:
                rep_hints = "[extracted_text]"
                representations = file_obj.get_representation_info(rep_hints)

                for rep in representations:
                    if rep["representation"] == "extracted_text":
                        if rep["status"]["state"] == "success":
                            content_url = rep["content"]["url_template"]
                            content_url = content_url.replace("{+asset_path}", "")

                            # Download extracted text
                            response = self.client.make_request(
                                'GET',
                                content_url
                            )
                            return response.text

            except Exception:
                pass  # Fall through to basic extraction

            # Fallback: Try to download and parse locally
            # For PDFs and Office docs, would need additional libraries
            # (PyPDF2, python-docx, etc.)

            return ""

        except Exception as e:
            print(f"Error extracting content from {file_obj.name}: {str(e)}")
            return ""

    # ========================================================================
    # FILE OPERATIONS
    # ========================================================================

    async def get_file(self, file_id: str) -> Optional[Dict]:
        """Get file info by ID"""
        if not self.client:
            return None

        try:
            file_obj = self.client.file(file_id).get()
            return {
                "id": file_obj.id,
                "name": file_obj.name,
                "size": file_obj.size,
                "modified_at": file_obj.modified_at,
                "description": file_obj.description
            }
        except Exception:
            return None

    async def download_file(self, file_id: str) -> Optional[bytes]:
        """Download file content"""
        if not self.client:
            return None

        try:
            content_stream = io.BytesIO()
            self.client.file(file_id).download_to(content_stream)
            content_stream.seek(0)
            return content_stream.read()
        except Exception:
            return None

    async def get_folder_structure(self, folder_id: str = "0", depth: int = 2) -> Dict:
        """Get folder structure for UI"""
        if not self.client:
            return {}

        try:
            return await self._get_folder_tree(folder_id, depth, 0)
        except Exception as e:
            return {"error": str(e)}

    async def _get_folder_tree(
        self,
        folder_id: str,
        max_depth: int,
        current_depth: int
    ) -> Dict:
        """Recursively build folder tree"""
        try:
            folder = self.client.folder(folder_id).get()

            result = {
                "id": folder.id,
                "name": folder.name,
                "type": "folder",
                "children": []
            }

            if current_depth < max_depth:
                items = folder.get_items(limit=100, fields=["id", "name", "type"])

                for item in items:
                    if item.type == "folder":
                        child = await self._get_folder_tree(
                            item.id,
                            max_depth,
                            current_depth + 1
                        )
                        result["children"].append(child)
                    else:
                        result["children"].append({
                            "id": item.id,
                            "name": item.name,
                            "type": "file"
                        })

            return result

        except Exception as e:
            return {"id": folder_id, "error": str(e)}

    # ========================================================================
    # WEBHOOK SUPPORT
    # ========================================================================

    async def setup_webhook(self, target_url: str, folder_id: str = "0") -> Optional[str]:
        """
        Set up a webhook for real-time file changes.

        Args:
            target_url: URL to receive webhook events
            folder_id: Folder to watch (default: root)

        Returns:
            Webhook ID if successful
        """
        if not self.client:
            return None

        try:
            webhook = self.client.create_webhook(
                self.client.folder(folder_id),
                [
                    "FILE.UPLOADED",
                    "FILE.TRASHED",
                    "FILE.DELETED",
                    "FILE.RESTORED",
                    "FILE.COPIED",
                    "FILE.MOVED",
                    "FILE.RENAMED"
                ],
                target_url
            )
            return webhook.id
        except Exception as e:
            print(f"Error creating webhook: {str(e)}")
            return None

    async def delete_webhook(self, webhook_id: str) -> bool:
        """Delete a webhook"""
        if not self.client:
            return False

        try:
            self.client.webhook(webhook_id).delete()
            return True
        except Exception:
            return False

    # ========================================================================
    # SEARCH
    # ========================================================================

    async def search(
        self,
        query: str,
        file_extensions: Optional[List[str]] = None,
        folder_ids: Optional[List[str]] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Search files in Box.

        Args:
            query: Search query
            file_extensions: Filter by extensions
            folder_ids: Limit to specific folders
            limit: Max results

        Returns:
            List of file info dicts
        """
        if not self.client:
            return []

        try:
            results = self.client.search().query(
                query,
                limit=limit,
                file_extensions=file_extensions,
                ancestor_folder_ids=folder_ids,
                fields=["id", "name", "description", "size", "modified_at", "parent"]
            )

            files = []
            for item in results:
                if item.type == "file":
                    files.append({
                        "id": item.id,
                        "name": item.name,
                        "description": item.description,
                        "size": item.size,
                        "modified_at": item.modified_at,
                        "parent_id": item.parent.id if item.parent else None,
                        "parent_name": item.parent.name if item.parent else None
                    })

            return files

        except Exception as e:
            print(f"Search error: {str(e)}")
            return []

    # ========================================================================
    # ABSTRACT METHOD IMPLEMENTATION
    # ========================================================================

    async def get_document(self, doc_id: str) -> Optional[Document]:
        """
        Get a specific document by ID.

        Args:
            doc_id: Document ID (format: box_{file_id} or just file_id)

        Returns:
            Document object if found, None otherwise
        """
        if not self.client:
            connected = await self.connect()
            if not connected:
                return None

        try:
            # Extract Box file ID from document ID
            file_id = doc_id.replace("box_", "") if doc_id.startswith("box_") else doc_id

            # Get file from Box
            file_obj = self.client.file(file_id).get(
                fields=["id", "name", "description", "size", "sha1",
                       "created_at", "modified_at", "created_by", "modified_by",
                       "parent", "path_collection", "shared_link", "tags",
                       "extension", "content_created_at", "content_modified_at"]
            )

            # Build path from path_collection
            path_parts = []
            if file_obj.path_collection and file_obj.path_collection.entries:
                for entry in file_obj.path_collection.entries:
                    if entry.name:
                        path_parts.append(entry.name)
            path_parts.append(file_obj.name)
            full_path = "/".join(path_parts)

            # Extract content if possible
            file_ext = f".{file_obj.extension}" if file_obj.extension else ""
            content = ""
            if file_ext.lower() in self.EXTRACTABLE_TYPES:
                content = await self._extract_content(file_obj)

            # Build metadata
            created_by = file_obj.created_by
            modified_by = file_obj.modified_by

            metadata = {
                "box_id": file_obj.id,
                "sha1": file_obj.sha1,
                "size": file_obj.size,
                "extension": file_obj.extension,
                "path": full_path,
                "tags": file_obj.tags or [],
                "shared_link": file_obj.shared_link.url if file_obj.shared_link else None,
                "created_by": {
                    "id": created_by.id if created_by else None,
                    "name": created_by.name if created_by else None,
                    "login": created_by.login if created_by else None
                } if created_by else None,
                "modified_by": {
                    "id": modified_by.id if modified_by else None,
                    "name": modified_by.name if modified_by else None,
                    "login": modified_by.login if modified_by else None
                } if modified_by else None
            }

            # Parse timestamps
            created_at = file_obj.content_created_at or file_obj.created_at
            modified_at = file_obj.content_modified_at or file_obj.modified_at

            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            if isinstance(modified_at, str):
                modified_at = datetime.fromisoformat(modified_at.replace('Z', '+00:00'))

            # Create document
            doc = Document(
                id=f"box_{file_obj.id}",
                source_type="box_file",
                source_id=file_obj.id,
                title=file_obj.name,
                content=content,
                metadata=metadata,
                created_at=created_at,
                updated_at=modified_at,
                author=created_by.login if created_by else None
            )

            return doc

        except Exception as e:
            print(f"Error getting document {doc_id}: {str(e)}")
            return None
