# Em services/math_engine.py
import math
from typing import Dict

class PoissonEngine:
    """
    Motor matemático para calcular probabilidades baseadas no histórico (xG ou Média de Gols).
    """
    def __init__(self, max_goals: int = 5):
        # 5 gols é o limite da nossa matriz. Acima disso, a chance estatística é quase zero.
        self.max_goals = max_goals

    def _poisson_probability(self, expected_goals: float, exact_goals: int) -> float:
        """
        Aplica a fórmula matemática de Poisson.
        """
        # Proteção contra xG zerado para não quebrar a matemática
        if expected_goals <= 0:
            return 1.0 if exact_goals == 0 else 0.0
            
        return ((math.exp(-expected_goals)) * (expected_goals ** exact_goals)) / math.factorial(exact_goals)

    def calculate_probabilities(self, home_xg: float, away_xg: float) -> Dict[str, float]:
        """
        Cruza as probabilidades de todos os placares possíveis (0x0 até 5x5) 
        e consolida no mercado 1X2 (Home, Draw, Away).
        """
        prob_home = 0.0
        prob_draw = 0.0
        prob_away = 0.0

        for home_goals in range(self.max_goals + 1):
            for away_goals in range(self.max_goals + 1):
                # Calcula a chance desse placar exato acontecer (ex: 2x1)
                prob_exact_score = (
                    self._poisson_probability(home_xg, home_goals) * self._poisson_probability(away_xg, away_goals)
                )

                # Soma a probabilidade no balde correto
                if home_goals > away_goals:
                    prob_home += prob_exact_score
                elif home_goals == away_goals:
                    prob_draw += prob_exact_score
                else:
                    prob_away += prob_exact_score

        # Normaliza para garantir que a soma seja exata (compensando placares > 5)
        total = prob_home + prob_draw + prob_away
        
        return {
            "home_win": round(prob_home / total, 4),
            "draw": round(prob_draw / total, 4),
            "away_win": round(prob_away / total, 4)
        }