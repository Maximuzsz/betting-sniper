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
        params = {
            "date": date_str,
            "timezone": "America/Sao_Paulo" # <-- Garante que a data bata com o Brasil!
        }
        
        if league_id:
            params["league"] = league_id
        if season:
            params["season"] = season

        try:
            # Aumentamos o timeout para 15s pois buscar o mundo todo exige mais do servidor
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            # 🚨 O DETETIVE DE ERROS 🚨
            # Se a API reclamar de cota estourada ou chave inválida, vai aparecer no log do Render
            if data.get('errors'):
                print(f"⚠️ ALERTA API-SPORTS: {data.get('errors')}")

            if not data.get('response'):
                print(f"ℹ️ Nenhum jogo retornado pela API para a data {date_str}.")
                return []

            fixtures = data['response']
            upcoming = []

            for item in fixtures:
                fixture = item['fixture']
                teams = item['teams']
                league = item['league']
                
                # Vamos filtrar apenas jogos que não começaram (NS ou TBD)
                if fixture['status']['short'] in ['NS', 'TBD']:
                    upcoming.append({
                        "fixture_id": fixture['id'],
                        "date": fixture['date'],
                        "league_id": league['id'],
                        "league_name": league['name'],
                        "season": league['season'],
                        "home_team_id": teams['home']['id'],
                        "home_team_name": teams['home']['name'],
                        "home_team_logo": teams['home']['logo'],
                        "away_team_id": teams['away']['id'],
                        "away_team_name": teams['away']['name'],
                        "away_team_logo": teams['away']['logo']
                    })
                    
            # Dica Sênior: Se você não filtrou por liga, a API traz milhares de jogos. 
            # Limitamos aos primeiros 30 para o celular não engasgar renderizando tudo de uma vez.
            return upcoming[:30] if not league_id else upcoming

        except requests.exceptions.RequestException as e:
            print(f"❌ Erro ao buscar próximos jogos: {str(e)}")
            return []