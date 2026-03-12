# Em core/models.py
class MatchData:
    def __init__(self, home, away):
        self.home = home
        self.away = away
        # Preenchidos ao longo do processo
        self.math_probs = {}   # {home_win: 0.5, ...}
        self.news_summary = "" # Resumo do NewsScout
        self.ai_adjusted = {}  # Probabilidades após o "feeling" da IA
        self.market_odds = {}  # Odds da Bet365/Pinnacle
        self.ev = 0.0          # Valor Esperado final