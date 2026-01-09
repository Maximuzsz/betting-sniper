"""
Team statistics service (goals scored/conceded).
Fetches LAST 5 MATCHES statistics asynchronously.
"""
from services.stats_utils import normalize_text
from services.stats_scrapers import fetch_ogol_stats, fetch_fbref_stats

# Cache em memória para evitar requests repetidos na mesma sessão
STATS_CACHE = {}

class StatsService:
    def __init__(self):
        pass
        
    def get_team_stats(self, team_name, league_key, league_name="futebol"):
        cache_key = f"{normalize_text(team_name)}_{league_key}"
        if cache_key in STATS_CACHE:
            print(f"   💾 Cache hit: {team_name}")
            return STATS_CACHE[cache_key]

        print(f"   📊 Buscando stats para {team_name}...")
        
        # Tenta OGol Primeiro (Mais rápido/estável)
        data = fetch_ogol_stats(team_name)
        
        # Se falhar, tenta FBRef
        if not data:
            data = fetch_fbref_stats(team_name)
            
        if data:
            STATS_CACHE[cache_key] = data
            return data

        print(f"   ⚠️ Stats não encontrados. Usando padrão.")
        return {'scored_avg': 1.35, 'conceded_avg': 1.25, 'source': 'Default'}