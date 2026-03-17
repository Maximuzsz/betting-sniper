import time
from typing import List
from datetime import datetime

class BetSettler:
    def __init__(self, db_manager, stats_service):
        self.db = db_manager
        self.api = stats_service

    def run_resolution_cycle(self):
        print(f"[{datetime.now()}] 🔍 Sniper verificando resultados...")
        pending_bets = self.db.get_pending_bets()
        
        if not pending_bets:
            print("ℹ️ Sem alvos pendentes para resolução.")
            return

        for bet in pending_bets:
            try:
                # Aqui você chama a sua API-Football para pegar o placar
                match_data = self.api.get_match_result(bet['fixture_id'])
                
                if match_data and match_data['status'] in ['FT', 'AET', 'PEN']:
                    self.resolve_bet(bet, match_data)
            except Exception as e:
                print(f"⚠️ Falha ao resolver fixture {bet['fixture_id']}: {e}")

    def resolve_bet(self, bet, result):
        # Lógica simples para o mercado 'DRAW' (Empate)
        is_winner = False
        home_goals = result['goals_home']
        away_goals = result['goals_away']

        if bet['market'] == 'DRAW' and home_goals == away_goals:
            is_winner = True
        elif bet['market'] == 'HOME' and home_goals > away_goals:
            is_winner = True
        elif bet['market'] == 'AWAY' and away_goals > home_goals:
            is_winner = True

        status = 'WON' if is_winner else 'LOST'
        profit = (bet['stake'] * bet['odd_taken']) - bet['stake'] if is_winner else -bet['stake']

        # Atualiza no banco: status, profit e soma o lucro à banca do usuário
        self.db.update_bet_status(bet['id'], status, profit, bet['user_id'])
        print(f"🎯 Bet {bet['id']} resolvida como {status}. Profit: R$ {profit}")
        