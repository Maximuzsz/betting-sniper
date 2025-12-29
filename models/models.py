import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.types import JSON
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database connection URL (from .env or defaults for localhost)
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
    external_id = Column(String, unique=True, nullable=True)  # The Odds API ID
    league_key = Column(String)  # e.g.: soccer_brazil_campeonato
    home_team = Column(String, nullable=False)
    away_team = Column(String, nullable=False)
    commence_time = Column(DateTime)
    
    # Relationship
    predictions = relationship("Prediction", back_populates="match")


class Prediction(Base):
    __tablename__ = 'predictions'
    
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey('matches.id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Inputs used in analysis
    input_home_goals_avg = Column(Float)
    input_home_conceded_avg = Column(Float)
    input_away_goals_avg = Column(Float)
    input_away_conceded_avg = Column(Float)
    
    # Bookmaker odds at bet time
    bookmaker_name = Column(String)
    odd_home_used = Column(Float)
    odd_draw_used = Column(Float)
    odd_away_used = Column(Float)
    
    # Algorithm results
    math_prob_home = Column(Float)       # Pure Poisson probability
    ai_delta_adjustment = Column(Float)  # AI adjustment (e.g.: -0.05)
    final_prob_home = Column(Float)      # Final probability
    
    expected_value = Column(Float)       # Calculated EV
    is_value_bet = Column(Boolean)       # True if EV > 0
    
    # Full JSON returned by Gemini (Reasoning)
    ai_analysis_json = Column(JSON) 
    
    match = relationship("Match", back_populates="predictions")


def init_db():
    """Helper function to create database tables."""
    try:
        # Test connection before creating tables
        with engine.connect() as conn:
            pass
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        error_msg = str(e)
        if "does not exist" in error_msg or "role" in error_msg.lower():
            raise Exception(
                f"PostgreSQL connection error: User '{DB_USER}' does not exist.\n"
                f"Run the script: psql -U postgres -f setup_db.sql\n"
                f"Or adjust POSTGRES_USER and POSTGRES_PASSWORD in .env file"
            ) from e
        raise


if __name__ == "__main__":
    print("Creating database tables...")
    init_db()
    print("Tables created successfully!")
