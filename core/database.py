import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from typing import Optional, Dict

class DatabaseManager:
    """
    Gestor de ligação ao PostgreSQL para armazenamento e cache de dados.
    """
    def __init__(self):
        # Lê a string de ligação do ficheiro .env
        self.db_url = os.getenv("DATABASE_URL")
        if not self.db_url:
            raise ValueError("DATABASE_URL não está definida no ficheiro .env")

    def _get_connection(self):
        return psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)

    def get_cached_team_stats(self, team_id: int, league_id: int, season: int, max_age_days: int = 7) -> Optional[Dict[str, float]]:
        """
        Procura as estatísticas na base de dados. 
        Retorna None se não existir ou se o registo for mais antigo do que max_age_days.
        """
        query = """
            SELECT home_xg, away_xg, last_updated 
            FROM team_season_stats 
            WHERE team_id = %s AND league_id = %s AND season = %s
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (team_id, league_id, season))
                    result = cursor.fetchone()

                    if result:
                        # Verifica se a cache expirou
                        age = datetime.now() - result['last_updated']
                        if age <= timedelta(days=max_age_days):
                            return {
                                "home_xg": float(result['home_xg']),
                                "away_xg": float(result['away_xg'])
                            }
                        else:
                            print(f"🔄 Cache expirada para a equipa {team_id}. A necessitar de nova requisição.")
            return None
            
        except psycopg2.Error as e:
            print(f"❌ Erro ao ler da base de dados: {e}")
            return None

    def upsert_team_stats(self, team_id: int, league_id: int, season: int, home_xg: float, away_xg: float):
        """
        Insere ou atualiza (Upsert) as estatísticas da equipa na base de dados.
        """
        query = """
            INSERT INTO team_season_stats (team_id, league_id, season, home_xg, away_xg, last_updated)
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (team_id, league_id, season) 
            DO UPDATE SET 
                home_xg = EXCLUDED.home_xg,
                away_xg = EXCLUDED.away_xg,
                last_updated = CURRENT_TIMESTAMP;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (team_id, league_id, season, home_xg, away_xg))
                conn.commit()
                print(f"💾 Estatísticas guardadas com sucesso para a equipa {team_id}.")
        except psycopg2.Error as e:
            print(f"❌ Erro ao guardar na base de dados: {e}")
    
    def create_user(self, name: str, email: str, password_hash: str, initial_bankroll: float) -> Optional[int]:
        """Cria um novo usuário com senha criptografada."""
        query = """
            INSERT INTO users (name, email, password_hash, bankroll) 
            VALUES (%s, %s, %s, %s) RETURNING id;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (name, email, password_hash, initial_bankroll))
                    user_id = cursor.fetchone()['id']
                conn.commit()
                return user_id
        except psycopg2.Error as e:
            print(f"❌ Erro ao criar usuário: {e}")
            return None

    def get_user_by_email(self, email: str) -> Optional[dict]:
        """Busca o usuário inteiro pelo email para fazer o login."""
        query = "SELECT id, name, email, password_hash, bankroll FROM users WHERE email = %s;"
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (email,))
                    return cursor.fetchone()
        except psycopg2.Error:
            return None
        
    def get_user_bankroll(self, user_id: int) -> float:
        """Busca o saldo atual do usuário."""
        query = "SELECT bankroll FROM users WHERE id = %s;"
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (user_id,))
                    result = cursor.fetchone()
                    return float(result['bankroll']) if result else 0.0
        except psycopg2.Error:
            return 0.0

    def register_bet(self, user_id: int, match_string: str, market: str, odd: float, stake: float, ev: float, ai_justification: str):
        """Registra a aposta no sistema e desconta o valor da banca do usuário."""
        insert_bet_query = """
            INSERT INTO bets (user_id, match_string, market, odd_taken, stake, expected_ev, ai_justification)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        update_bankroll_query = """
            UPDATE users SET bankroll = bankroll - %s WHERE id = %s;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Registra o bilhete
                    cursor.execute(insert_bet_query, (user_id, match_string, market, odd, stake, ev, ai_justification))
                    # Desconta a stake da banca (o dinheiro saiu para a casa de apostas)
                    cursor.execute(update_bankroll_query, (stake, user_id))
                conn.commit()
                print(f"✅ Aposta registrada! R$ {stake} debitados da banca do usuário {user_id}.")
        except psycopg2.Error as e:
            print(f"❌ Erro ao registrar aposta: {e}")

    def resolve_bet(self, bet_id: int, status: str):
        """
        Resolve a aposta (WON ou LOST). Se ganhou, devolve a stake + lucro para a banca.
        status deve ser 'WON' ou 'LOST'.
        """
        get_bet_query = "SELECT user_id, odd_taken, stake FROM bets WHERE id = %s AND status = 'PENDING';"
        update_bet_query = "UPDATE bets SET status = %s, profit = %s WHERE id = %s;"
        update_bankroll_query = "UPDATE users SET bankroll = bankroll + %s WHERE id = %s;"

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(get_bet_query, (bet_id,))
                    bet = cursor.fetchone()
                    
                    if not bet:
                        print("⚠️ Aposta não encontrada ou já resolvida.")
                        return

                    profit = 0.0
                    total_return = 0.0

                    if status == 'WON':
                        # Lucro puro = (Stake * Odd) - Stake
                        total_return = float(bet['stake'] * bet['odd_taken'])
                        profit = total_return - float(bet['stake'])
                    elif status == 'LOST':
                        profit = -float(bet['stake'])
                        total_return = 0.0 # Perdeu tudo

                    # Atualiza o status da aposta
                    cursor.execute(update_bet_query, (status, profit, bet_id))
                    
                    # Se ganhou, devolve o retorno total para a banca do usuário
                    if status == 'WON':
                        cursor.execute(update_bankroll_query, (total_return, bet['user_id']))
                        
                conn.commit()
                print(f"🏁 Aposta {bet_id} resolvida como {status}. Lucro/Prejuízo: R$ {profit:.2f}")
        except psycopg2.Error as e:
            print(f"❌ Erro ao resolver a aposta: {e}")
            
    def get_pending_bets(self):
        """Busca todas as apostas que ainda não foram resolvidas."""
        query = "SELECT * FROM bets WHERE status = 'PENDING';"
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    return cursor.fetchall()
        except Exception as e:
            print(f"❌ Erro ao buscar apostas pendentes: {e}")
            return []

    def update_bet_status(self, bet_id: int, status: str, profit: float, user_id: int):
        """
        Atualiza o status da aposta e ajusta a banca do usuário em caso de vitória.
        """
        # Se ganhou, o lucro é (Stake * Odd) - Stake. 
        # No 'WON', devolvemos a Stake + o Lucro para a banca.
        # No 'LOST', o dinheiro já saiu no momento da aposta, então não fazemos nada na banca.
        
        query_bet = "UPDATE bets SET status = %s, profit = %s WHERE id = %s;"
        query_user = "UPDATE users SET bankroll = bankroll + %s WHERE id = %s;"
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # 1. Atualiza o bilhete
                    cursor.execute(query_bet, (status, profit, bet_id))
                    
                    # 2. Se ganhou, credita o valor total (Stake + Lucro) de volta
                    if status == 'WON':
                        # Se a aposta foi de 10 e a odd 2.0, o lucro é 10. 
                        # Devolvemos 20 (stake original que foi tirada + lucro).
                        total_return = profit + self._get_stake_from_bet(bet_id)
                        cursor.execute(query_user, (total_return, user_id))
                    
                    conn.commit()
                    return True
        except Exception as e:
            print(f"❌ Erro ao atualizar status da bet {bet_id}: {e}")
            return False

    def _get_stake_from_bet(self, bet_id: int) -> float:
        """Auxiliar para saber quanto foi a stake original."""
        query = "SELECT stake FROM bets WHERE id = %s;"
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (bet_id,))
                res = cursor.fetchone()
                return float(res['stake']) if res else 0.0
            
    def get_dashboard_stats(self, user_id: int):
        """Calcula as métricas de performance do usuário e da IA."""
        query = """
            SELECT 
                COALESCE(SUM(profit), 0) as total_profit,
                COUNT(*) FILTER (WHERE status != 'PENDING') as total_resolved,
                COUNT(*) FILTER (WHERE status = 'WON') as total_wins,
                -- Cálculo da assertividade global da IA (todos os registros WON vs LOST)
                (SELECT 
                    CASE 
                        WHEN COUNT(*) FILTER (WHERE status != 'PENDING') = 0 THEN 0
                        ELSE (COUNT(*) FILTER (WHERE status = 'WON') * 100 / COUNT(*) FILTER (WHERE status != 'PENDING'))
                    END
                FROM bets) as sniper_global_accuracy
            FROM bets 
            WHERE user_id = %s;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (user_id,))
                    row = cursor.fetchone()
                    
                    total_resolved = row['total_resolved']
                    total_wins = row['total_wins']
                    
                    # Cálculo do Win Rate do usuário logado
                    win_rate = (total_wins * 100 / total_resolved) if total_resolved > 0 else 0
                    
                    return {
                        "total_profit": float(row['total_profit']),
                        "win_rate": round(win_rate, 1),
                        "sniper_accuracy": round(float(row['sniper_global_accuracy']), 1),
                        "total_bets": total_resolved
                    }
        except Exception as e:
            print(f"❌ Erro ao calcular stats: {e}")
            return {"total_profit": 0, "win_rate": 0, "sniper_accuracy": 0, "total_bets": 0}
        
    def get_user_dashboard_metrics(self, user_id: int):
        """
        Calcula Lucro Total, Win Rate, Assertividade Global da IA e Volume de apostas.
        """
        query = """
            SELECT 
                -- 1. Lucro Total (Apenas de apostas resolvidas)
                COALESCE(SUM(profit), 0) as total_profit,
                
                -- 2. Total de apostas que não estão mais pendentes
                COUNT(*) FILTER (WHERE status != 'PENDING') as total_resolved,
                
                -- 3. Total de vitórias
                COUNT(*) FILTER (WHERE status = 'WON') as total_wins,
                
                -- 4. Assertividade Global do Sniper (Métrica de autoridade do App)
                (SELECT 
                    CASE 
                        WHEN COUNT(*) FILTER (WHERE status != 'PENDING') = 0 THEN 0
                        ELSE (COUNT(*) FILTER (WHERE status = 'WON') * 100 / COUNT(*) FILTER (WHERE status != 'PENDING'))
                    END
                 FROM bets) as sniper_global_accuracy
            FROM bets 
            WHERE user_id = %s;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (user_id,))
                    row = cursor.fetchone()
                    
                    total_resolved = row['total_resolved']
                    total_wins = row['total_wins']
                    
                    # Cálculo do Win Rate individual
                    win_rate = (total_wins * 100 / total_resolved) if total_resolved > 0 else 0
                    
                    return {
                        "total_profit": float(row['total_profit']),
                        "win_rate": round(win_rate, 1),
                        "sniper_accuracy": round(float(row['sniper_global_accuracy']), 1),
                        "total_bets": total_resolved
                    }
        except Exception as e:
            print(f"❌ Erro ao processar dashboard stats: {e}")
            return {"total_profit": 0, "win_rate": 0, "sniper_accuracy": 0, "total_bets": 0}