from scipy.stats import poisson

class PoissonEngine:
    def __init__(self, league_avg_goals=1.3):
        self.league_avg = league_avg_goals

    def calculate_probabilities(self, home_stats, away_stats):
        """
        home_stats: {'scored': float, 'conceded': float} (Médias)
        away_stats: {'scored': float, 'conceded': float} (Médias)
        """
        # 1. Força de Ataque e Defesa
        # Se o time marca 1.3 (igual a média), a força é 1.0.
        h_att = home_stats['scored'] / self.league_avg
        h_def = home_stats['conceded'] / self.league_avg
        
        a_att = away_stats['scored'] / self.league_avg
        a_def = away_stats['conceded'] / self.league_avg

        # 2. Expectativa de Gols (Lambda)
        # Ataque Casa x Defesa Visitante x Média Liga
        home_lambda = h_att * a_def * self.league_avg
        away_lambda = a_att * h_def * self.league_avg

        # 3. Probabilidades de Placar (Matriz 0x0 até 5x5)
        prob_home_win, prob_draw, prob_away_win = 0, 0, 0

        for h in range(6): # 0 a 5 gols
            for a in range(6):
                p = poisson.pmf(h, home_lambda) * poisson.pmf(a, away_lambda)
                if h > a:
                    prob_home_win += p
                elif h == a:
                    prob_draw += p
                else:
                    prob_away_win += p
                    
        return {
            "home_win": prob_home_win,
            "draw": prob_draw,
            "away_win": prob_away_win,
            "lambda_home": home_lambda,
            "lambda_away": away_lambda
        }