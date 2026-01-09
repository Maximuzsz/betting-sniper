"""
Scraping logic for Stats Service.
Handles OGol and FBRef specific parsing.
"""
import re
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from services.http_utils import request_with_retry
from services.stats_utils import clean_team_name, normalize_text, calculate_weighted_avg

LAST_N_MATCHES = 5

def fetch_ogol_stats(team_name):
    """
    Busca estatísticas no OGol.com.br.
    """
    try:
        # 1. Busca o time
        clean_name = clean_team_name(team_name)
        
        search_url = f"https://www.ogol.com.br/pesquisa?search_txt={quote_plus(clean_name)}&search_type=teams"
        resp = request_with_retry(search_url)
        
        if not resp: return None
        
        soup = BeautifulSoup(resp.content, 'html.parser')
        team_link = None
        
        # Verifica redirecionamento direto
        if "/equipe/" in resp.url:
            team_link = resp.url
        else:
            # Procura na lista de resultados
            for a in soup.find_all('a', href=True):
                if "/equipe/" in a['href']:
                    link_text = normalize_text(a.get_text())
                    search_norm = normalize_text(clean_name)
                    if search_norm in link_text or link_text in search_norm:
                        team_link = f"https://www.ogol.com.br{a['href']}"
                        break
        
        if not team_link: return None

        # 2. Vai para a página do time
        resp_team = request_with_retry(team_link)
        if not resp_team: return None
        
        soup_team = BeautifulSoup(resp_team.content, 'html.parser')
        
        # 3. Extrai Resultados
        matches_data = []
        tables = soup_team.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) < 3: continue
                
                row_text = row.get_text().strip()
                score_match = re.search(r'(\d+)-(\d+)', row_text)
                
                if score_match:
                    try:
                        # Procura células com texto
                        valid_cells = [c for c in cells if c.get_text().strip()]
                        
                        score_cell_idx = -1
                        for idx, cell in enumerate(valid_cells):
                            if score_match.group(0) in cell.get_text():
                                score_cell_idx = idx
                                break
                        
                        if score_cell_idx > 0 and score_cell_idx < len(valid_cells) - 1:
                            home_name = normalize_text(valid_cells[score_cell_idx-1].get_text())
                            away_name = normalize_text(valid_cells[score_cell_idx+1].get_text())
                            target_name = normalize_text(clean_name)
                            
                            g1 = int(score_match.group(1))
                            g2 = int(score_match.group(2))
                            
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
        scored_avg = calculate_weighted_avg([m['scored'] for m in matches_to_use])
        conceded_avg = calculate_weighted_avg([m['conceded'] for m in matches_to_use])
        
        return {
            'scored_avg': round(scored_avg, 2),
            'conceded_avg': round(conceded_avg, 2),
            'source': 'OGol',
            'matches': len(matches_to_use)
        }

    except Exception:
        return None

def fetch_fbref_stats(team_name):
    """
    Busca estatísticas no FBRef (Backup).
    """
    try:
        clean_name = clean_team_name(team_name)
        search_url = f"https://fbref.com/en/search/search.fcgi?search={quote_plus(clean_name)}"
        resp = request_with_retry(search_url)
        if not resp: return None

        soup = BeautifulSoup(resp.content, 'html.parser')
        team_link = None
        
        if "squads" in resp.url:
            team_link = resp.url
        else:
            for a in soup.find_all('a', href=True):
                if '/squads/' in a['href'] and normalize_text(clean_name) in normalize_text(a.get_text()):
                    team_link = f"https://fbref.com{a['href']}"
                    break
        
        if not team_link: return None
        
        fixtures_link = team_link if "scores-and-fixtures" in team_link else team_link.rstrip('/') + "/matchlogs/all_comps/schedule"
        resp_fix = request_with_retry(fixtures_link)
        if not resp_fix: return None
        
        soup_fix = BeautifulSoup(resp_fix.content, 'html.parser')
        matches = []
        
        for table in soup_fix.find_all('table', {'class': re.compile(r'stats_table')}):
            for row in table.find_all('tr'):
                gf = row.find('td', {'data-stat': 'goals_for'})
                ga = row.find('td', {'data-stat': 'goals_against'})
                if gf and ga and gf.get_text().strip():
                    try: matches.append({'scored': int(gf.get_text()), 'conceded': int(ga.get_text())})
                    except: continue
        
        if not matches: return None
        recent = matches[-LAST_N_MATCHES:]
        return {'scored_avg': round(calculate_weighted_avg([m['scored'] for m in recent]), 2), 'conceded_avg': round(calculate_weighted_avg([m['conceded'] for m in recent]), 2), 'source': 'FBRef', 'matches': len(recent)}
    except: return None