"""
GitHub Connector
OAuth integration and repository code analysis for 2nd Brain.
"""

import os
import re
import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
import base64


class GitHubConnector:
    """
    Handle GitHub OAuth and repository access.

    Features:
    - OAuth 2.0 flow
    - Repository listing
    - Code file fetching
    - Smart filtering (code files only)
    - Rate limit handling
    """

    def __init__(self, access_token: Optional[str] = None):
        """
        Initialize GitHub connector.

        Args:
            access_token: GitHub OAuth access token
        """
        self.access_token = access_token
        self.client_id = os.getenv('GITHUB_CLIENT_ID')
        self.client_secret = os.getenv('GITHUB_CLIENT_SECRET')
        self.redirect_uri = os.getenv('GITHUB_REDIRECT_URI', 'http://localhost:5003/api/integrations/github/callback')

        self.base_url = 'https://api.github.com'
        self.headers = {
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28'
        }

        if self.access_token:
            self.headers['Authorization'] = f'Bearer {self.access_token}'

    # =========================================================================
    # OAUTH FLOW
    # =========================================================================

    def get_authorization_url(self, state: str) -> str:
        """
        Get GitHub OAuth authorization URL.

        Args:
            state: CSRF protection state

        Returns:
            Authorization URL to redirect user to
        """
        scopes = ['repo', 'read:user', 'read:org']
        scope_string = ' '.join(scopes)

        return (
            f"https://github.com/login/oauth/authorize?"
            f"client_id={self.client_id}&"
            f"redirect_uri={self.redirect_uri}&"
            f"scope={scope_string}&"
            f"state={state}"
        )

    def exchange_code_for_token(self, code: str) -> Dict:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from GitHub

        Returns:
            {
                'access_token': '...',
                'token_type': 'bearer',
                'scope': 'repo,read:user'
            }
        """
        response = requests.post(
            'https://github.com/login/oauth/access_token',
            headers={'Accept': 'application/json'},
            data={
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'code': code,
                'redirect_uri': self.redirect_uri
            }
        )

        response.raise_for_status()
        data = response.json()

        if 'error' in data:
            raise Exception(f"GitHub OAuth error: {data.get('error_description', data['error'])}")

        return data

    # =========================================================================
    # USER & REPOSITORY INFO
    # =========================================================================

    def get_user_info(self) -> Dict:
        """
        Get authenticated user information.

        Returns:
            {
                'login': 'username',
                'id': 12345,
                'name': 'Full Name',
                'email': 'user@example.com',
                'avatar_url': '...',
                'public_repos': 10,
                'total_private_repos': 5
            }
        """
        response = requests.get(
            f'{self.base_url}/user',
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_repositories(self, per_page: int = 100) -> List[Dict]:
        """
        Get all repositories accessible to user.

        Args:
            per_page: Results per page (max 100)

        Returns:
            List of repository dicts with:
            - id, name, full_name
            - description, language
            - private, fork, archived
            - default_branch, size
            - created_at, updated_at, pushed_at
        """
        repos = []
        page = 1

        while True:
            response = requests.get(
                f'{self.base_url}/user/repos',
                headers=self.headers,
                params={
                    'per_page': per_page,
                    'page': page,
                    'sort': 'updated',
                    'affiliation': 'owner,collaborator,organization_member'
                }
            )
            response.raise_for_status()

            batch = response.json()
            if not batch:
                break

            repos.extend(batch)

            # Check if more pages
            if len(batch) < per_page:
                break

            page += 1

        return repos

    # =========================================================================
    # CODE FETCHING
    # =========================================================================

    # Code file extensions to analyze
    CODE_EXTENSIONS = {
        # Backend
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rb', '.php',
        '.cs', '.cpp', '.c', '.h', '.hpp', '.rs', '.kt', '.swift', '.scala',

        # Frontend
        '.html', '.css', '.scss', '.sass', '.less', '.vue', '.svelte',

        # Config & Infrastructure
        '.yaml', '.yml', '.json', '.toml', '.ini', '.conf',
        '.tf', '.tfvars',  # Terraform

        # Documentation
        '.md', '.rst', '.txt',

        # Database
        '.sql',

        # Scripts
        '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat'
    }

    # Directories to skip
    SKIP_DIRS = {
        'node_modules', 'venv', 'env', '.venv', '__pycache__', 'dist', 'build',
        '.git', '.svn', '.hg', 'vendor', 'tmp', 'temp', 'cache', '.cache',
        'coverage', '.coverage', '.pytest_cache', '.mypy_cache', '.tox',
        'logs', 'log', '.DS_Store', 'target', 'out', '.next', '.nuxt'
    }

    def get_repository_tree(self, owner: str, repo: str, branch: str = 'main') -> List[Dict]:
        """
        Get repository file tree recursively.

        Args:
            owner: Repository owner
            repo: Repository name
            branch: Branch name (default: main)

        Returns:
            List of file dicts with:
            - path, type (blob/tree), sha, size, url
        """
        try:
            response = requests.get(
                f'{self.base_url}/repos/{owner}/{repo}/git/trees/{branch}',
                headers=self.headers,
                params={'recursive': '1'}
            )
            response.raise_for_status()

            data = response.json()
            return data.get('tree', [])

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # Try 'master' branch
                response = requests.get(
                    f'{self.base_url}/repos/{owner}/{repo}/git/trees/master',
                    headers=self.headers,
                    params={'recursive': '1'}
                )
                response.raise_for_status()
                data = response.json()
                return data.get('tree', [])
            raise

    def filter_code_files(self, tree: List[Dict], max_files: int = 500) -> List[Dict]:
        """
        Filter tree to only code files (skip binaries, dependencies, etc.).

        Args:
            tree: Repository tree from get_repository_tree()
            max_files: Maximum files to return

        Returns:
            Filtered list of code files sorted by relevance
        """
        code_files = []

        for item in tree:
            # Only process files (blobs), not directories
            if item['type'] != 'blob':
                continue

            path = item['path']

            # Skip files in ignored directories
            path_parts = path.split('/')
            if any(part in self.SKIP_DIRS for part in path_parts):
                continue

            # Check file extension
            _, ext = os.path.splitext(path.lower())
            if ext not in self.CODE_EXTENSIONS:
                continue

            # Skip very large files (>1MB)
            if item.get('size', 0) > 1_000_000:
                continue

            code_files.append(item)

        # Prioritize important files
        def priority_score(item):
            path = item['path'].lower()
            score = 0

            # Boost important files
            if 'readme' in path:
                score += 1000
            if path.endswith('.md'):
                score += 100
            if 'config' in path or 'settings' in path:
                score += 50
            if path.endswith(('.py', '.js', '.ts', '.go', '.java')):
                score += 10

            # Penalize test files (but don't skip)
            if 'test' in path or 'spec' in path:
                score -= 5

            return -score  # Negative for reverse sort

        code_files.sort(key=priority_score)

        return code_files[:max_files]

    def get_file_content(self, owner: str, repo: str, path: str) -> Optional[str]:
        """
        Get file content from GitHub.

        Args:
            owner: Repository owner
            repo: Repository name
            path: File path in repository

        Returns:
            File content as string, or None if binary/error
        """
        try:
            response = requests.get(
                f'{self.base_url}/repos/{owner}/{repo}/contents/{path}',
                headers=self.headers
            )
            response.raise_for_status()

            data = response.json()

            # GitHub returns content as base64
            if 'content' in data:
                content_b64 = data['content']
                content_bytes = base64.b64decode(content_b64)

                # Try to decode as UTF-8 (skip binary files)
                try:
                    return content_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    return None

            return None

        except Exception as e:
            print(f"[GitHub] Error fetching {path}: {e}")
            return None

    def fetch_repository_code(
        self,
        owner: str,
        repo: str,
        max_files: int = 100,
        max_chars_per_file: int = 50000
    ) -> List[Dict]:
        """
        Fetch code files from repository with content.

        Args:
            owner: Repository owner
            repo: Repository name
            max_files: Maximum files to fetch
            max_chars_per_file: Max characters per file

        Returns:
            List of dicts:
            {
                'path': 'src/main.py',
                'content': '...',
                'language': 'Python',
                'size': 1234,
                'lines': 50
            }
        """
        print(f"[GitHub] Fetching repository tree: {owner}/{repo}")
        tree = self.get_repository_tree(owner, repo)

        print(f"[GitHub] Found {len(tree)} total items in repository")
        code_files = self.filter_code_files(tree, max_files=max_files)

        print(f"[GitHub] Filtered to {len(code_files)} code files")

        results = []

        for i, file_item in enumerate(code_files, 1):
            path = file_item['path']
            print(f"[GitHub] [{i}/{len(code_files)}] Fetching: {path}")

            content = self.get_file_content(owner, repo, path)

            if content is None:
                print(f"[GitHub]   → Skipped (binary or error)")
                continue

            # Truncate if too long
            if len(content) > max_chars_per_file:
                content = content[:max_chars_per_file] + "\n\n[... truncated ...]"

            # Detect language from extension
            _, ext = os.path.splitext(path)
            language = self._extension_to_language(ext)

            results.append({
                'path': path,
                'content': content,
                'language': language,
                'size': file_item.get('size', len(content)),
                'lines': content.count('\n') + 1
            })

        print(f"[GitHub] Successfully fetched {len(results)} files")
        return results

    @staticmethod
    def _extension_to_language(ext: str) -> str:
        """Map file extension to language name"""
        mapping = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.ts': 'TypeScript',
            '.jsx': 'React JSX',
            '.tsx': 'React TSX',
            '.java': 'Java',
            '.go': 'Go',
            '.rb': 'Ruby',
            '.php': 'PHP',
            '.cs': 'C#',
            '.cpp': 'C++',
            '.c': 'C',
            '.h': 'C/C++ Header',
            '.rs': 'Rust',
            '.kt': 'Kotlin',
            '.swift': 'Swift',
            '.scala': 'Scala',
            '.html': 'HTML',
            '.css': 'CSS',
            '.scss': 'SCSS',
            '.yaml': 'YAML',
            '.yml': 'YAML',
            '.json': 'JSON',
            '.md': 'Markdown',
            '.sql': 'SQL',
            '.sh': 'Shell',
            '.bash': 'Bash',
        }
        return mapping.get(ext.lower(), 'Unknown')

    # =========================================================================
    # RATE LIMIT HANDLING
    # =========================================================================

    def get_rate_limit(self) -> Dict:
        """
        Get current rate limit status.

        Returns:
            {
                'limit': 5000,
                'remaining': 4999,
                'reset': 1234567890  # Unix timestamp
            }
        """
        response = requests.get(
            f'{self.base_url}/rate_limit',
            headers=self.headers
        )
        response.raise_for_status()

        data = response.json()
        return data['resources']['core']
