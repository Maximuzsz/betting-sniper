"""
AI service for context analysis using Google Gemini.
Implements model rotation to avoid 429 errors.
"""
import json
import re
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold


class AIService:
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        self.models_priority = [
            'gemini-2.5-flash-preview-09-2025',
            'gemini-2.5-flash',
            'gemini-2.0-flash-exp', 
            'gemini-1.5-flash', 
            'gemini-1.5-flash-latest',
            'gemini-1.5-pro',
            'gemini-pro'
        ]
        self.current_model_index = 0
        self.active_model = None

    def _get_working_model(self):
        """Get the current working model, rotating if needed."""
        if self.current_model_index >= len(self.models_priority):
            self.current_model_index = 0
        model_name = self.models_priority[self.current_model_index]
        if not self.active_model:
            self.active_model = genai.GenerativeModel(model_name, safety_settings=self.safety_settings)
        return self.active_model

    def analyze_context(self, match_info, math_probs, news_context):
        """
        Analyze match context using AI.
        
        Args:
            match_info: Match data with home_team and away_team
            math_probs: Mathematical probabilities from Poisson
            news_context: News and lineup information
        
        Returns:
            dict with analysis, deltas, and trends
        """
        if "Nenhuma notícia" in news_context or "não disponível" in news_context.lower() or "apenas estatísticas" in news_context.lower():
            news_context = "Sem dados recentes disponíveis. Assuma base titular e risco neutro."

        prompt = f"""
        Você é um Trader Esportivo Profissional (Sniper).
        
        OBJETIVO:
        Analise o CONTEÚDO EXTRAÍDO de sites esportivos abaixo.
        
        DADOS DO JOGO:
        Confronto: {match_info.get('home_team')} x {match_info.get('away_team')}
        Probabilidade Matemática: Casa {math_probs['home_win']:.1%} | Visitante {math_probs['away_win']:.1%}
        
        NOTÍCIAS (LEIA TUDO):
        \"\"\"
        {news_context}
        \"\"\"
        
        TAREFA:
        1. Identifique a "Provável Escalação" no texto.
           - Se citar "time misto", "reservas" ou "poupar", penalize o time fortemente.
           - Se citar "força máxima", bonifique levemente.
        2. Liste os DESFALQUES confirmados (Lesão, Suspensão).
        3. Ignore informações de "Mercado da Bola".
        
        Retorne um JSON com esta estrutura exata:
        {{
            "analise_textual": "Texto resumo (máx 300 chars)",
            "delta_home": 0.0,
            "delta_away": 0.0,
            "tendencia_gols": "Neutra",
            "tendencia_btts": "Duvidoso",
            "risco_critico": false
        }}
        """
        
        last_error = ""
        max_attempts = min(3, len(self.models_priority))
        
        for attempt in range(max_attempts): 
            model = self._get_working_model()
            model_name = self.models_priority[self.current_model_index]
            try:
                print(f"🤖 Trying model: {model_name} (attempt {attempt + 1}/{max_attempts})")
                resp = model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                
                try:
                    result = json.loads(resp.text)
                    print(f"✅ Analysis completed successfully using {model_name}")
                    return result
                except json.JSONDecodeError as je:
                    json_match = re.search(r'\{[^}]+\}', resp.text)
                    if json_match:
                        try:
                            return json.loads(json_match.group())
                        except:
                            pass
                    last_error = f"Invalid JSON: {str(je)}"
                    continue
                    
            except Exception as e:
                error_str = str(e)
                print(f"⚠️ Error in model {model_name}: {error_str[:200]}")
                last_error = error_str
                
                if any(code in error_str for code in ["429", "404", "403"]) or any(word in error_str.lower() for word in ["quota", "not found", "permission"]):
                    self.current_model_index += 1
                    self.active_model = None
                    if self.current_model_index >= len(self.models_priority):
                        self.current_model_index = 0
                else:
                    if attempt < max_attempts - 1:
                        continue
                    break
                    
        print(f"❌ Failed to process AI analysis after {max_attempts} attempts")
        return {
            "analise_textual": f"Limited analysis - error: {last_error[:100] if last_error else 'Unknown error'}. Using mathematical data.", 
            "delta_home": 0.0, 
            "delta_away": 0.0, 
            "tendencia_gols": "Neutra", 
            "tendencia_btts": "Duvidoso", 
            "risco_critico": False
        }
