import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.types import JSON
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Configuração da URL de Conexão (Pega do .env ou usa default para localhost)
DB_USER = os.getenv("POSTGRES_USER", "admin")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "admin123")
DB_NAME = os.getenv("POSTGRES_DB", "sniper_db")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Match(Base):
    __tablename__ = 'matches'
    
    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, nullable=True) # ID da The Odds API
    league_key = Column(String) # ex: soccer_brazil_campeonato
    home_team = Column(String, nullable=False)
    away_team = Column(String, nullable=False)
    commence_time = Column(DateTime)
    
    # Relacionamento
    predictions = relationship("Prediction", back_populates="match")

class Prediction(Base):
    __tablename__ = 'predictions'
    
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey('matches.id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Inputs usados na análise
    input_home_goals_avg = Column(Float)
    input_home_conceded_avg = Column(Float)
    input_away_goals_avg = Column(Float)
    input_away_conceded_avg = Column(Float)
    
    # Odds da Casa no momento da aposta
    bookmaker_name = Column(String)
    odd_home_used = Column(Float)
    odd_draw_used = Column(Float)
    odd_away_used = Column(Float)
    
    # Resultados do Algoritmo
    math_prob_home = Column(Float)       # Probabilidade Poisson Pura
    ai_delta_adjustment = Column(Float)  # Ajuste da IA (ex: -0.05)
    final_prob_home = Column(Float)      # Probabilidade Final
    
    expected_value = Column(Float)       # EV Calculado
    is_value_bet = Column(Boolean)       # Se EV > 0
    
    # Armazena o JSON completo que o Gemini retornou (Reasoning)
    ai_analysis_json = Column(JSON) 
    
    match = relationship("Match", back_populates="predictions")

# Função helper para criar as tabelas
def init_db():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    print("Criando tabelas no Banco de Dados...")
    init_db()
    print("Tabelas criadas com sucesso!")