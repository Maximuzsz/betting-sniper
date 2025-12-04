import requests
import json
import google.generativeai as genai
import warnings
import re
import unicodedata
from bs4 import BeautifulSoup
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# Configurações de Supressão de Erros
warnings.simplefilter("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", module="duckduckgo_search")
warnings.filterwarnings("ignore", category=UserWarning)

try:
    from duckduckgo_search import DDGS
except ImportError:
    from ddgs import DDGS

# --- SERVIÇO DE ODDS ---
class OddsService:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.the-odds-api.com/v4"

    def get_upcoming_matches(self, sport_key='soccer_brazil_campeonato'):
        url = f"{self.base_url}/sports/{sport_key}/odds"
        params = {'apiKey': self.api_key, 'regions': 'eu,us,uk', 'markets': 'h2h', 'oddsFormat': 'decimal'}
        try:
            r = requests.get(url, params=params)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"ERRO ODDS: {e}")
            return []

# --- SERVIÇO DE IA (ROTAÇÃO DE MODELOS ANTI-429) ---
class AIService:
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        # Lista de prioridade (Tenta o melhor, se falhar cai para o mais econômico)
        self.models_priority = [
            'gemini-2.5-flash-preview-09-2025', # Modelo mais recente e compatível
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
        # Se já esgotamos a lista, volta para o padrão seguro
        if self.current_model_index >= len(self.models_priority):
            self.current_model_index = 0
            
        model_name = self.models_priority[self.current_model_index]
        
        # Só cria o objeto se ainda não existir ou se mudamos de índice
        if not self.active_model:
            # print(f"🔄 Tentando modelo: {model_name}")
            self.active_model = genai.GenerativeModel(model_name, safety_settings=self.safety_settings)
            
        return self.active_model

    def analyze_context(self, match_info, math_probs, news_context):
        if "Nenhuma notícia" in news_context:
            news_context = "Sem dados recentes. Assuma base titular e risco neutro."

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
        
        # Tenta até 3 vezes, trocando de modelo se der erro
        for attempt in range(len(self.models_priority)): 
            model = self._get_working_model()
            try:
                resp = model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                return json.loads(resp.text)
            except Exception as e:
                error_str = str(e)
                print(f"⚠️ Erro no modelo {self.models_priority[self.current_model_index]}: {error_str}")
                last_error = error_str
                
                # Se for erro de Cota (429) ou Não Encontrado (404), troca de modelo
                if "429" in error_str or "404" in error_str or "quota" in error_str.lower() or "not found" in error_str.lower():
                    print("   -> Trocando para o próximo modelo...")
                    self.current_model_index += 1
                    self.active_model = None # Força recriação na próxima iteração
                else:
                    # Outros erros (ex: JSON inválido) podem ser temporários, mas não adiantaria trocar modelo
                    break
                    
        return {
            "analise_textual": f"Erro na IA (Todos os modelos falharam): {last_error[:100]}...", 
            "delta_home": 0.0, 
            "delta_away": 0.0, 
            "tendencia_gols": "Neutra", 
            "tendencia_btts": "Duvidoso", 
            "risco_critico": False
        }

# --- SERVIÇO DE NOTÍCIAS (GE SNIPER FINAL V14) ---
class NewsService:
    def _normalize(self, text):
        """Remove acentos e coloca em minúsculas para comparação."""
        if not text: return ""
        return unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8').lower()

    def _scrape_page_content(self, url):
        """Entra na página e pega o texto real simulando um usuário comum."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code != 200: return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            for tag in soup(["script", "style", "nav", "footer", "header", "iframe", "svg", "button", "aside", "form"]):
                tag.decompose()
            
            # Limpeza extra de elementos de "Engagement" do GE
            for div in soup.find_all("div", class_=re.compile(r"(banner|widget|poll|sign-wall|comments)")):
                div.decompose()

            text_elements = soup.find_all(['p', 'li', 'h1', 'h2'])
            text_content = ' '.join([t.get_text().strip() for t in text_elements if len(t.get_text()) > 20])
            
            return text_content[:7000] 
        except Exception: return None

    def get_match_context(self, home_team, away_team, competition="futebol"):
        print(f"🕵️ Sniper Iniciado: {home_team} x {away_team}...")
        
        blocklist = [
            "loja", "camisa", "u20", "feminino", "basquete", "wikipedia", "konami", "efootball", 
            "pes 20", "fifa", "videogame", "forex", "amazon", "ingresso",
            "contratacoes", "mercado da bola", "quem chega", "quem sai", "reforcos", "vaivem", "transferencia"
        ]
        
        queries = [
            f"{home_team} x {away_team} escalação globo esporte",
            f"provável escalação {home_team} contra {away_team} uol",
            f"desfalques {home_team} x {away_team} onde assistir",
            f"pré-jogo {home_team} x {away_team}"
        ]
        
        context_text = ""
        unique_links = set()
        ddgs = DDGS()
        articles_read = 0
        
        home_norm = self._normalize(home_team)
        away_norm = self._normalize(away_team)

        for q in queries:
            if articles_read >= 2: break
            try:
                print(f"   🔎 Pesquisando: '{q}'...")
                results = ddgs.text(q, region='br-pt', safesearch='off', timelimit='w', max_results=3)
                
                if not results:
                    print("      -> Sem resultados recentes. Tentando busca absoluta...")
                    results = ddgs.text(q, region='br-pt', safesearch='off', max_results=3)

                if not results: continue

                for res in results:
                    if articles_read >= 2: break
                    link = res.get('href', '')
                    title = res.get('title', '')
                    
                    if link in unique_links: continue
                    unique_links.add(link)
                    
                    if "ge.globo.com" in link and "/noticia/" not in link and "/jogo/" not in link:
                        continue

                    full_check = self._normalize(title + " " + link)
                    if any(bad in full_check for bad in blocklist):
                        continue
                    
                    if home_norm not in full_check and away_norm not in full_check:
                        continue

                    print(f"   📖 Lendo: {title[:60]}...")
                    content = self._scrape_page_content(link)
                    
                    if content and len(content) > 300:
                        content_norm = self._normalize(content)
                        keywords = ["escalacao", "tecnico", "lesao", "suspenso", "provavel", "titular", "zagueiro", "atacante", "lateral"]
                        
                        if any(k in content_norm for k in keywords):
                            if "contratacao" in content_norm and "reforco" in content_norm and "2025" in content_norm:
                                print("      ⚠️ Texto parece ser sobre Mercado da Bola. Ignorando.")
                                continue
                                
                            context_text += f"\n=== MATÉRIA: {title} ===\nLINK: {link}\nTEXTO: {content}\n========================\n"
                            articles_read += 1
                            print("      ✅ Extraído com sucesso!")
                        else:
                            print("      ⚠️ Texto lido, mas sem termos táticos.")
            except Exception as e:
                print(f"   ⚠️ Erro na busca: {e}")
                continue

        if not context_text:
            return "Nenhuma notícia detalhada encontrada. IA usará estatística."
            
        return context_text