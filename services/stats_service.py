"""
Team statistics service (goals scored/conceded).
Uses multiple free sources: FBRef, FlashScore, Transfermarkt, web search.
"""
import re
import unicodedata
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from .http_utils import request_with_retry, get_cached, set_cached

# Try to import DuckDuckGo for fallback search
try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        DDGS_AVAILABLE = True
    except ImportError:
        DDGS_AVAILABLE = False
        DDGS = None


class StatsService:
    """100% free statistics service with multiple sources."""
    
    # Brazilian team name mappings for FBRef
    TEAM_MAPPINGS_BR = {
        'palmeiras': 'Palmeiras', 'flamengo': 'Flamengo',
        'atletico-mg': 'Atletico-Mineiro', 'atlético-mg': 'Atletico-Mineiro',
        'atlético mineiro': 'Atletico-Mineiro', 'atletico mineiro': 'Atletico-Mineiro',
        'botafogo': 'Botafogo-RJ', 'sao paulo': 'Sao-Paulo', 'são paulo': 'Sao-Paulo',
        'internacional': 'Internacional', 'inter': 'Internacional',
        'fluminense': 'Fluminense', 'corinthians': 'Corinthians', 'fortaleza': 'Fortaleza',
        'gremio': 'Gremio', 'grêmio': 'Gremio', 'cruzeiro': 'Cruzeiro',
        'athletico-pr': 'Athletico-Paranaense', 'athletico paranaense': 'Athletico-Paranaense',
        'bahia': 'Bahia', 'vasco': 'Vasco-da-Gama', 'vasco da gama': 'Vasco-da-Gama',
        'santos': 'Santos', 'red bull bragantino': 'Red-Bull-Bragantino', 'bragantino': 'Red-Bull-Bragantino',
        'juventude': 'Juventude', 'cuiaba': 'Cuiaba', 'cuiabá': 'Cuiaba',
        'vitoria': 'Vitoria', 'vitória': 'Vitoria', 'criciuma': 'Criciuma', 'criciúma': 'Criciuma',
        'atletico-go': 'Atletico-Goianiense', 'atlético goianiense': 'Atletico-Goianiense',
        'goias': 'Goias', 'goiás': 'Goias', 'america-mg': 'America-MG',
        'coritiba': 'Coritiba', 'sport': 'Sport-Recife', 'ceara': 'Ceara', 'ceará': 'Ceara'
    }
    
    def __init__(self, api_key=None, api_host=None):
        self._stats_cache = {}

    @staticmethod
    def _normalize_team_name(team_name):
        """Normalize team name for search."""
        name = unicodedata.normalize('NFKD', team_name).encode('ASCII', 'ignore').decode('utf-8')
        return name.lower().strip()

    def _get_team_slug(self, team_name):
        """Convert team name to FBRef slug."""
        normalized = self._normalize_team_name(team_name)
        
        if normalized in self.TEAM_MAPPINGS_BR:
            return self.TEAM_MAPPINGS_BR[normalized]
        
        for key, value in self.TEAM_MAPPINGS_BR.items():
            if key in normalized or normalized in key:
                return value
        
        return team_name.replace(' ', '-').replace('.', '').title()

    @staticmethod
    def _extract_goal_avg(text, patterns):
        """Extract goal average using regex patterns list."""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    val = float(match.group(1).replace(',', '.'))
                    if 0.3 <= val <= 4.0:
                        return val
                except:
                    continue
        return None

    def _scrape_fbref_stats(self, team_name, league_key):
        """Fetch statistics from FBRef."""
        try:
            cache_key = f"fbref_{team_name}_{league_key}"
            if cache_key in self._stats_cache:
                return self._stats_cache[cache_key]
            
            team_slug = self._get_team_slug(team_name)
            print(f"      📊 FBRef: Searching {team_slug}...")
            
            search_url = f"https://fbref.com/en/search/search.fcgi?search={quote_plus(team_name)}"
            response = request_with_retry(search_url, timeout=10)
            
            if not response:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for team page link
            team_link = None
            team_slug_lower = team_slug.lower().replace('-', '')
            
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                if '/squads/' in href:
                    if team_slug_lower in href.lower().replace('-', ''):
                        team_link = f"https://fbref.com{href}"
                        break
                    text = link.get_text().lower()
                    if self._normalize_team_name(team_name) in text:
                        team_link = f"https://fbref.com{href}"
                        break
            
            if not team_link:
                print(f"      ⚠️ FBRef: Team not found")
                return None
            
            team_response = request_with_retry(team_link, timeout=10)
            if not team_response:
                return None
            
            stats = self._extract_fbref_stats(BeautifulSoup(team_response.content, 'html.parser'))
            if stats:
                self._stats_cache[cache_key] = stats
            return stats
            
        except Exception as e:
            print(f"      ⚠️ FBRef error: {e}")
            return None

    def _extract_fbref_stats(self, soup):
        """Extract statistics from FBRef tables."""
        scored_patterns = [
            r'(\d+\.\d+)\s*(?:GF|goals?\s*for|gols?\s*feitos)',
            r'(?:GF|Goals\s*For)[:\s]+\d+\s*\((\d+\.\d+)',
            r'(?:goals?\s*scored|gols?\s*marcados)[:\s]*(\d+\.\d+)',
        ]
        conceded_patterns = [
            r'(\d+\.\d+)\s*(?:GA|goals?\s*against|gols?\s*sofridos)',
            r'(?:GA|Goals\s*Against)[:\s]+\d+\s*\((\d+\.\d+)',
            r'(?:goals?\s*conceded|gols?\s*sofridos)[:\s]*(\d+\.\d+)',
        ]
        
        page_text = soup.get_text()
        scored_avg = self._extract_goal_avg(page_text, scored_patterns)
        conceded_avg = self._extract_goal_avg(page_text, conceded_patterns)
        
        if scored_avg and conceded_avg:
            return {'scored_avg': round(scored_avg, 2), 'conceded_avg': round(conceded_avg, 2), 'source': 'FBRef'}
        return None

    def _scrape_flashscore_stats(self, team_name, league_name):
        """Fetch statistics from FlashScore."""
        try:
            cache_key = f"flashscore_{team_name}"
            if cache_key in self._stats_cache:
                return self._stats_cache[cache_key]
            
            print(f"      📊 FlashScore: Searching {team_name}...")
            
            team_slug = self._normalize_team_name(team_name).replace(' ', '-')
            url = f"https://www.flashscore.com/team/{team_slug}/"
            response = request_with_retry(url, timeout=10)
            
            if not response or response.status_code != 200:
                search_url = f"https://www.flashscore.com/search/?q={quote_plus(team_name)}"
                response = request_with_retry(search_url, timeout=10)
            
            if not response:
                return None
            
            page_text = BeautifulSoup(response.content, 'html.parser').get_text()
            
            scored_match = re.search(r'(?:goals?\s*(?:scored|for|per\s*match))[:\s]*(\d+\.?\d*)', page_text, re.IGNORECASE)
            conceded_match = re.search(r'(?:goals?\s*(?:conceded|against))[:\s]*(\d+\.?\d*)', page_text, re.IGNORECASE)
            
            scored_avg = float(scored_match.group(1)) if scored_match and 0.3 <= float(scored_match.group(1)) <= 4.0 else None
            conceded_avg = float(conceded_match.group(1)) if conceded_match and 0.3 <= float(conceded_match.group(1)) <= 4.0 else None
            
            if scored_avg and conceded_avg:
                result = {'scored_avg': round(scored_avg, 2), 'conceded_avg': round(conceded_avg, 2), 'source': 'FlashScore'}
                self._stats_cache[cache_key] = result
                return result
            
            return None
        except Exception as e:
            print(f"      ⚠️ FlashScore error: {e}")
            return None

    def _scrape_transfermarkt_stats(self, team_name, league_name):
        """Fetch statistics from Transfermarkt."""
        try:
            print(f"      📊 Transfermarkt: Searching {team_name}...")
            
            search_url = f"https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query={quote_plus(team_name)}"
            response = request_with_retry(search_url, timeout=10)
            
            if not response:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for team link
            team_link = None
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                if '/verein/' in href or team_name.lower() in link.get_text().lower():
                    team_link = href if href.startswith('http') else f"https://www.transfermarkt.com{href}"
                    break
            
            if not team_link:
                return None
            
            team_response = request_with_retry(team_link, timeout=10)
            if not team_response:
                return None
            
            page_text = BeautifulSoup(team_response.content, 'html.parser').get_text()
            
            scored_patterns = [
                r'(?:goals?\s*(?:scored|for)|gols?\s*(?:feitos|marcados))[:\s]*(?:Ø\s*)?(\d+\.?\d*)',
                r'Ø\s*(\d+\.?\d*)\s*(?:goals?\s*(?:scored|for)|gols)',
            ]
            conceded_patterns = [
                r'(?:goals?\s*(?:conceded|against)|gols?\s*sofridos)[:\s]*(?:Ø\s*)?(\d+\.?\d*)',
                r'Ø\s*(\d+\.?\d*)\s*(?:goals?\s*(?:conceded|against))',
            ]
            
            scored_avg = self._extract_goal_avg(page_text, scored_patterns)
            conceded_avg = self._extract_goal_avg(page_text, conceded_patterns)
            
            if scored_avg and conceded_avg:
                return {'scored_avg': round(scored_avg, 2), 'conceded_avg': round(conceded_avg, 2), 'source': 'Transfermarkt'}
            return None
            
        except Exception as e:
            print(f"      ⚠️ Transfermarkt error: {e}")
            return None

    def _get_stats_from_search(self, team_name, league_name):
        """Fetch statistics via DuckDuckGo (fallback)."""
        if not DDGS_AVAILABLE:
            return None

        try:
            print(f"      📊 Web search: {team_name}...")
            
            is_brazilian = any(word in league_name.lower() for word in ['brasil', 'brasileirão', 'série'])
            
            queries = [
                f"{team_name} estatísticas gols feitos sofridos por jogo 2024",
                f"{team_name} goals scored conceded per game statistics 2024",
            ] if is_brazilian else [
                f"{team_name} goals scored conceded per game statistics 2024",
                f"{team_name} average goals for against stats",
            ]
            
            ddgs = DDGS()
            all_context = ""
            
            for query in queries[:2]:
                try:
                    results = list(ddgs.text(query, region='br-pt' if is_brazilian else 'wt-wt', max_results=8))
                    for r in results:
                        body = r.get('body', '') or r.get('snippet', '')
                        title = r.get('title', '')
                        all_context += " " + body + " " + title
                except:
                    continue
            
            if len(all_context) < 100:
                return None
            
            scored_patterns = [
                r'(?:goals?\s*(?:scored|for|per\s*(?:game|match))|gols?\s*(?:feitos|marcados|por\s*jogo))[:\s]*(\d+\.\d+)',
                r'(\d+\.\d+)\s*(?:goals?\s*(?:per\s*(?:game|match)|scored)|gols?\s*por\s*jogo)',
                r'(?:média|average)[:\s]*(\d+\.\d+)\s*(?:gols?|goals?)',
            ]
            conceded_patterns = [
                r'(?:goals?\s*(?:conceded|against|allowed)|gols?\s*(?:sofridos|levados))[:\s]*(\d+\.\d+)',
                r'(\d+\.\d+)\s*(?:goals?\s*(?:conceded|against)|gols?\s*sofridos)',
            ]
            
            scored_avg = self._extract_goal_avg(all_context, scored_patterns)
            conceded_avg = self._extract_goal_avg(all_context, conceded_patterns)
            
            # Try to find second value if only one was found
            if (scored_avg and not conceded_avg) or (conceded_avg and not scored_avg):
                all_decimals = re.findall(r'(\d+\.\d+)', all_context)
                for dec in all_decimals:
                    try:
                        val = float(dec)
                        if 0.3 <= val <= 4.0:
                            if scored_avg and not conceded_avg and val != scored_avg:
                                conceded_avg = val
                                break
                            elif conceded_avg and not scored_avg and val != conceded_avg:
                                scored_avg = val
                                break
                    except:
                        continue
            
            if scored_avg and conceded_avg:
                return {'scored_avg': round(scored_avg, 2), 'conceded_avg': round(conceded_avg, 2), 'source': 'WebSearch'}
            return None
            
        except Exception as e:
            print(f"      ⚠️ Search error: {e}")
            return None

    def get_team_stats(self, team_name, league_key, league_name="futebol"):
        """
        Fetch goals scored and conceded statistics for a team.
        
        Args:
            team_name: Team name
            league_key: League key (e.g.: 'soccer_brazil_campeonato')
            league_name: League name for alternative search
        
        Returns:
            {'scored_avg': float, 'conceded_avg': float, 'source': str} or None
        """
        print(f"   🔍 Fetching statistics for {team_name}...")
        
        # Check cache first
        cache_key = f"stats_{self._normalize_team_name(team_name)}_{league_key}"
        cached = get_cached(cache_key, max_age=7200)
        if cached:
            print(f"   ✅ Statistics from cache ({cached.get('source', 'Cache')})")
            return cached
        
        # Try sources in order of reliability
        sources = [
            ('FBRef', lambda: self._scrape_fbref_stats(team_name, league_key)),
            ('FlashScore', lambda: self._scrape_flashscore_stats(team_name, league_name)),
            ('Transfermarkt', lambda: self._scrape_transfermarkt_stats(team_name, league_name)),
            ('WebSearch', lambda: self._get_stats_from_search(team_name, league_name)),
        ]
        
        for source_name, fetch_fn in sources:
            try:
                stats = fetch_fn()
                if stats:
                    print(f"   ✅ Statistics from {stats.get('source', source_name)}: "
                          f"Scored={stats['scored_avg']}, Conceded={stats['conceded_avg']}")
                    set_cached(cache_key, stats)
                    return stats
            except Exception as e:
                print(f"      ⚠️ {source_name} failed: {e}")
        
        print(f"   ⚠️ Could not fetch statistics for {team_name}")
        return None
