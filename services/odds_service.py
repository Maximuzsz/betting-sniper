"""
Service to fetch betting odds via The Odds API.
"""
import requests


class OddsService:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.the-odds-api.com/v4"

    def get_available_sports(self):
        """List all sports available in the API."""
        url = f"{self.base_url}/sports"
        params = {'apiKey': self.api_key}
        try:
            r = requests.get(url, params=params, timeout=10)
            return r.json() if r.status_code == 200 else []
        except:
            return []
    
    def get_upcoming_matches(self, sport_key='soccer_brazil_campeonato'):
        """Fetch matches with odds for a specific league, aggregating from multiple regions."""
        url = f"{self.base_url}/sports/{sport_key}/odds"
        
        # Prioritize regions where Bet365 is more common
        regions_list = ['uk', 'eu', 'us', 'au']
        
        aggregated_matches = {}

        for region in regions_list:
            params = {
                'apiKey': self.api_key, 
                'regions': region, 
                'markets': 'h2h', 
                'oddsFormat': 'decimal'
            }
            try:
                r = requests.get(url, params=params, timeout=12)
                
                if r.status_code == 200:
                    matches_from_region = r.json()
                    
                    if not isinstance(matches_from_region, list):
                        continue

                    print(f"✅ Found {len(matches_from_region)} matches in region '{region}' for {sport_key}")

                    for match in matches_from_region:
                        match_id = match.get('id')
                        if not match_id:
                            continue

                        if match_id not in aggregated_matches:
                            # Se o jogo não está no nosso dicionário, adiciona
                            aggregated_matches[match_id] = match
                        else:
                            # Se o jogo já existe, agrega os bookmakers
                            existing_bookmakers = aggregated_matches[match_id].get('bookmakers', [])
                            new_bookmakers = match.get('bookmakers', [])
                            
                            # Evita duplicatas, mantendo os bookmakers já existentes
                            existing_keys = {b['key'] for b in existing_bookmakers}
                            for bookmaker in new_bookmakers:
                                if bookmaker['key'] not in existing_keys:
                                    existing_bookmakers.append(bookmaker)
                            
                            aggregated_matches[match_id]['bookmakers'] = existing_bookmakers
                
                elif r.status_code == 401:
                    return {"error": "API Key inválida."}
                
            except requests.exceptions.RequestException as e:
                print(f"⚠️ Request error for region {region}: {e}")
                continue
        
        if not aggregated_matches:
            print(f"ℹ️ No matches found for {sport_key} in any region.")
            return []
            
        final_list = list(aggregated_matches.values())
        print(f"✨ Total de {len(final_list)} jogos únicos agregados.")
        return final_list
