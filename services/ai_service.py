"""
AI service for context analysis using Google Gemini.
Implements model rotation, JSON validation, and structured output.
"""
import json
import re
import datetime
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

class AIService:
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        
        # Configurações de segurança permissivas
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        # CORREÇÃO PRINCIPAL: Usando IDs de versão específicos (001/002)
        # Isso evita o erro 404 de alias não encontrado
        self.models_priority = [
            'gemini-1.5-flash-002',  # Versão mais nova e estável do Flash
            'gemini-1.5-flash-001',  # Versão anterior (Backup seguro)
            'gemini-1.5-pro-002',    # Pro apenas como último recurso (limite baixo)
        ]
        self.current_model_index = 0

    def analyze_context(self, match_info, math_probs, news_context):
        """
        Analyze match context using AI with automatic model rotation.
        """
        # 1. Validação de Entrada
        if not news_context or len(str(news_context)) < 10 or "Nenhuma notícia" in str(news_context):
            news_context = "Sem dados específicos recentes. Assuma base titular e risco neutro."

        current_date = datetime.datetime.now().strftime("%d/%m/%Y")

        # 2. Prompt Engenharia
        prompt = f"""
        Você é um Trader Esportivo Profissional (Sniper).
        Hoje é: {current_date}.
        
        OBJETIVO:
        Analise as notícias abaixo para determinar o impacto QUALITATIVO no jogo.
        
        DADOS DO JOGO:
        Confronto: {match_info.get('home_team', 'Casa')} (Casa) x {match_info.get('away_team', 'Visitante')} (Visitante)
        Probabilidade Matemática (Poisson): Casa {math_probs.get('home_win', 0):.1%} | Visitante {math_probs.get('away_win', 0):.1%}
        
        NOTÍCIAS EXTRAÍDAS:
        \"\"\"
        {news_context}
        \"\"\"
        
        REGRAS DE ANÁLISE:
        1. Escalação: "Time misto", "reservas", "poupar" = PENALIDADE GRAVE.
        2. Desfalques: Ausência de goleiro titular ou artilheiro = PENALIDADE MÉDIA.
        3. Motivação (Must Win): Time precisa vencer para ser campeão ou não cair? = BÔNUS LEVE.
        4. Desmotivação: "Cumprir tabela", "foco em outra competição" = PENALIDADE MÉDIA.
        5. Estilo de Jogo: Se a notícia citar "retranca" ou "jogo fechado", ajuste a tendência de gols para Baixa.
        6. Mercado: Ignore notícias sobre transferências futuras.
        
        FORMATO DE SAÍDA (JSON):
        {{
            "analise_textual": "Resumo de 1 frase (ex: 'Palmeiras poupa titulares focado na Libertadores').",
            "delta_home": 0.0,
            "delta_away": 0.0,
            "tendencia_gols": "Alta", 
            "tendencia_btts": "Sim",
            "risco_critico": false
        }}
        """
        
        # 3. Configuração
        generation_config = {
            "response_mime_type": "application/json",
            "temperature": 0.2
        }
        
        last_error = ""
        # Tenta todos os modelos da lista
        max_attempts = len(self.models_priority)
        
        for attempt in range(max_attempts): 
            try:
                model_name = self.models_priority[self.current_model_index]
                
                # Instancia o modelo
                model = genai.GenerativeModel(
                    model_name, 
                    safety_settings=self.safety_settings
                )
                
                # print(f"🤖 AI Analysis: Tentando modelo {model_name}...")
                resp = model.generate_content(prompt, generation_config=generation_config)
                
                # Parseamento
                try:
                    result = json.loads(resp.text)
                    if "delta_home" not in result: 
                        raise ValueError("JSON incompleto")
                    return result
                except (json.JSONDecodeError, ValueError):
                    # Fallback Regex 
                    json_match = re.search(r'\{[\s\S]*\}', resp.text)
                    if json_match:
                        return json.loads(json_match.group())
                    raise ValueError("Falha no parse do JSON")
                    
            except Exception as e:
                error_str = str(e).lower()
                last_error = str(e)
                # print(f"⚠️ Erro no modelo {model_name}: {error_str}")
                
                # Rotação de modelo
                self.current_model_index += 1
                if self.current_model_index >= len(self.models_priority):
                    self.current_model_index = 0
                
                # Se for erro de autenticação, para tudo
                if "api_key" in error_str:
                    break

        # Fallback Seguro
        return {
            "analise_textual": f"Erro IA ({last_error[:50]}). Usando base matemática.", 
            "delta_home": 0.0, 
            "delta_away": 0.0, 
            "tendencia_gols": "Neutra", 
            "tendencia_btts": "Duvidoso", 
            "risco_critico": False
        }