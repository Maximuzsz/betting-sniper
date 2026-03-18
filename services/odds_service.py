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
        if not self.api_key: return None

        sport_key = self.league_map.get(league_id, "upcoming")
        url = f"{self.base_url}/sports/{sport_key}/odds"
        
        params = {
            "apiKey": self.api_key,
            "regions": "eu,uk",
            "markets": "h2h,totals", # <--- ADICIONAMOS 'totals' AQUI
            "oddsFormat": "decimal"
        }

        try:
            response = requests.get(url, params=params)
            if response.status_code != 200: return None
            games = response.json()
            
            for game in games:
                g_home, g_away = game['home_team'].lower(), game['away_team'].lower()
                h_team, a_team = home_team.lower(), away_team.lower()

                if (h_team in g_home or g_home in h_team) and (a_team in g_away or g_away in a_team):
                    if game['bookmakers']:
                        bookmaker = game['bookmakers'][0]
                        # Inicializa o dicionário com os 5 mercados
                        odds = {"home": 0.0, "draw": 0.0, "away": 0.0, "over_2.5": 0.0, "under_2.5": 0.0}
                        
                        for market in bookmaker['markets']:
                            if market['key'] == 'h2h':
                                for outcome in market['outcomes']:
                                    name = outcome['name'].lower()
                                    if name == g_home: odds['home'] = float(outcome['price'])
                                    elif name == g_away: odds['away'] = float(outcome['price'])
                                    elif name == 'draw': odds['draw'] = float(outcome['price'])
                            
                            # Captura as odds de Over/Under 2.5
                            elif market['key'] == 'totals':
                                for outcome in market['outcomes']:
                                    if outcome['point'] == 2.5: # Trava na linha asiática principal de 2.5
                                        if outcome['name'].lower() == 'over':
                                            odds['over_2.5'] = float(outcome['price'])
                                        elif outcome['name'].lower() == 'under':
                                            odds['under_2.5'] = float(outcome['price'])
                                
                        print(f"✅ [ODDS REAIS COMPLETAS]: {odds}")
                        return odds
            return None
        except Exception as e:
            print(f"❌ Erro na Odds API: {e}")
            return None