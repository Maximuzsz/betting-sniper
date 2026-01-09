import os
import urllib.parse
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text, inspect, text
from sqlalchemy.types import JSON
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# --- LÓGICA DE CONEXÃO ROBUSTA ---
def get_database_url():
    url = os.getenv("DATABASE_URL")
    if not url:
        db_user, db_pass, db_name, db_host, db_port = "admin", "admin123", "sniper_db", "localhost", "5432"
        url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url

DATABASE_URL = get_database_url()

try:
    connect_args = {"sslmode": "require"} if "neon.tech" in DATABASE_URL or "sslmode" in DATABASE_URL else {}
    
    if DATABASE_URL:
        # pool_pre_ping=True evita quedas de conexão em bancos na nuvem (Render, Neon, etc)
        engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True, pool_recycle=1800)
    else:
        engine = create_engine("sqlite:///sniper.db", connect_args={"check_same_thread": False})
except Exception as e:
    print(f"❌ Erro na configuração da Engine: {e}")
    raise e

Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- MODELOS ---

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    kelly_fraction = Column(Float, default=0.1, nullable=False)
    
    wallet = relationship("Wallet", back_populates="user", uselist=False)
    predictions = relationship("Prediction", back_populates="user")

class Wallet(Base):
    """Tabela para gerenciar a Banca (Saldo) de um usuário."""
    __tablename__ = 'wallet'
    id = Column(Integer, primary_key=True, index=True)
    balance = Column(Float, default=1000.0)
    updated_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    
    user = relationship("User", back_populates="wallet")

class Match(Base):
    __tablename__ = 'matches'
    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, nullable=True)
    league_key = Column(String)
    home_team = Column(String, nullable=False)
    away_team = Column(String, nullable=False)
    commence_time = Column(DateTime)
    
    predictions = relationship("Prediction", back_populates="match")

class Prediction(Base):
    __tablename__ = 'predictions'
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey('matches.id'))
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # ... (demais campos)
    input_home_goals_avg = Column(Float)
    input_home_conceded_avg = Column(Float)
    input_away_goals_avg = Column(Float)
    input_away_conceded_avg = Column(Float)
    bookmaker_name = Column(String)
    odd_home_used = Column(Float)
    odd_draw_used = Column(Float)
    odd_away_used = Column(Float)
    math_prob_home = Column(Float)
    ai_delta_adjustment = Column(Float)
    final_prob_home = Column(Float)
    expected_value = Column(Float)
    is_value_bet = Column(Boolean)
    ai_analysis_json = Column(JSON)
    stake = Column(Float, default=0.0)
    selected_team = Column(String)
    status = Column(String, default="PENDING")
    
    match = relationship("Match", back_populates="predictions")
    user = relationship("User", back_populates="predictions")

    def calculate_profit(self):
        if self.status == 'GREEN':
            odd_used = self.odd_home_used if self.final_prob_home > 0.5 else self.odd_away_used
            return (self.stake * odd_used) - self.stake
        elif self.status == 'RED':
            return -self.stake
        return 0.0

# Variável global para evitar execução repetida da migração a cada rerun do Streamlit
_db_initialized = False

def init_db():
    global _db_initialized
    if _db_initialized:
        return

    try:
        with engine.connect() as connection:
            print("✅ Banco de Dados conectado!")
            Base.metadata.create_all(bind=engine)
            print("Sync de tabelas básicas concluído.")

            inspector = inspect(engine)
            
            # Função auxiliar para adicionar colunas
            def add_column_if_not_exists(table_name, column_name, column_definition):
                if inspector.has_table(table_name):
                    columns = [c['name'] for c in inspector.get_columns(table_name)]
                    if column_name not in columns:
                        print(f"⚠️ Adicionando coluna '{column_name}' à tabela '{table_name}'...")
                        connection.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}'))

            with connection.begin(): # Transação para DDL
                # Tabela Users
                add_column_if_not_exists('users', 'kelly_fraction', 'FLOAT DEFAULT 0.1')

                # Tabela Predictions
                add_column_if_not_exists('predictions', 'stake', 'FLOAT DEFAULT 0.0')
                add_column_if_not_exists('predictions', 'status', 'VARCHAR(50) DEFAULT \'PENDING\'')
                add_column_if_not_exists('predictions', 'selected_team', 'VARCHAR(10)')
                add_column_if_not_exists('predictions', 'user_id', 'INTEGER REFERENCES users(id)')
                
                # Tabela Wallet
                add_column_if_not_exists('wallet', 'user_id', 'INTEGER REFERENCES users(id)')

            print("✅ Sincronização com o Banco de Dados completa!")
            _db_initialized = True

    except Exception as e:
        print(f"❌ Erro Crítico DB: {e}")

if __name__ == "__main__":
    init_db()