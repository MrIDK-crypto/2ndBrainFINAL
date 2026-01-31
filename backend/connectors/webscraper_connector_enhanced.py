"""
Enhanced Website Scraper Connector
Addresses all limitations of the original scraper:
- JavaScript rendering (Selenium/Playwright support)
- Authentication (cookies, headers, login flow)
- robots.txt compliance
- sitemap.xml parsing
- User-Agent rotation
- Proxy support
- Configurable content filters
"""

import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin, urlparse, robotparser
from collections import deque
from urllib.robotparser import RobotFileParser

from .base_connector import BaseConnector, ConnectorConfig, ConnectorStatus, Document
from utils.logger import log_info, log_error, log_warning

try:
    import requests
    from bs4 import BeautifulSoup
    SCRAPER_AVAILABLE = True
except ImportError:
    SCRAPER_AVAILABLE = False

# Optional: JavaScript rendering support
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class EnhancedWebScraperConnector(BaseConnector):
    """
    Enhanced website scraper with advanced features.

    Key Improvements:
    - JavaScript rendering (Selenium or Playwright)
    - Authentication support (cookies, headers, login forms)
    - robots.txt compliance
    - sitemap.xml parsing for efficient discovery
    - User-Agent rotation
    - Proxy support
    - Configurable content filters
    - Better error handling and retries
    """

    CONNECTOR_TYPE = "webscraper_enhanced"
    REQUIRED_CREDENTIALS = []
    OPTIONAL_SETTINGS = {
        # Basic settings
        "start_url": "",  # Required - starting URL to crawl
        "priority_paths": [],  # Paths to prioritize
        "max_depth": 3,
        "max_pages": 50,
        "rate_limit_delay": 1.0,

        # Content filters
        "min_content_length": 100,  # Configurable minimum (was hardcoded)
        "max_content_length": 1000000,  # Skip extremely large pages
        "include_pdfs": True,
        "allowed_extensions": [".html", ".htm", ".pdf", ""],
        "exclude_patterns": ["#", "mailto:", "tel:"],

        # JavaScript rendering
        "render_js": False,  # Enable for React/Vue/Angular sites
        "js_engine": "playwright",  # "selenium" or "playwright"
        "js_wait_time": 3,  # Seconds to wait for JS to load

        # Authentication
        "auth_type": None,  # "basic", "cookies", "form", "bearer"
        "auth_username": None,
        "auth_password": None,
        "auth_cookies": {},  # Dict of cookie name:value
        "auth_headers": {},  # Dict of header name:value
        "auth_login_url": None,  # URL of login form
        "auth_login_selectors": {},  # {"username": "#user", "password": "#pass", "submit": "button"}

        # Compliance
        "respect_robots_txt": True,  # Check robots.txt before crawling
        "use_sitemap": True,  # Parse sitemap.xml for URLs
        "crawl_delay": None,  # Override robots.txt crawl-delay

        # User-Agent rotation
        "user_agents": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (compatible; 2ndBrainBot/2.0; +https://github.com/your-repo)"
        ],
        "rotate_user_agent": False,

        # Proxy support
        "use_proxy": False,
        "proxy_url": None,  # "http://user:pass@proxy:port"
        "proxy_rotation": False,  # Rotate through proxy list
        "proxy_list": [],  # List of proxy URLs

        # Retry logic
        "max_retries": 3,
        "retry_delay": 2,  # Exponential backoff base
    }

    # List of common User-Agents (fallback if not configured)
    DEFAULT_USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.visited_urls: Set[str] = set()
        self.session = None
        self.base_domain = None
        self.robots_parser = None
        self.current_user_agent_idx = 0
        self.current_proxy_idx = 0
        self.driver = None  # Selenium/Playwright driver

    async def connect(self) -> bool:
        """Test website connection and setup"""
        if not SCRAPER_AVAILABLE:
            self._set_error("BeautifulSoup4 and requests not installed. Run: pip install beautifulsoup4 requests")
            return False

        try:
            self.status = ConnectorStatus.CONNECTING

            start_url = self.config.settings.get("start_url", "").strip()
            if not start_url:
                self._set_error("No start_url configured")
                return False

            # Validate URL
            if not start_url.startswith(("http://", "https://")):
                start_url = "https://" + start_url
                self.config.settings["start_url"] = start_url

            # Extract base domain
            parsed = urlparse(start_url)
            self.base_domain = f"{parsed.scheme}://{parsed.netloc}"

            # Setup session
            self.session = requests.Session()

            # Setup proxy
            if self.config.settings.get("use_proxy"):
                proxy_url = self._get_next_proxy()
                if proxy_url:
                    self.session.proxies = {
                        "http": proxy_url,
                        "https": proxy_url
                    }
                    log_info("WebScraperEnhanced", "Using proxy", proxy=proxy_url)

            # Setup User-Agent
            user_agent = self._get_next_user_agent()
            self.session.headers.update({"User-Agent": user_agent})

            # Setup authentication
            await self._setup_authentication()

            # Load robots.txt
            if self.config.settings.get("respect_robots_txt", True):
                await self._load_robots_txt()

            # Test connection
            response = self.session.get(start_url, timeout=30, allow_redirects=True)
            if response.status_code not in [200, 301, 302]:
                self._set_error(f"Failed to connect: HTTP {response.status_code}")
                return False

            self.status = ConnectorStatus.CONNECTED
            self._clear_error()
            log_info("WebScraperEnhanced", "Connected successfully", url=start_url)
            return True

        except Exception as e:
            log_error("WebScraperEnhanced", "Connection failed", error=e)
            self._set_error(f"Failed to connect: {str(e)}")
            return False

    async def disconnect(self) -> bool:
        """Cleanup resources"""
        if self.session:
            self.session.close()
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        self.visited_urls.clear()
        self.status = ConnectorStatus.DISCONNECTED
        return True

    async def _setup_authentication(self):
        """Setup authentication based on configured type"""
        auth_type = self.config.settings.get("auth_type")

        if not auth_type:
            return

        if auth_type == "basic":
            username = self.config.settings.get("auth_username")
            password = self.config.settings.get("auth_password")
            if username and password:
                from requests.auth import HTTPBasicAuth
                self.session.auth = HTTPBasicAuth(username, password)
                log_info("WebScraperEnhanced", "Basic auth configured")

        elif auth_type == "bearer":
            token = self.config.settings.get("auth_password")  # Use password field for token
            if token:
                self.session.headers["Authorization"] = f"Bearer {token}"
                log_info("WebScraperEnhanced", "Bearer auth configured")

        elif auth_type == "cookies":
            cookies = self.config.settings.get("auth_cookies", {})
            for name, value in cookies.items():
                self.session.cookies.set(name, value)
            log_info("WebScraperEnhanced", "Cookies configured", count=len(cookies))

        elif auth_type == "form":
            # Login via form submission
            login_url = self.config.settings.get("auth_login_url")
            username = self.config.settings.get("auth_username")
            password = self.config.settings.get("auth_password")

            if login_url and username and password:
                # Simple form login (customize as needed)
                response = self.session.post(login_url, data={
                    "username": username,
                    "password": password
                })

                if response.status_code == 200:
                    log_info("WebScraperEnhanced", "Form login successful")
                else:
                    log_warning("WebScraperEnhanced", "Form login failed", status=response.status_code)

        # Additional custom headers
        custom_headers = self.config.settings.get("auth_headers", {})
        if custom_headers:
            self.session.headers.update(custom_headers)
            log_info("WebScraperEnhanced", "Custom headers added", count=len(custom_headers))

    async def _load_robots_txt(self):
        """Load and parse robots.txt"""
        try:
            robots_url = urljoin(self.base_domain, "/robots.txt")
            self.robots_parser = RobotFileParser()
            self.robots_parser.set_url(robots_url)
            self.robots_parser.read()

            # Check crawl delay
            crawl_delay = self.robots_parser.crawl_delay("*")
            if crawl_delay and not self.config.settings.get("crawl_delay"):
                self.config.settings["rate_limit_delay"] = max(
                    crawl_delay,
                    self.config.settings.get("rate_limit_delay", 1.0)
                )
                log_info("WebScraperEnhanced", "robots.txt crawl delay applied", delay=crawl_delay)

        except Exception as e:
            log_warning("WebScraperEnhanced", "Could not load robots.txt", error=str(e))
            self.robots_parser = None

    def _can_fetch(self, url: str) -> bool:
        """Check if URL can be fetched according to robots.txt"""
        if not self.config.settings.get("respect_robots_txt", True):
            return True

        if self.robots_parser:
            user_agent = self.session.headers.get("User-Agent", "*")
            return self.robots_parser.can_fetch(user_agent, url)

        return True

    async def _discover_urls_from_sitemap(self) -> List[str]:
        """Discover URLs from sitemap.xml"""
        urls = []

        if not self.config.settings.get("use_sitemap", True):
            return urls

        try:
            sitemap_url = urljoin(self.base_domain, "/sitemap.xml")
            response = self.session.get(sitemap_url, timeout=10)

            if response.status_code == 200:
                root = ET.fromstring(response.content)

                # Handle different sitemap formats
                namespaces = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

                # Check if it's a sitemap index
                for sitemap in root.findall('.//ns:sitemap', namespaces):
                    loc = sitemap.find('ns:loc', namespaces)
                    if loc is not None:
                        # Recursively fetch sitemap
                        urls.extend(await self._fetch_sitemap_urls(loc.text))

                # Extract URLs from regular sitemap
                for url_elem in root.findall('.//ns:url', namespaces):
                    loc = url_elem.find('ns:loc', namespaces)
                    if loc is not None:
                        urls.append(loc.text)

                log_info("WebScraperEnhanced", "Discovered URLs from sitemap", count=len(urls))

        except Exception as e:
            log_warning("WebScraperEnhanced", "Could not parse sitemap", error=str(e))

        return urls

    async def _fetch_sitemap_urls(self, sitemap_url: str) -> List[str]:
        """Fetch URLs from a specific sitemap file"""
        urls = []
        try:
            response = self.session.get(sitemap_url, timeout=10)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                namespaces = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

                for url_elem in root.findall('.//ns:url', namespaces):
                    loc = url_elem.find('ns:loc', namespaces)
                    if loc is not None:
                        urls.append(loc.text)
        except Exception as e:
            log_warning("WebScraperEnhanced", "Error fetching sitemap file", url=sitemap_url, error=str(e))

        return urls

    def _get_next_user_agent(self) -> str:
        """Get next User-Agent (rotation support)"""
        user_agents = self.config.settings.get("user_agents", self.DEFAULT_USER_AGENTS)

        if self.config.settings.get("rotate_user_agent", False):
            ua = user_agents[self.current_user_agent_idx % len(user_agents)]
            self.current_user_agent_idx += 1
            return ua

        return user_agents[0] if user_agents else self.DEFAULT_USER_AGENTS[0]

    def _get_next_proxy(self) -> Optional[str]:
        """Get next proxy (rotation support)"""
        proxy_list = self.config.settings.get("proxy_list", [])
        proxy_url = self.config.settings.get("proxy_url")

        if not proxy_list and not proxy_url:
            return None

        if self.config.settings.get("proxy_rotation", False) and proxy_list:
            proxy = proxy_list[self.current_proxy_idx % len(proxy_list)]
            self.current_proxy_idx += 1
            return proxy

        return proxy_url or (proxy_list[0] if proxy_list else None)

    async def _render_with_js(self, url: str) -> str:
        """Render page with JavaScript using Selenium or Playwright"""
        js_engine = self.config.settings.get("js_engine", "playwright")
        wait_time = self.config.settings.get("js_wait_time", 3)

        if js_engine == "selenium" and SELENIUM_AVAILABLE:
            return await self._render_selenium(url, wait_time)
        elif js_engine == "playwright" and PLAYWRIGHT_AVAILABLE:
            return await self._render_playwright(url, wait_time)
        else:
            log_error("WebScraperEnhanced", f"{js_engine} not available, falling back to requests")
            response = self.session.get(url, timeout=30)
            return response.text

    async def _render_selenium(self, url: str, wait_time: int) -> str:
        """Render with Selenium"""
        if not self.driver:
            options = ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument(f'user-agent={self._get_next_user_agent()}')

            self.driver = webdriver.Chrome(options=options)

        self.driver.get(url)
        time.sleep(wait_time)  # Wait for JS to execute

        return self.driver.page_source

    async def _render_playwright(self, url: str, wait_time: int) -> str:
        """Render with Playwright"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=self._get_next_user_agent())
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(wait_time)

            content = page.content()
            browser.close()

            return content

    async def sync(self, since: Optional[datetime] = None) -> List[Document]:
        """Crawl website with all enhancements"""
        if self.status != ConnectorStatus.CONNECTED:
            if not await self.connect():
                return []

        self.status = ConnectorStatus.SYNCING
        documents = []

        try:
            start_url = self.config.settings["start_url"]
            max_depth = self.config.settings.get("max_depth", 3)
            max_pages = self.config.settings.get("max_pages", 50)
            rate_limit = self.config.settings.get("rate_limit_delay", 1.0)

            log_info("WebScraperEnhanced", "Starting enhanced crawl",
                    url=start_url, max_depth=max_depth, max_pages=max_pages)

            # Discover URLs from sitemap
            sitemap_urls = await self._discover_urls_from_sitemap()

            # Initialize queue with sitemap URLs + start URL
            queue = deque([(start_url, 0)])
            for url in sitemap_urls[:max_pages]:  # Limit sitemap URLs
                if self._can_fetch(url):
                    queue.append((url, 1))

            self.visited_urls.clear()
            pages_crawled = 0

            while queue and pages_crawled < max_pages:
                url, depth = queue.popleft()

                if url in self.visited_urls or depth > max_depth:
                    continue

                # Check robots.txt
                if not self._can_fetch(url):
                    log_info("WebScraperEnhanced", "robots.txt disallows", url=url)
                    continue

                doc = await self._crawl_page_enhanced(url, depth)
                if doc:
                    documents.append(doc)
                    pages_crawled += 1
                    log_info("WebScraperEnhanced", "Page crawled",
                            count=f"{pages_crawled}/{max_pages}", url=url)

                    # Extract links
                    if depth < max_depth:
                        links = self._extract_links(doc.metadata.get("html_content", ""), url)
                        for link in links:
                            if link not in self.visited_urls:
                                queue.append((link, depth + 1))

                time.sleep(rate_limit)

            log_info("WebScraperEnhanced", "Crawl complete",
                    pages=pages_crawled, documents=len(documents))

            self.config.last_sync = datetime.now()
            self.status = ConnectorStatus.CONNECTED

        except Exception as e:
            log_error("WebScraperEnhanced", "Sync failed", error=e)
            self._set_error(f"Sync failed: {str(e)}")

        return documents

    async def _crawl_page_enhanced(self, url: str, depth: int) -> Optional[Document]:
        """Crawl page with retry logic and enhanced features"""
        max_retries = self.config.settings.get("max_retries", 3)
        retry_delay = self.config.settings.get("retry_delay", 2)

        for attempt in range(max_retries):
            try:
                self.visited_urls.add(url)

                # Render with JS if enabled
                if self.config.settings.get("render_js", False):
                    html_content = await self._render_with_js(url)
                    return self._parse_html_enhanced(url, html_content, depth)
                else:
                    response = self.session.get(url, timeout=30, allow_redirects=True)

                    if response.status_code != 200:
                        log_warning("WebScraperEnhanced", "Non-200 status",
                                  url=url, status=response.status_code)
                        return None

                    content_type = response.headers.get("Content-Type", "").lower()

                    if "application/pdf" in content_type:
                        if self.config.settings.get("include_pdfs", True):
                            return self._parse_pdf_enhanced(url, response.content)
                        return None

                    if "text/html" in content_type:
                        return self._parse_html_enhanced(url, response.text, depth)

                    return None

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                    log_warning("WebScraperEnhanced", "Retry after error",
                              url=url, attempt=attempt+1, wait=wait_time)
                    time.sleep(wait_time)
                else:
                    log_error("WebScraperEnhanced", "Max retries exceeded", url=url, error=e)
                    return None

        return None

    def _parse_html_enhanced(self, url: str, html_content: str, depth: int) -> Optional[Document]:
        """Parse HTML with configurable content filters"""
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Extract title
            title = soup.find("title")
            title_text = title.get_text().strip() if title else urlparse(url).path

            # Remove script and style
            for script in soup(["script", "style"]):
                script.decompose()

            # Extract main content
            main_content = (
                soup.find("main") or
                soup.find("article") or
                soup.find("div", id=re.compile(r"content|main", re.I)) or
                soup.find("div", class_=re.compile(r"content|main", re.I)) or
                soup.find("body") or
                soup
            )

            text = main_content.get_text(separator="\n", strip=True)
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            content = "\n\n".join(lines)

            # Configurable content length filters
            min_length = self.config.settings.get("min_content_length", 100)
            max_length = self.config.settings.get("max_content_length", 1000000)

            if len(content) < min_length:
                log_info("WebScraperEnhanced", "Content too short",
                        url=url, length=len(content), min=min_length)
                return None

            if len(content) > max_length:
                log_warning("WebScraperEnhanced", "Content too long, truncating",
                           url=url, length=len(content))
                content = content[:max_length]

            # Extract metadata
            description = soup.find("meta", attrs={"name": "description"})
            description_text = description.get("content", "").strip() if description else ""

            keywords = soup.find("meta", attrs={"name": "keywords"})
            keywords_text = keywords.get("content", "").strip() if keywords else ""

            return Document(
                doc_id=f"webscraper_{self._url_to_id(url)}",
                source="webscraper_enhanced",
                content=content,
                title=title_text,
                metadata={
                    "url": url,
                    "depth": depth,
                    "description": description_text,
                    "keywords": keywords_text,
                    "word_count": len(content.split()),
                    "html_content": html_content
                },
                timestamp=datetime.now(),
                url=url,
                doc_type="webpage"
            )

        except Exception as e:
            log_error("WebScraperEnhanced", "HTML parsing failed", url=url, error=e)
            return None

    def _parse_pdf_enhanced(self, url: str, pdf_content: bytes) -> Optional[Document]:
        """Parse PDF with better error handling"""
        try:
            import PyPDF2
            import io

            pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
            text_parts = []

            for page_num, page in enumerate(pdf_reader.pages, 1):
                text = page.extract_text()
                if text.strip():
                    text_parts.append(f"--- Page {page_num} ---\n{text}")

            content = "\n\n".join(text_parts)

            min_length = self.config.settings.get("min_content_length", 100)
            if len(content) < min_length:
                return None

            title = urlparse(url).path.split("/")[-1]
            if pdf_reader.metadata and pdf_reader.metadata.title:
                title = pdf_reader.metadata.title

            return Document(
                doc_id=f"webscraper_{self._url_to_id(url)}",
                source="webscraper_enhanced",
                content=content,
                title=title,
                metadata={
                    "url": url,
                    "content_type": "pdf",
                    "page_count": len(pdf_reader.pages),
                    "word_count": len(content.split())
                },
                timestamp=datetime.now(),
                url=url,
                doc_type="pdf"
            )

        except Exception as e:
            log_error("WebScraperEnhanced", "PDF parsing failed", url=url, error=e)
            return None

    def _extract_links(self, html_content: str, base_url: str) -> List[str]:
        """Extract links with better filtering"""
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            links = []

            for anchor in soup.find_all("a", href=True):
                href = anchor["href"].strip()

                # Expanded exclusion patterns
                exclude_patterns = self.config.settings.get("exclude_patterns", [])
                exclude_patterns.extend(["#", "mailto:", "tel:", "javascript:"])

                if not href or any(href.startswith(p) for p in exclude_patterns):
                    continue

                absolute_url = urljoin(base_url, href)
                absolute_url = absolute_url.split("#")[0]  # Remove fragment

                parsed = urlparse(absolute_url)
                url_domain = f"{parsed.scheme}://{parsed.netloc}"

                if url_domain == self.base_domain:
                    links.append(absolute_url)

            return list(set(links))

        except Exception as e:
            log_error("WebScraperEnhanced", "Link extraction failed", error=e)
            return []

    def _url_to_id(self, url: str) -> str:
        """Convert URL to unique ID"""
        import hashlib
        return hashlib.sha256(url.encode()).hexdigest()  # SHA256 instead of MD5

    async def get_document(self, doc_id: str) -> Optional[Document]:
        """Get specific document"""
        return None

    async def test_connection(self) -> bool:
        """Test connection"""
        return await self.connect()
