from typing import Dict, Any, List

class DecisionEngine:
    """
    O Gatilho. Calcula Valor Esperado (+EV) e gestão de banca (Critério de Kelly Fracionado).
    """
    def __init__(self, kelly_fraction: float = 0.25, min_ev: float = 0.05):
        # Kelly Fracionado (1/4) é o padrão ouro profissional para reduzir a variância.
        self.kelly_fraction = kelly_fraction
        # Só atiramos se houver no mínimo 5% de vantagem (EV) sobre a casa de aposta.
        self.min_ev = min_ev

    def _calculate_ev(self, prob_ia: float, odd: float) -> float:
        """ Fórmula simples: (Probabilidade * Odd) - 100% """
        return (prob_ia * odd) - 1.0

    def _calculate_kelly_stake(self, prob_ia: float, odd: float, bankroll: float) -> float:
        """
        Calcula a Stake usando Kelly Fracionado com travas de segurança.
        """
        # 1. Normalização de sanidade: prob_ia nunca pode ser > 1 ou < 0
        p = max(0.0, min(float(prob_ia), 0.99)) # Limitamos a 99% para evitar divisão por zero bizarra
        
        b = odd - 1.0
        q = 1.0 - p

        if b <= 0: 
            return 0.0
            
        kelly_pct = ((b * p) - q) / b
        
        if kelly_pct <= 0: 
            return 0.0
            
        # 2. Kelly Fracionado (Ex: 0.25 para ser conservador)
        safe_kelly_pct = kelly_pct * self.kelly_fraction
        
        # 3. TRAVA SÊNIOR: Nunca arriscar mais de 5% da banca em um único tiro
        # Isso evita os R$ 36.000,00 que vimos no print.
        max_risk_pct = 0.05 
        final_pct = min(safe_kelly_pct, max_risk_pct)
        
        return round(bankroll * final_pct, 2)

    def evaluate_market(self, ai_adjusted_probs: Dict[str, Any], market_odds: Dict[str, float], bankroll: float) -> Dict[str, Any]:
        """
        Varre o mercado 1X2 (Casa, Empate, Fora) e decide onde (e se) o Sniper deve atirar.
        """
        decisions: List[Dict[str, Any]] = []
        
        # Mapeamento para cruzar o JSON da IA com as Odds do Mercado
        market_map = {
            'home': 'prob_home_ajustada',
            'draw': 'prob_draw_ajustada',
            'away': 'prob_away_ajustada'
        }
        
        # --- NOVO: TRADUTOR DE MERCADOS ---
        tradutor_mercado = {
            'home': 'VITÓRIA MANDANTE (1)',
            'draw': 'EMPATE (X)',
            'away': 'VITÓRIA VISITANTE (2)'
        }
        
        for market, ai_key in market_map.items():
            prob_ia = ai_adjusted_probs.get(ai_key, 0.0)
            odd = market_odds.get(market, 0.0)
            
            if odd <= 1.0 or prob_ia <= 0.0:
                continue
                
            ev = self._calculate_ev(prob_ia, odd)
            
            # O Gatilho: Se a IA está confiante e a matemática aprova, nós atiramos.
            confianca = ai_adjusted_probs.get('confianca_analise', 1.0) # Assume 1.0 se a IA não retornar esse campo
            if ev >= self.min_ev and confianca >= 0.7:
                stake = self._calculate_kelly_stake(prob_ia, odd, bankroll)
                
                # Só adiciona a recomendação se a stake sugerida for maior que zero
                if stake > 0:
                    decisions.append({
                        "mercado": tradutor_mercado[market], # <--- Aplica a tradução para PT-BR aqui
                        "odd_oferecida": odd,
                        "probabilidade_sniper": round(prob_ia * 100, 2),
                        "ev_esperado_pct": round(ev * 100, 2),
                        "stake_recomendada_R$": stake,
                        "justificativa": ai_adjusted_probs.get('justificativa_sniper', 'Análise de valor matemático aprovada.')
                    })
                
        return {
            "aprovado": len(decisions) > 0,
            "entradas_recomendadas": decisions
        }