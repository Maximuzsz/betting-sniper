import json
from google import genai
from google.genai import types
from typing import Dict, Any

class AIAnalyst:
    """
    O Cérebro do Sniper usando o novo SDK oficial 'google-genai'.
    """
    def __init__(self, api_key: str, model_name: str = 'gemini-2.5-flash'):
        # Instancia o novo cliente
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    def generate_adjusted_probabilities(self, home_team: str, away_team: str, math_probs: Dict[str, float], news_context: str) -> Dict[str, Any]:
        prompt = f"""
        Você é o Analista de Risco Sênior do sistema 'Betting Sniper'.
        Sua função não é adivinhar o vencedor, mas AJUSTAR probabilidades matemáticas baseadas em fatos extracampo.

        # 🛑 REGRA DE OURO (IDIOMA E TERMINOLOGIA) 🛑
        1. Você DEVE gerar o texto da chave "justificativa_sniper" EXCLUSIVAMENTE em Português do Brasil (pt-BR).
        2. NUNCA use termos em inglês como 'Home', 'Away' ou 'Draw' no seu texto. Use 'Mandante' (ou o nome exato do time), 'Visitante' e 'Empate'.
        3. A sua justificativa deve ser fria, direta e estritamente técnica. Foque no impacto matemático das heurísticas aplicadas.

        DADOS DO JOGO:
        Confronto: {home_team} (Mandante) x {away_team} (Visitante)
        
        Probabilidade Base (Poisson):
        - Vitória Mandante: {math_probs.get('home_win', 0):.1%}
        - Empate: {math_probs.get('draw', 0):.1%}
        - Vitória Visitante: {math_probs.get('away_win', 0):.1%}

        NOTÍCIAS EXTRAÍDAS HOJE (Contexto Qualitativo):
        \"\"\"
        {news_context}
        \"\"\"

        HEURÍSTICAS DO ANALISTA (Regras de Ajuste):
        1. Desfalques Críticos (Goleiro titular, Artilheiro, Capitão): Reduza a probabilidade do time afetado em 10% a 20%. Redistribua entre empate e vitória do adversário.
        2. Fator "Must Win" (Luta contra rebaixamento, Decisão de vaga): Aumente a probabilidade do time motivado em 5% a 10%.
        3. Time Misto/Foco em Outra Copa: Redução severa de 20% a 30% na probabilidade de vitória.
        4. Notícias Neutras/Vazias ou Conflitantes: NÃO altere a probabilidade base de Poisson. Confie na matemática.

        FORMATO DE SAÍDA OBRIGATÓRIO (Apenas JSON válido):
        {{
            "prob_home_ajustada": 0.0,
            "prob_draw_ajustada": 0.0,
            "prob_away_ajustada": 0.0,
            "tendencia_gols": "Over 2.5" | "Under 2.5" | "Neutra",
            "confianca_analise": 0.0,
            "justificativa_sniper": "Sua explicação técnica rigorosamente em pt-BR."
        }}
        """

        try:
            # Nova sintaxe de chamada do modelo
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2 # Excelente escolha (baixa temperatura = zero alucinação)
                )
            )
            
            return json.loads(response.text)
            
        except Exception as e:
            return {
                "prob_home_ajustada": math_probs.get('home_win', 0),
                "prob_draw_ajustada": math_probs.get('draw', 0),
                "prob_away_ajustada": math_probs.get('away_win', 0),
                "tendencia_gols": "Neutra",
                "confianca_analise": 0.0,
                "justificativa_sniper": f"Erro na análise de IA ({str(e)}). O modelo matemático de Poisson foi mantido sem alterações."
            }