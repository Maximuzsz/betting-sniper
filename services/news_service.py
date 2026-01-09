"""
Sports news search service.
Uses DuckDuckGo to find lineups, injuries and pre-match analysis.
"""
import unicodedata
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup
from services.webscraper import scrape_page_content

# Suppress DuckDuckGo warnings
warnings.filterwarnings("ignore", module="duckduckgo_search")

# Try to import DuckDuckGo
DDGS_AVAILABLE = False
try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        DDGS_AVAILABLE = True
    except ImportError:
        DDGS = None


class NewsService:
    TRUSTED_SOURCES = {
        'br': ['ge.globo.com', 'uol.com.br', 'espn.com.br', 'gazetaesportiva.com', 
               'lance.com.br', 'terra.com.br', 'goal.com/br'],
        'int': ['espn.com', 'skysports.com', 'bbc.com/sport', 'goal.com', 
                'football-italia.net', 'marca.com', 'as.com', 'transfermarkt']
    }
    
    BLOCKLIST = [
        "loja", "camisa", "u20", "u17", "sub-20", "sub-17", "feminino", "basquete", 
        "wikipedia", "konami", "efootball", "fifa", "videogame", "forex", "amazon", 
        "ingresso", "mercado da bola", "vaivem", "transferencia", "shopping",
        "promoção", "desconto", "fantasy", "palpite", "aposta", "bet365", "betano"
    ]
    
    RELEVANCE_KEYWORDS = {
        'high': ["escalacao", "provavel escalacao", "lineup", "starting xi", 
                 "lesao", "lesionado", "injury", "suspenso", "desfalque", "titular", "reserva", "poupado"],
        'medium': ["tecnico", "treinador", "coach", "formacao", "esquema",
                   "tatico", "pre-jogo", "preview", "coletivo", "treino"],
        'low': ["atacante", "zagueiro", "goleiro", "meio-campo", "forward", "defender"]
    }

    @staticmethod
    def _normalize(text):
        """Remove accents and normalize text for comparison."""
        if not text:
            return ""
        return unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8').lower()

    def _calculate_relevance_score(self, text):
        """Calculate relevance score based on keywords."""
        text_norm = self._normalize(text)
        score = 0
        for keyword in self.RELEVANCE_KEYWORDS['high']:
            if keyword in text_norm:
                score += 3
        for keyword in self.RELEVANCE_KEYWORDS['medium']:
            if keyword in text_norm:
                score += 2
        for keyword in self.RELEVANCE_KEYWORDS['low']:
            if keyword in text_norm:
                score += 1
        return score

    def _is_trusted_source(self, url, is_brazilian):
        """Check if URL is from a trusted source."""
        sources = self.TRUSTED_SOURCES['br'] if is_brazilian else self.TRUSTED_SOURCES['int']
        return any(source in url.lower() for source in sources)

    def _extract_lineup_info(self, soup, team_names):
        """Extract lineup information from HTML."""
        lineup_data = {'lesionados': [], 'suspensos': [], 'desfalques': [], 'duvidas': []}
        
        lineup_selectors = ['div[class*="lineup"]', 'div[class*="escalacao"]', 'div[class*="formation"]']
        for selector in lineup_selectors:
            for el in soup.select(selector):
                text = el.get_text(separator=' ', strip=True)
                if len(text) > 20:
                    lineup_data.setdefault('escalacao', []).append(text[:500])
        
        for p in soup.find_all(['p', 'li']):
            text = p.get_text().strip()
            text_lower = self._normalize(text)
            
            if any(w in text_lower for w in ['lesao', 'lesionado', 'injury', 'machucado']):
                lineup_data['lesionados'].append(text[:300])
            elif any(w in text_lower for w in ['suspenso', 'suspension', 'cartao']):
                lineup_data['suspensos'].append(text[:300])
            elif any(w in text_lower for w in ['duvida', 'incerto', 'doubt']):
                lineup_data['duvidas'].append(text[:300])
            elif any(w in text_lower for w in ['desfalque', 'ausencia', 'fora']):
                lineup_data['desfalques'].append(text[:300])
        
        return lineup_data

    def _scrape_page_content(self, url, team_names=None):
        """Extract page content with structured parsing."""
        try:
            content, soup = scrape_page_content(url)
            if not content or not soup:
                return None, None
            
            lineup_info = self._extract_lineup_info(soup, team_names) if team_names else None
            
            if lineup_info:
                structured = "\n\nSTRUCTURED INFO:"
                if lineup_info['lesionados']:
                    structured += f"\nINJURED: {' | '.join(lineup_info['lesionados'][:3])}"
                if lineup_info['suspensos']:
                    structured += f"\nSUSPENDED: {' | '.join(lineup_info['suspensos'][:3])}"
                if lineup_info['desfalques']:
                    structured += f"\nOUT: {' | '.join(lineup_info['desfalques'][:3])}"
                if lineup_info['duvidas']:
                    structured += f"\nDOUBTFUL: {' | '.join(lineup_info['duvidas'][:3])}"
                content += structured
            
            return content, lineup_info
        except Exception as e:
            print(f"      ⚠️ Error extracting content: {e}")
            return None, None

    def _search_with_fallback(self, ddgs, query, region, max_results=8):
        """Execute search with fallbacks."""
        for kwargs in [
            {'timelimit': 'w'},
            {},
            {'region': None}
        ]:
            try:
                final_kwargs = {'region': region, 'safesearch': 'off', 'max_results': max_results}
                final_kwargs.update({k: v for k, v in kwargs.items() if v is not None})
                if kwargs.get('region') is None:
                    final_kwargs.pop('region', None)
                results = list(ddgs.text(query, **final_kwargs))
                if results:
                    return results
            except:
                continue
        return []

    def get_match_context(self, home_team, away_team, competition="futebol"):
        """Fetch news context for a specific match."""
        print(f"🕵️ Sniper Started: {home_team} x {away_team}...")
        
        if not DDGS_AVAILABLE:
            return "News search service unavailable. AI will use statistics only."
        
        is_brazilian = any(word in competition.lower() for word in 
                          ['brasil', 'brasileirão', 'série', 'serie', 'copa do brasil'])
        
        if is_brazilian:
            queries = [
                f'"{home_team}" x "{away_team}" escalação provável',
                f'{home_team} {away_team} desfalques lesões suspensos',
                f'provável escalação {home_team} {away_team} ge globo',
            ]
            search_region = 'br-pt'
        else:
            queries = [
                f'"{home_team}" vs "{away_team}" predicted lineup team news',
                f'{home_team} {away_team} injuries suspensions',
                f'{home_team} vs {away_team} preview starting XI',
            ]
            search_region = 'wt-wt'
        
        unique_links = set()
        articles_data = []
        home_norm, away_norm = self._normalize(home_team), self._normalize(away_team)
        candidates = []

        try:
            ddgs = DDGS()
        except Exception as e:
            print(f"⚠️ Error initializing DuckDuckGo: {e}")
            return "Error accessing search service. AI will use statistics only."

        for q in queries:
            try:
                print(f"   🔎 Searching: '{q[:60]}...'")
                results = self._search_with_fallback(ddgs, q, search_region)
                
                if not results:
                    continue

                for res in results:
                    link = res.get('href', '') or res.get('url', '')
                    title = res.get('title', '')
                    snippet = res.get('body', '')
                    
                    if not link or not title or link in unique_links:
                        continue
                    unique_links.add(link)
                    
                    full_check = self._normalize(title + " " + link + " " + snippet)
                    
                    # Validate content
                    if any(bad in full_check for bad in self.BLOCKLIST):
                        continue
                    if is_brazilian and home_norm not in full_check and away_norm not in full_check:
                        continue
                    if "ge.globo.com" in link and "/noticia/" not in link and "/jogo/" not in link:
                        continue
                    
                    prelim_score = self._calculate_relevance_score(title + " " + snippet)
                    if self._is_trusted_source(link, is_brazilian):
                        prelim_score += 5
                    
                    # Adiciona à lista de candidatos para processamento paralelo
                    candidates.append({'link': link, 'title': title, 'prelim_score': prelim_score})
                            
            except Exception as e:
                print(f"   ⚠️ Search error: {e}")

        # Processamento Paralelo dos Artigos
        if candidates:
            # Limita a 5 candidatos mais promissores para não sobrecarregar
            candidates.sort(key=lambda x: x['prelim_score'], reverse=True)
            top_candidates = candidates[:6]
            
            print(f"   🚀 Scraping {len(top_candidates)} articles in parallel...")
            
            with ThreadPoolExecutor(max_workers=4) as executor:
                future_to_article = {executor.submit(self._scrape_page_content, c['link'], [home_team, away_team]): c for c in top_candidates}
                
                for future in as_completed(future_to_article):
                    c = future_to_article[future]
                    try:
                        content, lineup_info = future.result()
                        if content and len(content) > 250:
                            final_score = self._calculate_relevance_score(content)
                            if self._is_trusted_source(c['link'], is_brazilian): final_score += 5
                            
                            if final_score >= 3:
                                articles_data.append({'title': c['title'], 'link': c['link'], 'content': content, 'score': final_score})
                                print(f"      ✅ Extracted: {c['title'][:30]}... (Score: {final_score})")
                    except Exception as exc:
                        print(f"      ⚠️ Error processing {c['link']}: {exc}")

        if not articles_data:
            return "No detailed news found. AI will use statistics only."
        
        # Sort by relevance and build context
        articles_data.sort(key=lambda x: x['score'], reverse=True)
        
        context_text = ""
        for i, article in enumerate(articles_data[:3], 1):
            context_text += f"\n=== ARTICLE #{i} (Relevance: {article['score']}) ===\n"
            context_text += f"TITLE: {article['title']}\nSOURCE: {article['link']}\n{article['content']}\n"
            context_text += "=" * 50 + "\n"
            
        print(f"✅ {min(3, len(articles_data))} articles extracted.")
        return context_text
