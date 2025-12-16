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
        """Fetch matches with odds for a specific league."""
        url = f"{self.base_url}/sports/{sport_key}/odds"
        
        regions_list = ['us', 'uk', 'au', 'eu'] if 'brazil' in sport_key else ['eu', 'us', 'uk']
        last_response = None
        last_region = None
        
        for region in regions_list:
            params = {
                'apiKey': self.api_key, 
                'regions': region, 
                'markets': 'h2h', 
                'oddsFormat': 'decimal'
            }
            try:
                r = requests.get(url, params=params, timeout=10)
                last_response = r
                last_region = region
                
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list):
                        if len(data) > 0:
                            print(f"✅ Found {len(data)} matches in region {region}")
                            return data
                        continue
                    elif isinstance(data, dict) and 'error' in data:
                        return {"error": data.get('error', 'Unknown error')}
                elif r.status_code == 401:
                    error_msg = r.json().get('message', 'Invalid API key') if r.text else 'Invalid API key'
                    return {"error": error_msg}
                elif r.status_code == 429:
                    return {"error": "Rate limit exceeded. Try again later."}
                    
            except requests.exceptions.Timeout:
                continue
            except requests.exceptions.RequestException:
                continue
            except Exception:
                continue
        
        print(f"ℹ️ No region returned matches for {sport_key}")
        return []
