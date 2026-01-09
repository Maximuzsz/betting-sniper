"""
Utilities for Stats Service.
Contains team mapping, text normalization and math helpers.
"""
import re
import unicodedata

# Mapeamento expandido para cobrir apelidos e nomes curtos vs nomes de busca
TEAM_NAME_MAP = {
    # Brasil
    'galo': 'Atlético Mineiro', 'urubu': 'Flamengo', 'mengo': 'Flamengo',
    'vasco': 'Vasco da Gama', 'athletico': 'Athletico Paranaense', 'cap': 'Athletico Paranaense',
    'inter': 'Internacional', 'gremio': 'Grêmio', 'america-mg': 'América Mineiro',
    'sport': 'Sport Recife', 'ceara': 'Ceará', 'vitoria': 'Vitória', 'goias': 'Goiás',
    'ponte': 'Ponte Preta', 'guarani': 'Guarani', 'vila': 'Vila Nova', 'novorizontino': 'Grêmio Novorizontino',
    'crb': 'CRB', 'sampaio': 'Sampaio Corrêa', 'londrina': 'Londrina', 'abc': 'ABC',
    
    # Alemanha (Bundesliga)
    'dortmund': 'Borussia Dortmund', 'bvb': 'Borussia Dortmund',
    'bayern': 'Bayern München', 'munich': 'Bayern München', 'munchen': 'Bayern München',
    'frankfurt': 'Eintracht Frankfurt', 'eintracht': 'Eintracht Frankfurt',
    'leipzig': 'RB Leipzig', 'rbl': 'RB Leipzig',
    'leverkusen': 'Bayer Leverkusen', 'bayer': 'Bayer Leverkusen',
    'stuttgart': 'VfB Stuttgart', 'wolfsburg': 'VfL Wolfsburg',
    'gladbach': 'Borussia Mönchengladbach', 'monchengladbach': 'Borussia Mönchengladbach',
    'mainz': 'Mainz 05', 'hoffenheim': 'TSG Hoffenheim', 'augsburg': 'FC Augsburg',
    
    # Inglaterra (Premier League)
    'city': 'Manchester City', 'man city': 'Manchester City',
    'united': 'Manchester United', 'man utd': 'Manchester United',
    'tottenham': 'Tottenham Hotspur', 'spurs': 'Tottenham Hotspur',
    'wolves': 'Wolverhampton Wanderers', 'leicester': 'Leicester City',
    'newcastle': 'Newcastle United', 'west ham': 'West Ham United',
    'forest': 'Nottingham Forest', 'nottingham': 'Nottingham Forest',
    'brighton': 'Brighton & Hove Albion', 'palace': 'Crystal Palace',
    
    # Espanha (La Liga)
    'real': 'Real Madrid', 'barca': 'Barcelona', 'atletico': 'Atlético Madrid',
    'atleti': 'Atlético Madrid', 'betis': 'Real Betis', 'sociedad': 'Real Sociedad',
    'bilbao': 'Athletic Bilbao', 'athletic': 'Athletic Bilbao', 'sevilla': 'Sevilla',
    
    # Itália (Serie A)
    'inter milan': 'Inter de Milão', 'internazionale': 'Inter de Milão',
    'ac milan': 'Milan', 'juve': 'Juventus', 'roma': 'Roma', 'lazio': 'Lazio',
    'napoli': 'Napoli', 'atalanta': 'Atalanta', 'fiorentina': 'Fiorentina',
    'torino': 'Torino', 'monza': 'Monza', 'lecce': 'Lecce', 'verona': 'Hellas Verona',
    
    # França (Ligue 1)
    'psg': 'Paris Saint-Germain', 'paris': 'Paris Saint-Germain',
    'marseille': 'Olympique de Marseille', 'lyon': 'Olympique Lyonnais',
    'monaco': 'Monaco', 'lille': 'Lille', 'lens': 'Lens', 'rennes': 'Rennes',
    'nice': 'Nice', 'brest': 'Brest', 'reims': 'Reims',

    # Portugal (Primeira Liga)
    'sporting cp': 'Sporting', 'benfica': 'Benfica', 'porto': 'Porto', 'braga': 'Sporting de Braga',
    'guimaraes': 'Vitória SC', 'vitoria sc': 'Vitória SC', 'famalicao': 'Famalicão',
    
    # Holanda (Eredivisie)
    'ajax': 'Ajax', 'psv': 'PSV', 'feyenoord': 'Feyenoord', 'az': 'AZ Alkmaar', 'twente': 'Twente'
}

def normalize_text(text):
    if not text: return ""
    return unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8').lower().strip()

def clean_team_name(name):
    """Limpa o nome para busca, resolvendo apelidos e removendo sufixos."""
    norm = normalize_text(name)
    
    # 1. Verifica mapa manual (busca exata ou parcial)
    for k, v in TEAM_NAME_MAP.items():
        # Verifica se a chave está contida no nome (ex: "dortmund" em "borussia dortmund")
        if k == norm or (len(k) > 3 and k in norm): 
            return v
    
    # 2. Remove sufixos comuns internacionais que atrapalham a busca
    clean = re.sub(r'\b(fc|ec|sc|ac|as|sv|vfb|cf|club|clube|sport|calcio|squadra|united|city)\b', '', norm).strip()
    if clean: return clean.title()
    
    return name

def calculate_weighted_avg(matches):
    """Calcula média ponderada (jogos mais recentes têm mais peso)."""
    if not matches: return 0.0
    
    total_weight = 0
    weighted_sum = 0
    
    for i, match in enumerate(reversed(matches)): # O último da lista é o mais recente
        weight = i + 1 # 1, 2, 3, 4, 5...
        weighted_sum += match * weight
        total_weight += weight
        
    return weighted_sum / total_weight