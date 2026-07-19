"""
Web search and scraping tools for Tank AI agents.
Provides WebSearchTool and WebPageScraperTool.
"""
import re
import httpx
from typing import List, Dict, Any
from tank.ai.tools import tool


@tool
async def search_web(query: str) -> str:
    """
    Searches the live web for a query string and returns top snippets, titles, and URLs.
    
    Args:
        query: The search keywords or question to look up on the web.
    """
    url = "https://html.duckduckgo.com/html/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Tank/0.1.0"}
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.post(url, data={"q": query}, headers=headers)
            html = resp.text

        # Extract search result snippets
        results = []
        snippets = re.findall(r'<a class="result__snippet[^"]*"[^>]*>(.*?)</a>', html, re.DOTALL)
        titles = re.findall(r'<a class="result__url"[^>]*>(.*?)</a>', html, re.DOTALL)

        for i in range(min(4, len(snippets))):
            clean_snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
            clean_url = re.sub(r'<[^>]+>', '', titles[i]).strip() if i < len(titles) else ""
            results.append(f"[{i+1}] {clean_snippet}\nSource: {clean_url}")

        if not results:
            return f"No search results found for query: '{query}'."

        return "\n\n".join(results)
    except Exception as e:
        return f"Web search failed for '{query}': {str(e)}"


@tool
async def scrape_web_page(url: str) -> str:
    """
    Fetches a web page URL and returns its text content formatted for AI reading.
    
    Args:
        url: The full web page URL (e.g. https://example.com/article).
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Tank/0.1.0"}
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            html = resp.text

        # Strip scripts, styles, and HTML tags
        clean = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', clean)
        text = re.sub(r'\s+', ' ', text).strip()

        # Limit to 3000 chars to avoid blowing prompt limits
        if len(text) > 3000:
            text = text[:3000] + "... [content truncated]"

        return text or f"No readable text content extracted from {url}."
    except Exception as e:
        return f"Failed to scrape web page at {url}: {str(e)}"
