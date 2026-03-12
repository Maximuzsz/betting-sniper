import requests
from datetime import datetime
from typing import List

class NewsScout:
    """
    Serviço responsável por buscar o contexto atualizado do jogo, 
    focado em escalações, desfalques e motivação.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.endpoint = "https://google.serper.dev/search"
        
        # Blacklist: Filtra ruídos que não afetam a odd do jogo de hoje
        self.blacklist: List[str] = [
            "transferência", "mercado da bola", "venda", "contratação", 
            "namorada", "polêmica", "salário", "fofoca", "histórico de confrontos",
            "renovação"
        ]

    def fetch_match_context(self, home_team: str, away_team: str) -> str:
        """
        Busca e filtra as notícias mais relevantes do confronto.
        """
        hoje = datetime.now().strftime('%d/%m/%Y')
        # A query é a alma do negócio: buscamos a dor dos times (lesões/desfalques)
        query = f"{home_team} x {away_team} provável escalação desfalques lesão {hoje}"
        
        payload = {
            "q": query,
            "gl": "br",       # Foco em resultados do Brasil (GE, UOL, etc)
            "hl": "pt-br",    # Idioma
            "num": 10         # Puxamos 10 resultados para sobrar os bons após o filtro
        }
        
        headers = {
            'X-API-KEY': self.api_key, 
            'Content-Type': 'application/json'
        }

        try:
            # Timeout de 10s para não travar o fluxo do Sniper
            response = requests.post(self.endpoint, json=payload, headers=headers, timeout=10)
            response.raise_for_status() 
            data = response.json()
            
            valid_snippets = []
            
            for item in data.get('organic', []):
                snippet = item.get('snippet', '')
                snippet_lower = snippet.lower()
                
                # O Pulo do Gato: Validação contra a blacklist
                if not any(bad_word in snippet_lower for bad_word in self.blacklist):
                    valid_snippets.append(snippet)
                    
            if not valid_snippets:
                return "Nenhuma notícia relevante ou de desfalque encontrada para o jogo de hoje."
                
            # Retorna as 5 melhores notícias consolidadas
            context_text = "\n- ".join(valid_snippets[:5])
            return f"- {context_text}"
            
        except requests.exceptions.RequestException as e:
            return f"Erro de rede ao buscar notícias: {str(e)}"
        except Exception as e:
            return f"Erro inesperado no NewsScout: {str(e)}"