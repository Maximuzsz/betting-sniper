"""
Web Scraping Module - Utility functions for HTTP requests and scraping.
"""
import requests
import time
import hashlib
import random
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

# === GLOBAL REQUEST CACHE ===
_request_cache = {}
_cache_ttl = 3600  # 1 hour in seconds


def _get_cached(key, max_age=_cache_ttl):
    """Return cached value if still valid."""
    if key in _request_cache:
        data, timestamp = _request_cache[key]
        if datetime.now().timestamp() - timestamp < max_age:
            return data
        del _request_cache[key]
    return None


def _set_cached(key, value):
    """Store value in cache."""
    _request_cache[key] = (value, datetime.now().timestamp())


# === REALISTIC USER AGENTS ===
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
]


def get_headers(referer=None):
    """Return realistic HTTP headers to simulate browser."""
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
    }
    if referer:
        headers['Referer'] = referer
    return headers
m

def request_with_retry(url, max_retries=3, timeout=8, headers=None):
    """
    Make HTTP request with retry and exponential backoff.
    
    Args:
        url: URL to request
        max_retries: Maximum number of attempts
        timeout: Timeout in seconds
        headers: Custom headers (if None, uses default headers)
    
    Returns:
        Response object or None if failed
    """
    if headers is None:
        headers = get_headers()
    
    # Check cache first
    cache_key = hashlib.md5(url.encode()).hexdigest()
    cached = _get_cached(cache_key)
    if cached:
        return cached
    
    for attempt in range(max_retries):
        try:
            # Delay between attempts (exponential backoff)
            if attempt > 0:
                time.sleep(0.5 * (2 ** attempt))
            
            response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            
            if response.status_code == 200:
                _set_cached(cache_key, response)
                return response
            elif response.status_code == 429:  # Rate limited
                wait_time = int(response.headers.get('Retry-After', 5))
                time.sleep(min(wait_time, 10))
            elif response.status_code >= 500:  # Server error - retry
                continue
            else:
                return response  # Client error - don't retry
                
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                continue
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                continue
            raise
    
    return None


def scrape_page_content(url, remove_selectors=None):
    """
    Extract content from a web page removing irrelevant elements.
    
    Args:
        url: Page URL to scrape
        remove_selectors: List of CSS selectors to remove (optional)
    
    Returns:
        Tuple (text_content, soup_object) or (None, None) if failed
    """
    try:
        response = request_with_retry(url, timeout=8)
        if not response or response.status_code != 200:
            return None, None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Default selectors to remove irrelevant elements
        default_remove_selectors = [
            'script', 'style', 'nav', 'footer', 'header', 'iframe', 'svg', 
            'button', 'aside', 'form', 'noscript', 'figure',
            '[class*="banner"]', '[class*="widget"]', '[class*="poll"]', 
            '[class*="sign-wall"]', '[class*="comments"]', '[class*="related"]',
            '[class*="advertisement"]', '[class*="ad-"]', '[class*="sidebar"]',
            '[class*="social"]', '[class*="share"]', '[class*="newsletter"]',
            '[id*="comments"]', '[id*="sidebar"]', '[id*="related"]'
        ]
        
        selectors_to_remove = remove_selectors if remove_selectors else default_remove_selectors
        
        for selector in selectors_to_remove:
            for tag in soup.select(selector):
                tag.decompose()
        
        # Extract page title
        title = ""
        title_tag = soup.find(['h1', 'title'])
        if title_tag:
            title = title_tag.get_text().strip()
        
        # Extract main content prioritizing articles
        main_content = ""
        
        # Try to find main article content
        article_selectors = [
            'article', '[class*="article-body"]', '[class*="post-content"]',
            '[class*="entry-content"]', '[class*="content-text"]', 'main',
            '[itemprop="articleBody"]', '[class*="materia-"]'
        ]
        
        for selector in article_selectors:
            article = soup.select_one(selector)
            if article:
                text_elements = article.find_all(['p', 'li', 'h2', 'h3'])
                main_content = ' '.join([t.get_text().strip() for t in text_elements if len(t.get_text()) > 15])
                if len(main_content) > 300:
                    break
        
        # Fallback: extract all relevant paragraphs
        if len(main_content) < 300:
            text_elements = soup.find_all(['p', 'li', 'h2', 'h3'])
            main_content = ' '.join([t.get_text().strip() for t in text_elements if len(t.get_text()) > 20])
        
        # Limit content size
        full_content = f"TITLE: {title}\n\nCONTENT:\n{main_content[:8000]}"
        
        return full_content, soup
        
    except Exception as e:
        print(f"      ⚠️ Error extracting content: {e}")
        return None, None


def get_cached(key, max_age=_cache_ttl):
    """Public wrapper to access cache."""
    return _get_cached(key, max_age)


def set_cached(key, value):
    """Public wrapper to set cache."""
    _set_cached(key, value)
