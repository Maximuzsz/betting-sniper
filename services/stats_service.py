"""
Team statistics service (goals scored/conceded).
Fetches LAST 5 MATCHES statistics asynchronously.

MELHORIAS V3:
- Mapa Manual expandido para times Europeus (Bundesliga, Premier League, etc).
- Scraping do OGol mais robusto para listas de busca.
- Limpeza automática de sufixos (FC, AC, SC).
"""
import re
import requests
import unicodedata
import time
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# Cache em memória para evitar requests repetidos na mesma sessão
STATS_CACHE = {}

# Configurações
LAST_N_MATCHES = 5
MAX_WORKERS = 3 

class StatsService:
    def __init__(self):
        # Mapeamento expandido para cobrir apelidos e nomes curtos vs nomes de busca
        self.manual_map = {
            # Brasil
            'galo': 'Atlético Mineiro', 'urubu': 'Flamengo', 'mengo': 'Flamengo',
            'vasco': 'Vasco da Gama', 'athletico': 'Athletico Paranaense', 'cap': 'Athletico Paranaense',
            'inter': 'Internacional', 'gremio': 'Grêmio', 'america-mg': 'América Mineiro',
            'sport': 'Sport Recife', 'ceara': 'Ceará', 'vitoria': 'Vitória', 'goias': 'Goiás',
            
            # Alemanha (Bundesliga)
            'dortmund': 'Borussia Dortmund', 'bvb': 'Borussia Dortmund',
            'bayern': 'Bayern München', 'munich': 'Bayern München', 'munchen': 'Bayern München',
            'frankfurt': 'Eintracht Frankfurt', 'eintracht': 'Eintracht Frankfurt',
            'leipzig': 'RB Leipzig', 'rbl': 'RB Leipzig',
            'leverkusen': 'Bayer Leverkusen', 'bayer': 'Bayer Leverkusen',
            'stuttgart': 'VfB Stuttgart', 'wolfsburg': 'VfL Wolfsburg',
            'gladbach': 'Borussia Mönchengladbach', 'monchengladbach': 'Borussia Mönchengladbach',
            
            # Inglaterra (Premier League)
            'city': 'Manchester City', 'man city': 'Manchester City',
            'united': 'Manchester United', 'man utd': 'Manchester United',
            'tottenham': 'Tottenham Hotspur', 'spurs': 'Tottenham Hotspur',
            'wolves': 'Wolverhampton Wanderers', 'leicester': 'Leicester City',
            'newcastle': 'Newcastle United', 'west ham': 'West Ham United',
            
            # Espanha (La Liga)
            'real': 'Real Madrid', 'barca': 'Barcelona', 'atletico': 'Atlético Madrid',
            'atleti': 'Atlético Madrid', 'betis': 'Real Betis', 'sociedad': 'Real Sociedad',
            
            # Itália (Serie A)
            'inter milan': 'Inter de Milão', 'internazionale': 'Inter de Milão',
            'ac milan': 'Milan', 'juve': 'Juventus', 
            
            # França (Ligue 1)
            'psg': 'Paris Saint-Germain', 'paris': 'Paris Saint-Germain',
            'marseille': 'Olympique de Marseille', 'lyon': 'Olympique Lyonnais'
        }

    # --- UTILITÁRIOS ---
    def _request(self, url, retries=2):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7'
        }
        for i in range(retries + 1):
            try:
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code == 200: return r
            except:
                time.sleep(1)
        return None

    def _normalize(self, text):
        if not text: return ""
        return unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8').lower().strip()

    def _clean_team_name(self, name):
        """Limpa o nome para busca, resolvendo apelidos e removendo sufixos."""
        norm = self._normalize(name)
        
        # 1. Verifica mapa manual (busca exata ou parcial)
        for k, v in self.manual_map.items():
            # Verifica se a chave está contida no nome (ex: "dortmund" em "borussia dortmund")
            if k == norm or (len(k) > 3 and k in norm): 
                return v
        
        # 2. Remove sufixos comuns que atrapalham a busca (FC, EC, SC)
        clean = re.sub(r'\b(fc|ec|sc|ac|club|clube|sport)\b', '', norm).strip()
        if clean: return clean.title()
        
        return name

    # --- FONTE 1: OGOL (PRINCIPAL) ---
    def _fetch_ogol(self, team_name):
        """
        Busca estatísticas no OGol.com.br.
        """
        try:
            # 1. Busca o time
            clean_name = self._clean_team_name(team_name)
            # print(f"      🔎 OGol Search: {clean_name}")
            
            search_url = f"https://www.ogol.com.br/pesquisa?search_txt={quote_plus(clean_name)}&search_type=teams"
            resp = self._request(search_url)
            
            if not resp: return None
            
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            team_link = None
            
            # Verifica redirecionamento direto
            if "/equipe/" in resp.url:
                team_link = resp.url
            else:
                # Procura na lista de resultados (estrutura pode variar, busca genérica por links de equipe)
                # Tenta container de resultados ou tabela
                for a in soup.find_all('a', href=True):
                    if "/equipe/" in a['href']:
                        # Validação simples: o nome do link parece com o time buscado?
                        link_text = self._normalize(a.get_text())
                        search_norm = self._normalize(clean_name)
                        if search_norm in link_text or link_text in search_norm:
                            team_link = f"https://www.ogol.com.br{a['href']}"
                            break
            
            if not team_link: 
                # print("      ⚠️ OGol: Link do time não encontrado na busca.")
                return None

            # 2. Vai para a página do time
            resp_team = self._request(team_link)
            if not resp_team: return None
            
            soup_team = BeautifulSoup(resp_team.content, 'html.parser')
            
            # 3. Extrai Resultados
            matches_data = []
            
            # Procura qualquer tabela que tenha formato de placar
            tables = soup_team.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) < 3: continue
                    
                    row_text = row.get_text().strip()
                    
                    # Regex para placar (ex: 2-1, 0-0)
                    score_match = re.search(r'(\d+)-(\d+)', row_text)
                    
                    if score_match:
                        # Tenta identificar mandante e visitante na linha
                        # Estrutura comum: Data | Casa | Res | Fora
                        # Mas às vezes é diferente. Vamos tentar achar o nome do time na linha.
                        
                        links = row.find_all('a')
                        link_texts = [self._normalize(l.get_text()) for l in links]
                        row_norm = self._normalize(row_text)
                        
                        g1 = int(score_match.group(1))
                        g2 = int(score_match.group(2))
                        
                        # Identifica a posição do time na string
                        # Se o nome do time aparece ANTES do placar, é mandante. DEPOIS, visitante.
                        # Simplificação: OGol geralmente põe Casa na esquerda, Fora na direita.
                        
                        # Vamos usar a posição das células
                        try:
                            # Procura células com texto
                            valid_cells = [c for c in cells if c.get_text().strip()]
                            # Geralmente o placar está no meio
                            
                            # Heurística: Se a célula do placar está no índice X
                            # O time da casa está em X-1 e visitante em X+1
                            score_cell_idx = -1
                            for idx, cell in enumerate(valid_cells):
                                if score_match.group(0) in cell.get_text():
                                    score_cell_idx = idx
                                    break
                            
                            if score_cell_idx > 0 and score_cell_idx < len(valid_cells) - 1:
                                home_name = self._normalize(valid_cells[score_cell_idx-1].get_text())
                                away_name = self._normalize(valid_cells[score_cell_idx+1].get_text())
                                target_name = self._normalize(clean_name)
                                
                                # Verifica quem é o nosso time
                                is_home = target_name in home_name or home_name in target_name
                                is_away = target_name in away_name or away_name in target_name
                                
                                if is_home:
                                    matches_data.append({'scored': g1, 'conceded': g2})
                                elif is_away:
                                    matches_data.append({'scored': g2, 'conceded': g1})
                        except:
                            continue
                        
                        if len(matches_data) >= LAST_N_MATCHES:
                            break
                
                if len(matches_data) >= LAST_N_MATCHES:
                    break

            if not matches_data: return None
            
            matches_to_use = matches_data[:LAST_N_MATCHES]
            scored_avg = sum(m['scored'] for m in matches_to_use) / len(matches_to_use)
            conceded_avg = sum(m['conceded'] for m in matches_to_use) / len(matches_to_use)
            
            return {
                'scored_avg': round(scored_avg, 2),
                'conceded_avg': round(conceded_avg, 2),
                'source': 'OGol',
                'matches': len(matches_to_use)
            }

        except Exception as e:
            # print(f"Erro OGol: {e}")
            return None

    # --- FONTE 2: FBREF (BACKUP) ---
    def _fetch_fbref(self, team_name):
        try:
            clean_name = self._clean_team_name(team_name)
            search_url = f"https://fbref.com/en/search/search.fcgi?search={quote_plus(clean_name)}"
            resp = self._request(search_url)
            if not resp: return None

            soup = BeautifulSoup(resp.content, 'html.parser')
            team_link = None
            
            if "squads" in resp.url:
                team_link = resp.url
            else:
                for a in soup.find_all('a', href=True):
                    if '/squads/' in a['href'] and self._normalize(clean_name) in self._normalize(a.get_text()):
                        team_link = f"https://fbref.com{a['href']}"
                        break
            
            if not team_link: return None
            
            if "scores-and-fixtures" not in team_link:
                fixtures_link = team_link.rstrip('/') + "/matchlogs/all_comps/schedule"
            else:
                fixtures_link = team_link

            resp_fix = self._request(fixtures_link)
            if not resp_fix: return None
            
            soup_fix = BeautifulSoup(resp_fix.content, 'html.parser')
            matches = []
            
            tables = soup_fix.find_all('table', {'class': re.compile(r'stats_table')})
            for table in tables:
                for row in table.find_all('tr'):
                    gf_cell = row.find('td', {'data-stat': 'goals_for'})
                    ga_cell = row.find('td', {'data-stat': 'goals_against'})
                    if gf_cell and ga_cell and gf_cell.get_text().strip():
                        try:
                            matches.append({
                                'scored': int(gf_cell.get_text().strip()),
                                'conceded': int(ga_cell.get_text().strip())
                            })
                        except: continue
            
            if not matches: return None
            
            recent = matches[-LAST_N_MATCHES:]
            return {
                'scored_avg': round(sum(m['scored'] for m in recent) / len(recent), 2),
                'conceded_avg': round(sum(m['conceded'] for m in recent) / len(recent), 2),
                'source': 'FBRef',
                'matches': len(recent)
            }
        except: return None

    # --- ORQUESTRADOR ---
    def get_team_stats(self, team_name, league_key, league_name="futebol"):
        cache_key = f"{self._normalize(team_name)}_{league_key}"
        if cache_key in STATS_CACHE:
            print(f"   💾 Cache hit: {team_name}")
            return STATS_CACHE[cache_key]

        print(f"   📊 Buscando stats para {team_name}...")
        
        # Tenta OGol Primeiro (Mais rápido/estável)
        data = self._fetch_ogol(team_name)
        
        # Se falhar, tenta FBRef
        if not data:
            data = self._fetch_fbref(team_name)
            
        if data:
            STATS_CACHE[cache_key] = data
            return data

        print(f"   ⚠️ Stats não encontrados. Usando padrão.")
        return {'scored_avg': 1.35, 'conceded_avg': 1.25, 'source': 'Default'}