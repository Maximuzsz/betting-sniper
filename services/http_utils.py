"""
Shared HTTP utilities for services.
Includes cache, headers and retry requests.
"""
import requests
import hashlib
import random
import time
from datetime import datetime

# === GLOBAL REQUEST CACHE ===
_request_cache = {}
_cache_ttl = 3600  # 1 hour in seconds


def get_cached(key, max_age=_cache_ttl):
    """Return cached value if still valid."""
    if key in _request_cache:
        data, timestamp = _request_cache[key]
        if datetime.now().timestamp() - timestamp < max_age:
            return data
        del _request_cache[key]
    return None


def set_cached(key, value):
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


def request_with_retry(url, max_retries=3, timeout=8, headers=None):
    """Make HTTP request with retry and exponential backoff."""
    if headers is None:
        headers = get_headers()
    
    # Check cache first
    cache_key = hashlib.md5(url.encode()).hexdigest()
    cached = get_cached(cache_key)
    if cached:
        return cached
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                time.sleep(0.5 * (2 ** attempt))
            
            response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            
            if response.status_code == 200:
                set_cached(cache_key, response)
                return response
            elif response.status_code == 429:
                wait_time = int(response.headers.get('Retry-After', 5))
                time.sleep(min(wait_time, 10))
            elif response.status_code >= 500:
                continue
            else:
                return response
                
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                continue
        except requests.exceptions.RequestException:
            if attempt < max_retries - 1:
                continue
            raise
    
    return None
