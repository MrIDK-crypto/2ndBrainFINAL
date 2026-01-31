"""
Simple, reliable webscraper connector.
Built from scratch - clean and easy to understand.
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
from typing import List, Set, Optional
from dataclasses import dataclass


@dataclass
class ScrapedDocument:
    """A single scraped document"""
    doc_id: str  # URL
    title: str
    content: str
    source: str  # 'webscraper'
    url: str
    metadata: dict


class SimpleWebCrawler:
    """
    Simple web crawler that follows links and extracts content.
    Based on the user's base code - no complexity, just works.
    """

    def __init__(self, start_url: str, max_pages: int = 50, max_depth: int = 3):
        self.start_url = start_url
        self.domain = urlparse(start_url).netloc
        self.max_pages = max_pages
        self.max_depth = max_depth

        self.visited: Set[str] = set()
        self.documents: List[ScrapedDocument] = []

    def normalize_url(self, url: str) -> str:
        """Remove fragments and trailing slashes"""
        url = url.split('#')[0]  # Remove #section
        url = url.rstrip('/')
        return url

    def should_crawl(self, url: str, depth: int) -> bool:
        """Check if we should crawl this URL"""
        # Already visited?
        if url in self.visited:
            return False

        # Hit max pages?
        if len(self.visited) >= self.max_pages:
            return False

        # Too deep?
        if depth > self.max_depth:
            return False

        # Different domain?
        if urlparse(url).netloc != self.domain:
            return False

        # Skip common non-content files
        skip_extensions = ['.pdf', '.jpg', '.png', '.gif', '.zip', '.exe', '.mp4']
        if any(url.lower().endswith(ext) for ext in skip_extensions):
            return False

        return True

    def extract_text(self, soup: BeautifulSoup) -> str:
        """Extract clean text from HTML"""
        # Remove script and style tags
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()

        # Get text
        text = soup.get_text(separator='\n', strip=True)

        # Clean up whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = '\n'.join(lines)

        return text

    def crawl_page(self, url: str, depth: int = 0):
        """Crawl a single page and follow its links"""

        # Check if should crawl
        if not self.should_crawl(url, depth):
            return

        print(f"[Webscraper] Crawling (depth {depth}): {url}")
        self.visited.add(url)

        try:
            # Fetch page
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; 2ndBrain-Bot/1.0)'
            })

            if response.status_code != 200:
                print(f"[Webscraper] Skipping {url} - status {response.status_code}")
                return

            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract title
            title = soup.title.string if soup.title else url
            title = title.strip() if title else url

            # Extract content
            content = self.extract_text(soup)

            # Skip if no content
            if not content or len(content) < 100:
                print(f"[Webscraper] Skipping {url} - no content")
                return

            # Create document
            doc = ScrapedDocument(
                doc_id=url,
                title=title,
                content=content,
                source='webscraper',
                url=url,
                metadata={
                    'depth': depth,
                    'domain': self.domain,
                    'content_length': len(content)
                }
            )

            self.documents.append(doc)
            print(f"[Webscraper] ✓ Scraped: {title} ({len(content)} chars)")

            # Find and follow links (if not at max depth)
            if depth < self.max_depth and len(self.visited) < self.max_pages:
                for link in soup.find_all('a', href=True):
                    full_url = urljoin(url, link['href'])
                    full_url = self.normalize_url(full_url)

                    # Recursively crawl
                    self.crawl_page(full_url, depth + 1)

                    # Small delay to be polite
                    time.sleep(0.5)

        except Exception as e:
            print(f"[Webscraper] Error crawling {url}: {e}")

    def crawl(self) -> List[ScrapedDocument]:
        """Start crawling from the start URL"""
        print(f"[Webscraper] Starting crawl of {self.start_url}")
        print(f"[Webscraper] Max pages: {self.max_pages}, Max depth: {self.max_depth}")

        self.crawl_page(self.start_url, depth=0)

        print(f"[Webscraper] Finished! Scraped {len(self.documents)} pages")
        return self.documents


class WebScraperConnector:
    """
    Connector interface for the webscraper.
    Matches the backend connector pattern.
    """

    def __init__(self, config):
        self.config = config
        self.start_url = config.settings.get('start_url')
        self.max_pages = config.settings.get('max_pages', 50)
        self.max_depth = config.settings.get('max_depth', 3)

    def sync(self, since=None) -> List[ScrapedDocument]:
        """
        Sync (crawl) the website and return documents.

        Args:
            since: Not used for webscraper (always full crawl)

        Returns:
            List of ScrapedDocument objects
        """
        print(f"[Webscraper] sync() called with start_url={self.start_url}")

        try:
            crawler = SimpleWebCrawler(
                start_url=self.start_url,
                max_pages=self.max_pages,
                max_depth=self.max_depth
            )

            documents = crawler.crawl()

            return documents
        except Exception as e:
            print(f"[Webscraper] ERROR in sync(): {e}")
            import traceback
            traceback.print_exc()
            raise
