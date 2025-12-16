-- Script para criar o usuário e banco de dados
-- Execute com: psql -U postgres -f setup_db.sql

-- Cria o usuário admin se não existir
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'admin') THEN
        CREATE USER admin WITH PASSWORD 'admin123';
        ALTER USER admin CREATEDB;
    END IF;
END
$$;

-- Cria o banco de dados se não existir
SELECT 'CREATE DATABASE sniper_db OWNER admin'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'sniper_db')\gexec

-- Concede todas as permissões
GRANT ALL PRIVILEGES ON DATABASE sniper_db TO admin;

