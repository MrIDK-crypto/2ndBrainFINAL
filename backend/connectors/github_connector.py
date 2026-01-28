"""
GitHub Connector
Connects to GitHub API to extract code, issues, PRs, and documentation.
"""

from datetime import datetime
from typing import List, Dict, Optional, Any
import base64

from .base_connector import BaseConnector, ConnectorConfig, ConnectorStatus, Document

# Note: Requires PyGithub
# pip install PyGithub

try:
    from github import Github, GithubException
    GITHUB_AVAILABLE = True
except ImportError:
    GITHUB_AVAILABLE = False


class GitHubConnector(BaseConnector):
    """
    GitHub connector for extracting code and project knowledge.

    Extracts:
    - Repository README and documentation
    - Issues and discussions
    - Pull request descriptions and reviews
    - Code files (key files like configs, main modules)
    - Commit messages
    - Wiki pages
    """

    CONNECTOR_TYPE = "github"
    REQUIRED_CREDENTIALS = ["access_token"]
    OPTIONAL_SETTINGS = {
        "repos": [],  # Specific repos to sync (owner/repo format)
        "include_code": True,
        "include_issues": True,
        "include_prs": True,
        "include_wiki": True,
        "max_issues_per_repo": None,  # No limit - sync all issues
        "max_prs_per_repo": None,  # No limit - sync all PRs
        "code_extensions": [".py", ".js", ".ts", ".md", ".json", ".yaml", ".yml"]
        # No limits on file size, directory depth, or file count
    }

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.client = None
        self.user = None

    async def connect(self) -> bool:
        """Connect to GitHub API"""
        if not GITHUB_AVAILABLE:
            self._set_error("PyGithub not installed. Run: pip install PyGithub")
            return False

        try:
            self.status = ConnectorStatus.CONNECTING

            self.client = Github(self.config.credentials.get("access_token"))

            # Test connection by getting user
            self.user = self.client.get_user()
            _ = self.user.login  # Force API call

            self.sync_stats["user"] = self.user.login
            self.status = ConnectorStatus.CONNECTED
            self._clear_error()
            return True

        except GithubException as e:
            self._set_error(f"GitHub API error: {e.data.get('message', str(e))}")
            return False
        except Exception as e:
            self._set_error(f"Failed to connect: {str(e)}")
            return False

    async def disconnect(self) -> bool:
        """Disconnect from GitHub API"""
        self.client = None
        self.user = None
        self.status = ConnectorStatus.DISCONNECTED
        return True

    async def test_connection(self) -> bool:
        """Test GitHub connection"""
        if not self.client:
            return False

        try:
            _ = self.client.get_user().login
            return True
        except Exception:
            return False

    async def sync(self, since: Optional[datetime] = None) -> List[Document]:
        """Sync documents from GitHub"""
        if not self.client:
            await self.connect()

        if self.status != ConnectorStatus.CONNECTED:
            return []

        self.status = ConnectorStatus.SYNCING
        documents = []

        try:
            # Get repos to sync
            repos = await self._get_repos()

            for repo in repos:
                repo_docs = await self._sync_repo(repo, since)
                documents.extend(repo_docs)

            # Update stats
            self.sync_stats["documents_synced"] = len(documents)
            self.sync_stats["repos_synced"] = len(repos)
            self.sync_stats["sync_time"] = datetime.now().isoformat()

            self.config.last_sync = datetime.now()
            self.status = ConnectorStatus.CONNECTED

        except Exception as e:
            self._set_error(f"Sync failed: {str(e)}")

        return documents

    async def get_document(self, doc_id: str) -> Optional[Document]:
        """Get a specific document"""
        # Parse doc_id to determine type and fetch
        return None

    async def _get_repos(self) -> List:
        """Get list of repos to sync"""
        repos = []

        configured_repos = self.config.settings.get("repos", [])

        if configured_repos:
            # Get specific repos
            for repo_name in configured_repos:
                try:
                    repo = self.client.get_repo(repo_name)
                    repos.append(repo)
                except GithubException:
                    print(f"Could not access repo: {repo_name}")
        else:
            # Get user's repos (including forks)
            for repo in self.user.get_repos():
                repos.append(repo)

        return repos

    async def _sync_repo(self, repo, since: Optional[datetime]) -> List[Document]:
        """Sync documents from a single repository"""
        documents = []

        repo_name = repo.full_name

        # Sync README
        readme_doc = await self._get_readme(repo)
        if readme_doc:
            documents.append(readme_doc)

        # Sync issues
        if self.config.settings.get("include_issues", True):
            issue_docs = await self._sync_issues(repo, since)
            documents.extend(issue_docs)

        # Sync PRs
        if self.config.settings.get("include_prs", True):
            pr_docs = await self._sync_prs(repo, since)
            documents.extend(pr_docs)

        # Sync code files
        if self.config.settings.get("include_code", True):
            code_docs = await self._sync_code(repo)
            documents.extend(code_docs)

        return documents

    async def _get_readme(self, repo) -> Optional[Document]:
        """Get repository README"""
        try:
            readme = repo.get_readme()
            content = base64.b64decode(readme.content).decode('utf-8', errors='ignore')

            return Document(
                doc_id=f"github_{repo.full_name}_readme",
                source="github",
                content=f"# {repo.full_name} README\n\n{content}",
                title=f"README - {repo.name}",
                metadata={
                    "repo": repo.full_name,
                    "path": readme.path,
                    "doc_subtype": "readme"
                },
                author=repo.owner.login,
                url=readme.html_url,
                doc_type="documentation"
            )

        except GithubException:
            return None

    async def _sync_issues(self, repo, since: Optional[datetime]) -> List[Document]:
        """Sync repository issues"""
        documents = []
        max_issues = self.config.settings.get("max_issues_per_repo")  # None = unlimited

        try:
            issues = repo.get_issues(state="all", sort="updated", direction="desc")

            count = 0
            for issue in issues:
                if max_issues is not None and count >= max_issues:
                    break

                if since and issue.updated_at < since:
                    break

                # Get issue content
                content = f"""GitHub Issue: {issue.title}
Repository: {repo.full_name}
State: {issue.state}
Created: {issue.created_at}
Author: {issue.user.login if issue.user else 'Unknown'}
Labels: {', '.join([l.name for l in issue.labels])}

{issue.body or '(No description)'}

---
Comments ({issue.comments}):
"""
                # Get top comments
                for comment in issue.get_comments()[:5]:
                    content += f"\n@{comment.user.login}: {comment.body[:500]}\n"

                documents.append(Document(
                    doc_id=f"github_{repo.full_name}_issue_{issue.number}",
                    source="github",
                    content=content,
                    title=f"Issue #{issue.number}: {issue.title}",
                    metadata={
                        "repo": repo.full_name,
                        "issue_number": issue.number,
                        "state": issue.state,
                        "labels": [l.name for l in issue.labels],
                        "doc_subtype": "issue"
                    },
                    timestamp=issue.updated_at,
                    author=issue.user.login if issue.user else None,
                    url=issue.html_url,
                    doc_type="issue"
                ))

                count += 1

        except GithubException as e:
            print(f"Error syncing issues for {repo.full_name}: {e}")

        return documents

    async def _sync_prs(self, repo, since: Optional[datetime]) -> List[Document]:
        """Sync pull requests"""
        documents = []
        max_prs = self.config.settings.get("max_prs_per_repo")  # None = unlimited

        try:
            prs = repo.get_pulls(state="all", sort="updated", direction="desc")

            count = 0
            for pr in prs:
                if max_prs is not None and count >= max_prs:
                    break

                if since and pr.updated_at < since:
                    break

                # Get PR content
                content = f"""GitHub Pull Request: {pr.title}
Repository: {repo.full_name}
State: {pr.state}
Merged: {pr.merged}
Created: {pr.created_at}
Author: {pr.user.login if pr.user else 'Unknown'}
Base: {pr.base.ref} <- Head: {pr.head.ref}

{pr.body or '(No description)'}

---
Changed files: {pr.changed_files}
Additions: +{pr.additions}
Deletions: -{pr.deletions}
"""

                documents.append(Document(
                    doc_id=f"github_{repo.full_name}_pr_{pr.number}",
                    source="github",
                    content=content,
                    title=f"PR #{pr.number}: {pr.title}",
                    metadata={
                        "repo": repo.full_name,
                        "pr_number": pr.number,
                        "state": pr.state,
                        "merged": pr.merged,
                        "doc_subtype": "pull_request"
                    },
                    timestamp=pr.updated_at,
                    author=pr.user.login if pr.user else None,
                    url=pr.html_url,
                    doc_type="pull_request"
                ))

                count += 1

        except GithubException as e:
            print(f"Error syncing PRs for {repo.full_name}: {e}")

        return documents

    async def _sync_code(self, repo) -> List[Document]:
        """Sync all code files"""
        documents = []

        extensions = self.config.settings.get("code_extensions", [".py", ".js", ".md"])

        # Important files to always try to get
        important_files = [
            "README.md", "CONTRIBUTING.md", "CHANGELOG.md",
            "package.json", "requirements.txt", "setup.py",
            "Dockerfile", "docker-compose.yml",
            ".env.example", "config.yaml", "config.json"
        ]

        try:
            contents = repo.get_contents("")
            files_to_process = []

            # Walk through entire repo (no depth limit)
            while contents:
                file_content = contents.pop(0)

                if file_content.type == "dir":
                    # Traverse all directories
                    try:
                        contents.extend(repo.get_contents(file_content.path))
                    except GithubException:
                        pass
                elif file_content.type == "file":
                    # Check if we should include this file
                    is_important = file_content.name in important_files
                    has_extension = any(file_content.name.endswith(ext) for ext in extensions)

                    if is_important or has_extension:
                        files_to_process.append(file_content)

            # Process all files (no limit)
            for file_content in files_to_process:
                try:
                    content = base64.b64decode(file_content.content).decode('utf-8', errors='ignore')

                    documents.append(Document(
                        doc_id=f"github_{repo.full_name}_file_{file_content.path.replace('/', '_')}",
                        source="github",
                        content=f"# {repo.full_name}/{file_content.path}\n\n```\n{content}\n```",
                        title=f"{file_content.name} - {repo.name}",
                        metadata={
                            "repo": repo.full_name,
                            "path": file_content.path,
                            "size": file_content.size,
                            "doc_subtype": "code"
                        },
                        url=file_content.html_url,
                        doc_type="code"
                    ))

                except Exception as e:
                    print(f"Error processing file {file_content.path}: {e}")

        except GithubException as e:
            print(f"Error syncing code for {repo.full_name}: {e}")

        return documents
