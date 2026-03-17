import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from typing import Optional, Dict, List

class DatabaseManager:
    """
    Gestor de ligação ao PostgreSQL para armazenamento e cache de dados.
    """
    def __init__(self):
        # Lê a string de ligação do ficheiro .env
        self.db_url = os.getenv("DATABASE_URL")
        if not self.db_url:
            raise ValueError("DATABASE_URL não está definida no ficheiro .env")
            
        # Garante que as tabelas existem ao iniciar
        self._create_tables()

    def _get_connection(self):
        return psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)

    def _create_tables(self):
        """
        Faz o check no boot da API. Cria as tabelas necessárias apenas se elas não existirem.
        Totalmente seguro para os dados (Non-Destructive).
        """
        
        # 1. Tabela de Usuários
        query_users = """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            bankroll NUMERIC(10, 2) DEFAULT 0.0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """

        # 2. Tabela de Estatísticas (Poisson)
        query_stats = """
        CREATE TABLE IF NOT EXISTS team_season_stats (
            team_id INT,
            league_id INT,
            season INT,
            home_xg NUMERIC(5, 2),
            away_xg NUMERIC(5, 2),
            last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (team_id, league_id, season)
        );
        """

        # 3. Tabela de Bilhetes de Aposta (Com vínculo ao Usuário)
        query_bets = """
        CREATE TABLE IF NOT EXISTS bets (
            id SERIAL PRIMARY KEY,
            user_id INT REFERENCES users(id) ON DELETE CASCADE,
            match_string VARCHAR(255) NOT NULL,
            market VARCHAR(100) NOT NULL,
            odd_taken NUMERIC(5, 2) NOT NULL,
            stake NUMERIC(10, 2) NOT NULL,
            expected_ev NUMERIC(5, 2),
            ai_justification TEXT,
            status VARCHAR(20) DEFAULT 'PENDING',
            profit NUMERIC(10, 2) DEFAULT 0.0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """

        # 4. Tabela de Cache dos Jogos Diários
        query_matches = """
        CREATE TABLE IF NOT EXISTS upcoming_matches (
            fixture_id BIGINT PRIMARY KEY,
            date TIMESTAMP WITH TIME ZONE,
            league_id INT,
            league_name VARCHAR(255),
            season INT,
            home_team_id INT,
            home_team_name VARCHAR(255),
            home_team_logo VARCHAR(255),
            away_team_id INT,
            away_team_name VARCHAR(255),
            away_team_logo VARCHAR(255)
        );
        """

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Executa as queries na ordem certa (users tem que existir antes de bets)
                    cursor.execute(query_users)
                    cursor.execute(query_stats)
                    cursor.execute(query_bets)
                    cursor.execute(query_matches)
                conn.commit()
                print("✅ [DB CHECK] Estrutura verificada com sucesso. Dados preservados.")
        except psycopg2.Error as e:
            print(f"❌ Erro crítico ao verificar/criar tabelas: {e}")

    # --- NOVAS FUNÇÕES: CACHE DE JOGOS DIÁRIOS ---

    def save_upcoming_matches(self, matches: list):
        """Salva a lista de jogos no banco, atualizando se já existir."""
        if not matches:
            return
            
        query = """
            INSERT INTO upcoming_matches 
            (fixture_id, date, league_id, league_name, season, home_team_id, home_team_name, home_team_logo, away_team_id, away_team_name, away_team_logo)
            VALUES (%(fixture_id)s, %(date)s, %(league_id)s, %(league_name)s, %(season)s, %(home_team_id)s, %(home_team_name)s, %(home_team_logo)s, %(away_team_id)s, %(away_team_name)s, %(away_team_logo)s)
            ON CONFLICT (fixture_id) DO UPDATE SET
                date = EXCLUDED.date;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.executemany(query, matches)
                conn.commit()
        except Exception as e:
            print(f"❌ Erro ao salvar matches no banco: {e}")

    def get_matches_by_date(self, date_str: str) -> list:
        """Busca os jogos salvos no banco para uma data específica."""
        query = """
            SELECT * FROM upcoming_matches 
            WHERE DATE(date AT TIME ZONE 'America/Sao_Paulo') = %s
            ORDER BY date ASC;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (date_str,))
                    rows = cursor.fetchall()
                    
                    # Converte a data do BD para string ISO para o Frontend (React Native) não quebrar
                    for row in rows:
                        if 'date' in row and row['date']:
                            row['date'] = row['date'].isoformat()
                    return rows
        except Exception as e:
            print(f"❌ Erro ao buscar matches do banco: {e}")
            return []

    # --- FUNÇÕES ORIGINAIS MANTIDAS INTACTAS ---

    def get_cached_team_stats(self, team_id: int, league_id: int, season: int, max_age_days: int = 7) -> Optional[Dict[str, float]]:
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
        query = "SELECT id, name, email, password_hash, bankroll FROM users WHERE email = %s;"
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (email,))
                    return cursor.fetchone()
        except psycopg2.Error:
            return None
        
    def get_user_bankroll(self, user_id: int) -> float:
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
                    cursor.execute(insert_bet_query, (user_id, match_string, market, odd, stake, ev, ai_justification))
                    cursor.execute(update_bankroll_query, (stake, user_id))
                conn.commit()
                print(f"✅ Aposta registrada! R$ {stake} debitados da banca do usuário {user_id}.")
        except psycopg2.Error as e:
            print(f"❌ Erro ao registrar aposta: {e}")

    def resolve_bet(self, bet_id: int, status: str):
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
                        total_return = float(bet['stake'] * bet['odd_taken'])
                        profit = total_return - float(bet['stake'])
                    elif status == 'LOST':
                        profit = -float(bet['stake'])
                        total_return = 0.0

                    cursor.execute(update_bet_query, (status, profit, bet_id))
                    
                    if status == 'WON':
                        cursor.execute(update_bankroll_query, (total_return, bet['user_id']))
                        
                conn.commit()
                print(f"🏁 Aposta {bet_id} resolvida como {status}. Lucro/Prejuízo: R$ {profit:.2f}")
        except psycopg2.Error as e:
            print(f"❌ Erro ao resolver a aposta: {e}")
            
    def get_pending_bets(self):
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
        query_bet = "UPDATE bets SET status = %s, profit = %s WHERE id = %s;"
        query_user = "UPDATE users SET bankroll = bankroll + %s WHERE id = %s;"
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query_bet, (status, profit, bet_id))
                    if status == 'WON':
                        total_return = profit + self._get_stake_from_bet(bet_id)
                        cursor.execute(query_user, (total_return, user_id))
                    conn.commit()
                    return True
        except Exception as e:
            print(f"❌ Erro ao atualizar status da bet {bet_id}: {e}")
            return False

    def _get_stake_from_bet(self, bet_id: int) -> float:
        query = "SELECT stake FROM bets WHERE id = %s;"
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (bet_id,))
                res = cursor.fetchone()
                return float(res['stake']) if res else 0.0
            
    def get_dashboard_stats(self, user_id: int):
        query = """
            SELECT 
                COALESCE(SUM(profit), 0) as total_profit,
                COUNT(*) FILTER (WHERE status != 'PENDING') as total_resolved,
                COUNT(*) FILTER (WHERE status = 'WON') as total_wins,
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
        query = """
            SELECT 
                COALESCE(SUM(profit), 0) as total_profit,
                COUNT(*) FILTER (WHERE status != 'PENDING') as total_resolved,
                COUNT(*) FILTER (WHERE status = 'WON') as total_wins,
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