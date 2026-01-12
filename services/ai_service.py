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
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        # LISTA DE MODELOS ATUALIZADA (Priorizando Aliases Estáveis)
        # Usar aliases genéricos é mais seguro para evitar erros 404
        self.models_priority = [
            'gemini-2.5-flash',          # Ouro: Rápido e Inteligente
            'gemini-2.5-pro',            # Prata: Raciocínio Profundo
            'gemini-2.0-flash',          # Bronze: Estável
            'gemini-2.0-flash-lite',     # Backup Leve
            'gemini-flash-latest'        # Alias Genérico
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
        """
        # 1. Validação de Entrada
        if not news_context or len(str(news_context)) < 10 or "Nenhuma notícia" in str(news_context):
            news_context = "Sem dados específicos recentes. Assuma base titular e risco neutro."

        current_date = datetime.datetime.now().strftime("%d/%m/%Y")

        # 2. Prompt Engenharia (Refinado)
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
            "delta_home": 0.0,  // Ajuste decimal (Ex: -0.15 para perda grave, +0.05 para reforço)
            "delta_away": 0.0,
            "tendencia_gols": "Alta", // Alta (Over), Neutra, Baixa (Under)
            "tendencia_btts": "Sim",  // Sim, Não, Duvidoso
            "risco_critico": false    // True se houver time reserva ou crise grave
        }}
        """
        
        # 3. Configuração para forçar JSON (funciona nos modelos 1.5+)
        generation_config = {
            "response_mime_type": "application/json"
        }
        
        last_error = ""
        # Tenta modelos suficientes para garantir
        max_attempts = len(self.models_priority) 
        
        for attempt in range(max_attempts): 
            model = self._get_working_model()
            model_name = self.models_priority[self.current_model_index]
            
            try:
                # print(f"🤖 AI Analysis ({model_name})...")
                resp = model.generate_content(prompt, generation_config=generation_config)
                
                # Tenta parsear JSON direto
                try:
                    result = json.loads(resp.text)
                    if "delta_home" not in result: 
                        raise ValueError("JSON incompleto")
                    return result
                except (json.JSONDecodeError, ValueError):
                    # Fallback com Regex robusto
                    json_match = re.search(r'\{[\s\S]*\}', resp.text)
                    if json_match:
                        return json.loads(json_match.group())
                    raise ValueError("Não foi possível extrair JSON da resposta")
                    
            except Exception as e:
                error_str = str(e).lower()
                # print(f"⚠️ Erro AI ({model_name}): {error_str}")
                last_error = str(e)
                
                # Erros que exigem troca de modelo imediata (404, Cota, Permissão)
                if any(x in error_str for x in ["404", "not found", "quota", "429", "resource"]):
                    self.current_model_index += 1
                    self.active_model = None # Força recriação com novo nome
                else:
                    # Outros erros (ex: server error 500)
                    if attempt == max_attempts - 1: break
                    
        # Fallback Final Seguro
        return {
            "analise_textual": f"Erro na IA: {last_error[:50]}... Usando base matemática.", 
            "delta_home": 0.0, 
            "delta_away": 0.0, 
            "tendencia_gols": "Neutra", 
            "tendencia_btts": "Duvidoso", 
            "risco_critico": False
        }