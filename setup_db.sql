-- ATENÇÃO: Os comandos DROP apagam os dados existentes. 
-- Use para resetar o ambiente e garantir a estrutura correta.
DROP TABLE IF EXISTS bets;
DROP TABLE IF EXISTS team_season_stats;
DROP TABLE IF EXISTS users;

-- 1. Tabela de Usuários (Banca e Autenticação)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL, -- Removido o DEFAULT vazio, a senha é obrigatória
    bankroll NUMERIC(10,2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabela de Apostas (Histórico e Gestão de banca)
CREATE TABLE bets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    match_string VARCHAR(200) NOT NULL,
    market VARCHAR(50) NOT NULL,
    odd_taken NUMERIC(5,2) NOT NULL,
    stake NUMERIC(10,2) NOT NULL,
    expected_ev NUMERIC(5,2),
    status VARCHAR(20) DEFAULT 'PENDING',
    profit NUMERIC(10,2) DEFAULT 0.00,
    ai_justification TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabela de Cache de Estatísticas (Performance e Economia de API)
CREATE TABLE team_season_stats (
    team_id INTEGER,
    league_id INTEGER,
    season INTEGER,
    home_xg NUMERIC(5,2) NOT NULL,
    away_xg NUMERIC(5,2) NOT NULL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id, league_id, season)
);

-- Índices para otimização de buscas
CREATE INDEX idx_bets_user_status ON bets(user_id, status);
CREATE INDEX idx_team_stats ON team_season_stats(team_id, league_id, season);