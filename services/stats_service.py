import requests
from typing import Dict, Any, Optional

class StatsService:
    """
    Serviço responsável por buscar estatísticas reais (dados quantitativos) 
    usando a API-Football (v3).
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        # Usando a URL direta da API-Sports (mais rápida que pelo RapidAPI)
        self.base_url = "https://v3.football.api-sports.io"
        self.headers = {
            'x-apisports-key': self.api_key
        }

    def fetch_team_season_stats(self, league_id: int, season: int, team_id: int) -> Optional[Dict[str, float]]:
        """
        Busca a média de gols marcados pelo time na temporada.
        Retorna um dicionário com o xG (ou média de gols) para alimentar o Poisson.
        """
        endpoint = f"{self.base_url}/teams/statistics"
        params = {
            "league": league_id,
            "season": season,
            "team": team_id
        }

        try:
            # Timeout curto para não prender o fluxo do app
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Validação: Verifica se a API retornou erros ou dados vazios
            if not data.get('response') or data.get('errors'):
                print(f"⚠️ Erro na API de Stats: {data.get('errors')}")
                return None

            stats = data['response']
            
            # Navegando no JSON da API-Football para pegar a média de gols a favor (goals for)
            # Para refinar depois, podemos separar 'home' e 'away'
            goals_for_home = float(stats['goals']['for']['average']['home'])
            goals_for_away = float(stats['goals']['for']['average']['away'])

            return {
                "home_xg": goals_for_home,
                "away_xg": goals_for_away
            }

        except requests.exceptions.RequestException as e:
            print(f"❌ Erro de conexão com a API de Stats: {str(e)}")
            return None
        except KeyError as e:
            print(f"❌ Erro ao processar o JSON (formato inesperado): {str(e)}")
            return None
        
    def fetch_upcoming_matches(self, date_str: str, league_id: Optional[int] = None, season: Optional[int] = None) -> list:
        """
        Busca os jogos (fixtures) agendados para uma data específica.
        Formato da data esperado: 'YYYY-MM-DD'
        """
        endpoint = f"{self.base_url}/fixtures"
        
        # Parâmetros base da busca
        params = {"date": date_str}
        
        # Filtros opcionais para não gastar muita banda/cota puxando ligas irrelevantes
        if league_id:
            params["league"] = league_id
        if season:
            params["season"] = season

        try:
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data.get('response'):
                return []

            fixtures = data['response']
            upcoming = []

            for item in fixtures:
                fixture = item['fixture']
                teams = item['teams']
                league = item['league']
                
                # Vamos filtrar apenas jogos que não começaram (NS - Not Started) ou estão prestes a começar
                if fixture['status']['short'] in ['NS', 'TBD']:
                    upcoming.append({
                        "fixture_id": fixture['id'],
                        "date": fixture['date'],
                        "league_id": league['id'],
                        "league_name": league['name'],
                        "season": league['season'],
                        "home_team_id": teams['home']['id'],
                        "home_team_name": teams['home']['name'],
                        "home_team_logo": teams['home']['logo'], # Pra ficar bonito no Flutter!
                        "away_team_id": teams['away']['id'],
                        "away_team_name": teams['away']['name'],
                        "away_team_logo": teams['away']['logo']
                    })
                    
            return upcoming

        except requests.exceptions.RequestException as e:
            print(f"❌ Erro ao buscar próximos jogos: {str(e)}")
            return []