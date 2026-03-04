"""
Web Search Module — DuckDuckGo Search Integration
==================================================
Provides real web search capabilities using DuckDuckGo's search API.
Can fetch search results and optionally extract page content.
"""

import re
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx

try:
    from duckduckgo_search import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single web search result."""
    title: str
    url: str
    snippet: str
    body: Optional[str] = None  # Full page content if fetched


@dataclass
class WebSearchResponse:
    """Full web search response."""
    query: str
    results: List[SearchResult]
    error: Optional[str] = None
    answer: Optional[str] = None  # Instant answer if available


class WebSearchEngine:
    """
    DuckDuckGo-powered web search engine.
    
    Features:
    - Text search with configurable result count
    - Instant answers for factual queries
    - Optional page content fetching
    - Clean text extraction from HTML
    """
    
    # User agent for HTTP requests
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    
    # Max content length to fetch per page (chars)
    MAX_CONTENT_LENGTH = 5000
    
    def __init__(self, timeout: float = 10.0):
        """
        Initialize search engine.
        
        Args:
            timeout: HTTP request timeout in seconds
        """
        self.timeout = timeout
        self._ddgs: Optional[DDGS] = None
    
    @property
    def ddgs(self) -> "DDGS":
        """Lazy-initialize DuckDuckGo search client."""
        if self._ddgs is None:
            if not DDGS_AVAILABLE:
                raise ImportError("duckduckgo-search not installed. Run: pip install duckduckgo-search")
            self._ddgs = DDGS()
        return self._ddgs
    
    def search(
        self,
        query: str,
        max_results: int = 5,
        region: str = "wt-wt",  # Worldwide
        fetch_content: bool = False,
    ) -> WebSearchResponse:
        """
        Perform a web search using DuckDuckGo.
        
        Args:
            query: Search query string
            max_results: Maximum number of results to return (1-10)
            region: DuckDuckGo region code (wt-wt = worldwide)
            fetch_content: Whether to fetch full page content for top results
            
        Returns:
            WebSearchResponse with search results
        """
        if not DDGS_AVAILABLE:
            return WebSearchResponse(
                query=query,
                results=[],
                error="DuckDuckGo search not available. Install: pip install duckduckgo-search"
            )
        
        max_results = min(max(1, max_results), 10)
        results: List[SearchResult] = []
        answer: Optional[str] = None
        
        try:
            # Try to get instant answer first
            try:
                instant = self.ddgs.answers(query)
                if instant:
                    answer = instant[0].get("text", "")
            except Exception:
                pass
            
            # Perform web search
            raw_results = list(self.ddgs.text(
                query,
                max_results=max_results,
                region=region,
                safesearch="moderate",
            ))
            
            for r in raw_results:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", r.get("link", "")),
                    snippet=r.get("body", r.get("snippet", "")),
                    body=None
                ))
            
            # Optionally fetch page content in parallel
            if fetch_content and results:
                self._fetch_content_parallel(results[:3])  # Top 3 only
            
            return WebSearchResponse(
                query=query,
                results=results,
                answer=answer
            )
            
        except Exception as e:
            logger.warning(f"Web search error: {e}")
            return WebSearchResponse(
                query=query,
                results=[],
                error=str(e)
            )
    
    def _fetch_content_parallel(self, results: List[SearchResult], max_workers: int = 3):
        """Fetch page content for multiple results in parallel."""
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._fetch_page_content, r.url): r
                for r in results
            }
            for future in as_completed(futures, timeout=self.timeout):
                result = futures[future]
                try:
                    content = future.result()
                    if content:
                        result.body = content
                except Exception as e:
                    logger.debug(f"Failed to fetch {result.url}: {e}")
    
    def _fetch_page_content(self, url: str) -> Optional[str]:
        """
        Fetch and extract text content from a URL.
        
        Args:
            url: Web page URL
            
        Returns:
            Cleaned text content or None if failed
        """
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(
                    url,
                    headers={"User-Agent": self.USER_AGENT}
                )
                response.raise_for_status()
                
                html = response.text
                return self._extract_text(html)
                
        except Exception as e:
            logger.debug(f"Failed to fetch {url}: {e}")
            return None
    
    def _extract_text(self, html: str) -> str:
        """
        Extract readable text from HTML content.
        Very basic extraction without BeautifulSoup dependency.
        """
        # Remove script and style blocks
        text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<head[^>]*>.*?</head>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        
        # Decode HTML entities
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&quot;', '"', text)
        text = re.sub(r'&#\d+;', '', text)
        
        # Clean whitespace
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        # Truncate
        if len(text) > self.MAX_CONTENT_LENGTH:
            text = text[:self.MAX_CONTENT_LENGTH] + "..."
        
        return text
    
    def news_search(self, query: str, max_results: int = 5) -> WebSearchResponse:
        """
        Search for recent news articles.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            WebSearchResponse with news results
        """
        if not DDGS_AVAILABLE:
            return WebSearchResponse(
                query=query,
                results=[],
                error="DuckDuckGo search not available"
            )
        
        try:
            raw_results = list(self.ddgs.news(
                query,
                max_results=min(max_results, 10),
                safesearch="moderate"
            ))
            
            results = [
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", r.get("link", "")),
                    snippet=r.get("body", ""),
                    body=None
                )
                for r in raw_results
            ]
            
            return WebSearchResponse(query=query, results=results)
            
        except Exception as e:
            logger.warning(f"News search error: {e}")
            return WebSearchResponse(query=query, results=[], error=str(e))


# ── Module-level convenience functions ──────────────────────────────────────

_engine: Optional[WebSearchEngine] = None


def get_search_engine() -> WebSearchEngine:
    """Get or create the global search engine instance."""
    global _engine
    if _engine is None:
        _engine = WebSearchEngine()
    return _engine


def web_search(
    query: str,
    max_results: int = 5,
    fetch_content: bool = False
) -> WebSearchResponse:
    """
    Perform a web search (convenience function).
    
    Args:
        query: Search query
        max_results: Max results (1-10)
        fetch_content: Whether to fetch page bodies
        
    Returns:
        WebSearchResponse
    """
    return get_search_engine().search(query, max_results, fetch_content=fetch_content)


def format_search_results(response: WebSearchResponse, include_urls: bool = True) -> str:
    """
    Format search results as readable text for LLM consumption.
    
    Args:
        response: WebSearchResponse object
        include_urls: Whether to include URLs in output
        
    Returns:
        Formatted string with search results
    """
    if response.error:
        return f"Search failed: {response.error}"
    
    if not response.results:
        return f"No results found for: {response.query}"
    
    lines = [f"Web search results for: {response.query}\n"]
    
    # Include instant answer if available
    if response.answer:
        lines.append(f"Quick Answer: {response.answer}\n")
    
    for i, r in enumerate(response.results, 1):
        lines.append(f"{i}. {r.title}")
        if include_urls:
            lines.append(f"   URL: {r.url}")
        lines.append(f"   {r.snippet}")
        if r.body:
            # First 500 chars of body
            preview = r.body[:500] + "..." if len(r.body) > 500 else r.body
            lines.append(f"   Content: {preview}")
        lines.append("")
    
    return "\n".join(lines)
