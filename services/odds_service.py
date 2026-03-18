import requests
from typing import Dict, Optional

class OddsService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.the-odds-api.com/v4"
        
        # Mapeamento de Ligas: Nossos IDs -> Chaves da Odds API
        self.league_map = {
            2: "soccer_uefa_champs_league",
            3: "soccer_uefa_europa_league",
            71: "soccer_brazil_campeonato",
            253: "soccer_usa_mls",
            # Se a liga não estiver mapeada, a API busca no modo geral "upcoming"
        }

    def fetch_real_odds(self, league_id: int, home_team: str, away_team: str) -> Optional[Dict[str, float]]:
        if not self.api_key:
            return None

        sport_key = self.league_map.get(league_id, "upcoming")
        url = f"{self.base_url}/sports/{sport_key}/odds"
        
        params = {
            "apiKey": self.api_key,
            "regions": "eu,uk", # Pega as casas mais líquidas (Pinnacle, Bet365, etc)
            "markets": "h2h",   # Mercado 1X2 (Match Odds)
            "oddsFormat": "decimal"
        }

        try:
            response = requests.get(url, params=params)
            if response.status_code != 200:
                print(f"⚠️ Erro na Odds API: {response.text}")
                return None

            games = response.json()
            
            # Busca o nosso jogo na lista devolvida pela casa de aposta
            for game in games:
                g_home = game['home_team'].lower()
                g_away = game['away_team'].lower()
                h_team = home_team.lower()
                a_team = away_team.lower()

                # Lógica Fuzzy Sênior: Verifica se o nome base está contido no nome da casa de aposta
                if (h_team in g_home or g_home in h_team) and (a_team in g_away or g_away in a_team):
                    
                    if game['bookmakers']:
                        # Pega as odds da primeira casa de apostas disponível
                        bookmaker = game['bookmakers'][0] 
                        for market in bookmaker['markets']:
                            if market['key'] == 'h2h':
                                odds = {"home": 0.0, "draw": 0.0, "away": 0.0}
                                for outcome in market['outcomes']:
                                    name = outcome['name'].lower()
                                    if name == g_home:
                                        odds['home'] = float(outcome['price'])
                                    elif name == g_away:
                                        odds['away'] = float(outcome['price'])
                                    elif name == 'draw':
                                        odds['draw'] = float(outcome['price'])
                                
                                print(f"✅ [ODDS REAIS] {bookmaker['title']}: {odds}")
                                return odds
            
            print(f"⚠️ Jogo {home_team} x {away_team} sem odds abertas no momento.")
            return None

        except Exception as e:
            print(f"❌ Falha de conexão com The Odds API: {e}")
            return None