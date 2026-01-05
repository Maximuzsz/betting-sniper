import os
import urllib.parse
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.types import JSON
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# --- LÓGICA DE CONEXÃO ROBUSTA ---
def get_database_url():
    # 1. Tenta pegar a URL completa (NeonDB/Render)
    url = os.getenv("DATABASE_URL")
    
    # 2. Se não existir, tenta montar a local (Docker/Localhost)
    if not url:
        db_user = os.getenv("POSTGRES_USER", "admin")
        db_pass = os.getenv("POSTGRES_PASSWORD", "admin123")
        db_name = os.getenv("POSTGRES_DB", "sniper_db")
        db_host = os.getenv("POSTGRES_HOST", "localhost")
        db_port = os.getenv("POSTGRES_PORT", "5432")
        url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    
    # Correção de compatibilidade (postgres:// -> postgresql://)
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
        
    return url

DATABASE_URL = get_database_url()

# Log de Conexão (Mascarando senha para segurança)
if DATABASE_URL:
    try:
        parsed_url = urllib.parse.urlparse(DATABASE_URL)
        masked_netloc = f"{parsed_url.username}:******@{parsed_url.hostname}:{parsed_url.port}"
        print(f"🔌 Conectando ao Banco de Dados: {masked_netloc}/{parsed_url.path.lstrip('/')}")
    except:
        print("🔌 Conectando ao Banco de Dados (URL mascarada)...")

# Configuração da Engine
try:
    connect_args = {}
    # NeonDB exige SSL
    if "neon.tech" in DATABASE_URL or "sslmode" in DATABASE_URL:
        connect_args = {"sslmode": "require"}

    engine = create_engine(DATABASE_URL, connect_args=connect_args)
    
except Exception as e:
    print(f"❌ Erro na configuração da Engine: {e}")
    raise e

Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- MODELOS ---
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
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Inputs
    input_home_goals_avg = Column(Float)
    input_home_conceded_avg = Column(Float)
    input_away_goals_avg = Column(Float)
    input_away_conceded_avg = Column(Float)
    
    # Odds
    bookmaker_name = Column(String)
    odd_home_used = Column(Float)
    odd_draw_used = Column(Float)
    odd_away_used = Column(Float)
    
    # Resultados
    math_prob_home = Column(Float)
    ai_delta_adjustment = Column(Float)
    final_prob_home = Column(Float)
    
    expected_value = Column(Float)
    is_value_bet = Column(Boolean)
    
    # IA Analysis
    ai_analysis_json = Column(JSON) 
    
    match = relationship("Match", back_populates="predictions")

# Função helper para criar as tabelas
def init_db():
    try:
        print("🛠️ Verificando tabelas no banco...")
        # Testa conexão real
        with engine.connect() as conn:
            pass
        # Cria tabelas se não existirem
        Base.metadata.create_all(bind=engine)
        print("✅ Banco de Dados conectado e sincronizado com sucesso!")
    except Exception as e:
        print(f"❌ ERRO CRÍTICO ao conectar/criar tabelas: {e}")
        print("Dica: Verifique se o IP da sua máquina está permitido no Dashboard do NeonDB se estiver usando nuvem.")
        raise e
        
if __name__ == "__main__":
    init_db()