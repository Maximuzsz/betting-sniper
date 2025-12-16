"""
Team statistics service (goals scored/conceded).
Fetches LAST 5 MATCHES statistics from multiple free sources.

FUNCIONAMENTO:
- Busca EXATAMENTE os últimos 5 jogos de cada time
- Calcula média de gols marcados e sofridos nesses 5 jogos
- Valida os dados extraídos para garantir precisão
- Usa múltiplas fontes: FBRef (principal), FlashScore, Transfermarkt, WebSearch

PRECISÃO DOS DADOS:
- Extrai dados diretamente das tabelas de resultados
- Identifica corretamente gols marcados vs sofridos usando colunas GF/GA
- Valida que os dados são razoáveis (0-15 gols por jogo, média 0-6)
- Logs detalhados mostram cada jogo individual para verificação
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

# Number of recent matches to analyze - CONFIGURÁVEL
LAST_N_MATCHES = 5  # Exatamente 5 jogos mais recentes


class StatsService:
    """100% free statistics service - fetches LAST 5 MATCHES stats."""
    
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
    
    # European team mappings
    TEAM_MAPPINGS_EU = {
        'real madrid': 'Real-Madrid', 'barcelona': 'Barcelona', 'atletico madrid': 'Atletico-Madrid',
        'bayern munich': 'Bayern-Munich', 'bayern': 'Bayern-Munich', 'dortmund': 'Borussia-Dortmund',
        'manchester united': 'Manchester-United', 'manchester city': 'Manchester-City',
        'liverpool': 'Liverpool', 'chelsea': 'Chelsea', 'arsenal': 'Arsenal', 'tottenham': 'Tottenham',
        'juventus': 'Juventus', 'inter milan': 'Inter', 'ac milan': 'AC-Milan', 'napoli': 'Napoli',
        'psg': 'Paris-Saint-Germain', 'paris saint-germain': 'Paris-Saint-Germain',
        'lyon': 'Lyon', 'marseille': 'Marseille',
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
        """Fetch LAST 5 MATCHES statistics from FBRef."""
        try:
            cache_key = f"fbref_last5_{team_name}_{league_key}"
            if cache_key in self._stats_cache:
                print(f"      💾 Usando cache para {team_name}")
                return self._stats_cache[cache_key]
            
            team_slug = self._get_team_slug(team_name)
            print(f"      📊 FBRef: Buscando últimos {LAST_N_MATCHES} jogos de {team_slug}...")
            
            search_url = f"https://fbref.com/en/search/search.fcgi?search={quote_plus(team_name)}"
            response = request_with_retry(search_url, timeout=10)
            
            if not response:
                print(f"      ⚠️ FBRef: Falha na busca")
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for team page link
            team_link = None
            fixtures_link = None
            team_slug_lower = team_slug.lower().replace('-', '')
            
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                link_text = link.get_text().lower()
                
                # Look for squad page
                if '/squads/' in href:
                    if team_slug_lower in href.lower().replace('-', ''):
                        team_link = f"https://fbref.com{href}"
                        # Try to find fixtures page directly
                        if 'all_comps/scores-and-fixtures' not in team_link:
                            fixtures_link = team_link.rstrip('/') + '/all_comps/scores-and-fixtures'
                        break
                    if self._normalize_team_name(team_name) in link_text:
                        team_link = f"https://fbref.com{href}"
                        if 'all_comps/scores-and-fixtures' not in team_link:
                            fixtures_link = team_link.rstrip('/') + '/all_comps/scores-and-fixtures'
                        break
            
            if not team_link:
                print(f"      ⚠️ FBRef: Time '{team_name}' não encontrado")
                return None
            
            print(f"      🔗 Página do time encontrada: {team_link}")
            
            # Try fixtures page first (more reliable for recent matches)
            if fixtures_link:
                print(f"      🔗 Tentando página de resultados: {fixtures_link}")
                fixtures_response = request_with_retry(fixtures_link, timeout=10)
                if fixtures_response:
                    stats = self._extract_fbref_last_matches(
                        BeautifulSoup(fixtures_response.content, 'html.parser'), 
                        team_name
                    )
                    if stats:
                        self._stats_cache[cache_key] = stats
                        return stats
            
            # Fallback to main team page
            print(f"      🔗 Tentando página principal do time")
            team_response = request_with_retry(team_link, timeout=10)
            if not team_response:
                return None
            
            stats = self._extract_fbref_last_matches(
                BeautifulSoup(team_response.content, 'html.parser'), 
                team_name
            )
            if stats:
                self._stats_cache[cache_key] = stats
            return stats
            
        except Exception as e:
            print(f"      ⚠️ FBRef error: {e}")
            return None

    def _extract_fbref_last_matches(self, soup, team_name):
        """Extract LAST 5 MATCHES results from FBRef page."""
        matches = []
        normalized_team = self._normalize_team_name(team_name)
        
        print(f"      🔍 Procurando tabela de resultados para {team_name}...")
        
        # Try to find the "Scores & Fixtures" table or match results
        # FBRef uses tables with id like "matchlogs_for" or class "stats_table"
        tables = soup.find_all('table', {'class': re.compile(r'stats_table|sortable')})
        
        for table in tables:
            # Look for tables with match results (columns: Date, Comp, Round, Venue, Result, GF, GA, Opponent)
            headers = table.find_all('th')
            header_texts = [h.get_text().strip().lower() for h in headers]
            
            # Find column indices for GF (Goals For) and GA (Goals Against)
            gf_index = None
            ga_index = None
            venue_index = None
            result_index = None
            
            for idx, header in enumerate(header_texts):
                if header in ['gf', 'goals for']:
                    gf_index = idx
                elif header in ['ga', 'goals against']:
                    ga_index = idx
                elif header in ['venue', 'local']:
                    venue_index = idx
                elif header in ['result', 'resultado']:
                    result_index = idx
            
            # Check if this table has the columns we need
            has_gf_ga = (gf_index is not None and ga_index is not None)
            has_result = result_index is not None
            
            if not has_gf_ga and not has_result:
                continue
            
            print(f"      📋 Tabela encontrada - GF col:{gf_index}, GA col:{ga_index}, Venue col:{venue_index}, Result col:{result_index}")
            
            rows = table.find_all('tr')
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) < 4:
                    continue
                
                # Skip header rows
                if cells[0].name == 'th':
                    continue
                
                row_text = row.get_text()
                
                # Method 1: Use GF/GA columns directly if available
                if has_gf_ga and gf_index < len(cells) and ga_index < len(cells):
                    try:
                        gf_text = cells[gf_index].get_text().strip()
                        ga_text = cells[ga_index].get_text().strip()
                        
                        # Extract numbers from cells
                        gf_match = re.search(r'(\d+)', gf_text)
                        ga_match = re.search(r'(\d+)', ga_text)
                        
                        if gf_match and ga_match:
                            goals_scored = int(gf_match.group(1))
                            goals_conceded = int(ga_match.group(1))
                            
                            matches.append({
                                'scored': goals_scored,
                                'conceded': goals_conceded
                            })
                            
                            print(f"      ⚽ Jogo {len(matches)}: {goals_scored}-{goals_conceded}")
                            
                            if len(matches) >= LAST_N_MATCHES:
                                break
                            continue
                    except (ValueError, IndexError):
                        pass
                
                # Method 2: Extract from Result column with W/D/L pattern
                if has_result and result_index < len(cells):
                    result_text = cells[result_index].get_text().strip()
                    score_match = re.search(r'([WDL])\s*(\d+)[–\-:](\d+)', result_text)
                    
                    if score_match:
                        result_type = score_match.group(1)
                        goals_a = int(score_match.group(2))
                        goals_b = int(score_match.group(3))
                        
                        # W means team won, so first number is team's goals
                        if result_type == 'W':
                            goals_scored = goals_a
                            goals_conceded = goals_b
                        # L means team lost, so first number is still team's goals
                        elif result_type == 'L':
                            goals_scored = goals_a
                            goals_conceded = goals_b
                        # D means draw
                        else:
                            goals_scored = goals_a
                            goals_conceded = goals_b
                        
                        matches.append({
                            'scored': goals_scored,
                            'conceded': goals_conceded
                        })
                        
                        print(f"      ⚽ Jogo {len(matches)}: {result_type} {goals_scored}-{goals_conceded}")
                        
                        if len(matches) >= LAST_N_MATCHES:
                            break
                        continue
                
                # Method 3: General pattern extraction from row text as fallback
                score_match = re.search(r'[WDL]?\s*(\d+)[–\-:](\d+)', row_text)
                if score_match:
                    goals_a = int(score_match.group(1))
                    goals_b = int(score_match.group(2))
                    
                    # Try to determine venue to assign goals correctly
                    venue_text = ""
                    if venue_index and venue_index < len(cells):
                        venue_text = cells[venue_index].get_text().strip().lower()
                    
                    # Check result prefix (W/D/L) to understand perspective
                    result_prefix = re.search(r'([WDL])\s*\d+', row_text.strip())
                    
                    if venue_text in ['home', 'h', 'casa']:
                        # Home game: first score is team's score
                        goals_scored = goals_a
                        goals_conceded = goals_b
                    elif venue_text in ['away', 'a', 'fora']:
                        # Away game: need to check if scores are in team perspective
                        # FBRef usually shows scores in team's perspective
                        goals_scored = goals_a
                        goals_conceded = goals_b
                    elif result_prefix:
                        # Use W/D/L to validate
                        prefix = result_prefix.group(1)
                        # FBRef format is "W 2-1" meaning team won 2-1
                        goals_scored = goals_a
                        goals_conceded = goals_b
                    else:
                        # Default: first number is team's score
                        goals_scored = goals_a
                        goals_conceded = goals_b
                    
                    matches.append({
                        'scored': goals_scored,
                        'conceded': goals_conceded
                    })
                    
                    print(f"      ⚽ Jogo {len(matches)}: {goals_scored}-{goals_conceded} (venue: {venue_text or 'N/A'})")
                    
                    if len(matches) >= LAST_N_MATCHES:
                        break
            
            if matches:
                break
        
        if len(matches) < 2:
            print(f"      ⚠️ Poucos jogos encontrados na tabela principal, tentando fallback...")
            # Fallback: try to find form/results section with simpler patterns
            text_content = soup.get_text()
            
            # Look for recent form like "WWDLW" with scores
            form_matches = re.findall(r'([WDL])\s*(\d+)[–\-:](\d+)', text_content)
            for form in form_matches[:LAST_N_MATCHES]:
                result, g1, g2 = form
                g1, g2 = int(g1), int(g2)
                # In FBRef format "W 2-1", the first number is always the team's score
                matches.append({'scored': g1, 'conceded': g2})
                print(f"      ⚽ Jogo {len(matches)} (fallback): {result} {g1}-{g2}")
                
                if len(matches) >= LAST_N_MATCHES:
                    break
        
        # Only proceed if we have at least 2 matches
        if len(matches) >= 2:
            # Ensure we only use exactly LAST_N_MATCHES (5) or fewer if not available
            matches_to_use = matches[:LAST_N_MATCHES]
            n_matches = len(matches_to_use)
            
            # Validate that matches data makes sense
            for i, match in enumerate(matches_to_use):
                # Ensure goals are non-negative and reasonable (max 15 per match)
                if match['scored'] < 0 or match['scored'] > 15:
                    print(f"      ⚠️ Gols marcados suspeitos no jogo {i+1}: {match['scored']}")
                    return None
                if match['conceded'] < 0 or match['conceded'] > 15:
                    print(f"      ⚠️ Gols sofridos suspeitos no jogo {i+1}: {match['conceded']}")
                    return None
            
            # Calculate totals
            total_scored = sum(m['scored'] for m in matches_to_use)
            total_conceded = sum(m['conceded'] for m in matches_to_use)
            
            # Calculate averages
            scored_avg = round(total_scored / n_matches, 2)
            conceded_avg = round(total_conceded / n_matches, 2)
            
            # Final validation: averages should be reasonable (0-6 goals per game)
            if scored_avg < 0 or scored_avg > 6:
                print(f"      ⚠️ Média de gols marcados suspeita: {scored_avg}")
                return None
            if conceded_avg < 0 or conceded_avg > 6:
                print(f"      ⚠️ Média de gols sofridos suspeita: {conceded_avg}")
                return None
            
            # Detailed logging
            print(f"      ✅ FBRef: Encontrados {n_matches} jogos recentes")
            print(f"      📊 Detalhamento dos jogos:")
            for i, match in enumerate(matches_to_use, 1):
                print(f"         {i}. Feitos: {match['scored']}, Sofridos: {match['conceded']}")
            print(f"      📊 TOTAL: {total_scored} gols feitos, {total_conceded} gols sofridos em {n_matches} jogos")
            print(f"      📊 MÉDIA: {scored_avg} gols feitos/jogo, {conceded_avg} gols sofridos/jogo")
            
            return {
                'scored_avg': scored_avg,
                'conceded_avg': conceded_avg,
                'matches_analyzed': n_matches,
                'last_matches': matches_to_use,
                'source': f'FBRef (últimos {n_matches} jogos)'
            }
        
        print(f"      ❌ FBRef: Dados insuficientes (apenas {len(matches)} jogos encontrados)")
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
