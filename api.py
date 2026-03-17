import os
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from dotenv import load_dotenv
from datetime import datetime
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from threading import Thread
import time

# Importando os nossos serviços
from services.news_scout import NewsScout
from services.math_engine import PoissonEngine
from services.ai_analyst import AIAnalyst
from core.decision import DecisionEngine
from core.database import DatabaseManager
from services.stats_service import StatsService
from services.settler_service import BetSettler

# Importando o módulo de segurança que criamos
from core.security import verify_password, get_password_hash, create_access_token
import jwt
from jwt.exceptions import PyJWTError

load_dotenv()

# Fail-Fast de segurança
if not os.getenv("GEMINI_API_KEY") or not os.getenv("DATABASE_URL"):
    raise ValueError("❌ Variáveis de ambiente faltando! Verifique seu arquivo .env")

app = FastAPI(title="Betting Sniper API", version="2.0")


app.add_middleware(
    CORSMiddleware,
    # Substitua o ["*"] pelas origens exatas. 
    allow_origins=[
        "http://localhost:8081", 
        "http://127.0.0.1:8081",
        "https://betting-sniper.onrender.com" # A própria API (útil para o Swagger UI)
    ], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db_manager = DatabaseManager()
scout = NewsScout(api_key=os.getenv("SERPER_API_KEY"))
math_engine = PoissonEngine()
ai_analyst = AIAnalyst(api_key=os.getenv("GEMINI_API_KEY"))
decision_engine = DecisionEngine(kelly_fraction=0.25, min_ev=0.05)
stats_service = StatsService(api_key=os.getenv("API_SPORTS_KEY"))

# --- CONFIGURAÇÃO DE SEGURANÇA (O Cadeado) ---
# Diz ao FastAPI que a rota para pegar o token se chama "/login"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Função que atua como o "Leão de Chácara" em cada rota protegida
def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Tenta abrir o token
        SECRET_KEY = os.getenv("JWT_SECRET_KEY", "sniper_secreto_super_seguro_2026")
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except PyJWTError:
        raise credentials_exception
        
    user = db_manager.get_user_by_email(email)
    if user is None:
        raise credentials_exception
    return user

def start_settler_loop():
    import time # Import local para garantir
    settler = BetSettler(db_manager, stats_service)
    while True:
        try:
            settler.run_resolution_cycle()
        except Exception as e:
            print(f"⚠️ Erro no ciclo do settler: {e}")
        
        # Dorme por 30 minutos em vez de 1 hora para o dashboard atualizar mais rápido
        time.sleep(1800)

# --- MODELOS ---
class UserCreate(BaseModel):
    name: str
    email: str
    password: str  # Adicionamos a senha no cadastro
    initial_bankroll: float

class MatchAnalysisRequest(BaseModel):
    league_id: int       # Ex: 2 para Champions League, 71 para Brasileirão
    season: int          # Ex: 2025 ou 2026
    home_team_id: int    # O ID do time na API-Football (ex: 86 para Real Madrid)
    away_team_id: int    # O ID do time na API-Football (ex: 50 para Man City)
    home_team_name: str  # Nome para a IA pesquisar as notícias (ex: "Real Madrid")
    away_team_name: str  # Nome para a IA pesquisar as notícias (ex: "Manchester City")
    odds_home: float
    odds_draw: float
    odds_away: float

class Token(BaseModel):
    access_token: str
    token_type: str
    
class BetCreate(BaseModel):
    fixture_id: int 
    match_string: str
    market: str
    odd_taken: float
    stake: float
    expected_ev: float
    ai_justification: str

# --- ROTAS PÚBLICAS ---

@app.post("/users/", response_model=dict)
def create_user(user: UserCreate):
    """Cria o usuário com senha criptografada."""
    # Transforma a senha "123456" num hash maluco
    hashed_password = get_password_hash(user.password)
    
    user_id = db_manager.create_user(user.name, user.email, hashed_password, user.initial_bankroll)
    if not user_id:
        raise HTTPException(status_code=400, detail="Erro ao criar usuário. Email já cadastrado?")
    return {"message": "Usuário criado!", "user_id": user_id}

@app.post("/login", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Rota padrão OAuth2 para gerar o JWT."""
    user = db_manager.get_user_by_email(form_data.username) # No OAuth2, o email entra no campo 'username'
    
    if not user or not verify_password(form_data.password, user['password_hash']):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Se a senha bateu, cria o crachá digital!
    access_token = create_access_token(data={"sub": user['email']})
    return {"access_token": access_token, "token_type": "bearer"}


# --- ROTAS PROTEGIDAS (Precisam do Token) ---

@app.get("/bankroll")
def get_bankroll(current_user: dict = Depends(get_current_user)):
    """Pega a banca do usuário logado."""
    # O current_user já foi validado pelo JWT!
    bankroll = db_manager.get_user_bankroll(current_user['id'])
    return {"user_name": current_user['name'], "current_bankroll": bankroll}

@app.post("/sniper/analyze")
def analyze_match(req: MatchAnalysisRequest, current_user: dict = Depends(get_current_user)):
    """O Coração do Sniper com Busca Automática de Estatísticas e Cache."""
    
    bankroll = db_manager.get_user_bankroll(current_user['id'])
    if bankroll <= 0:
        raise HTTPException(status_code=400, detail="Banca zerada. Faça um depósito!")

    # --- 1. BUSCA DE ESTATÍSTICAS (O Pulo do Gato) ---
    def get_team_xg(team_id: int, is_home: bool) -> float:
        cached_stats = db_manager.get_cached_team_stats(team_id, req.league_id, req.season)
        
        if cached_stats:
            return cached_stats['home_xg'] if is_home else cached_stats['away_xg']
            
        api_stats = stats_service.fetch_team_season_stats(req.league_id, req.season, team_id)
        
        if not api_stats:
            # Em vez de dar erro 500, usamos um valor padrão para o Sniper não parar
            # Isso é o que chamamos de 'Graceful Degradation'
            print(f"⚠️ Usando xG padrão para o time {team_id} devido a limitação da API.")
            return 1.2 if is_home else 0.8 # Valores genéricos médios
            
        db_manager.upsert_team_stats(team_id, req.league_id, req.season, api_stats['home_xg'], api_stats['away_xg'])
        return api_stats['home_xg'] if is_home else api_stats['away_xg']

    # Puxa o xG de cada time usando a nossa lógica inteligente
    home_xg = get_team_xg(req.home_team_id, is_home=True)
    away_xg = get_team_xg(req.away_team_id, is_home=False)


    # --- 2. O FLUXO DE ANÁLISE ---
    
    # Matemática Pura (Agora com dados 100% reais!)
    math_probs = math_engine.calculate_probabilities(home_xg, away_xg)
    
    # Notícias de desfalques
    news_context = scout.fetch_match_context(req.home_team_name, req.away_team_name)
    
    # Ajuste da IA
    ai_result = ai_analyst.generate_adjusted_probabilities(
        req.home_team_name, req.away_team_name, math_probs, news_context
    )
    
    # Decisão Financeira
    market_odds = {"home": req.odds_home, "draw": req.odds_draw, "away": req.odds_away}
    decision = decision_engine.evaluate_market(ai_result, market_odds, bankroll)

    return {
        "match": f"{req.home_team_name} x {req.away_team_name}",
        "stats_used": {
            "home_xg": home_xg,
            "away_xg": away_xg
        },
        "analyst_verdict": ai_result,
        "financial_decision": decision
    }

@app.get("/matches/upcoming")
def get_upcoming_matches(
    date: Optional[str] = None, 
    league_id: Optional[int] = None, 
    season: Optional[int] = None,
    current_user: dict = Depends(get_current_user) # Mantendo o cadeado JWT!
):
    """
    Retorna a lista de próximos jogos.
    Se não passar a data no formato YYYY-MM-DD, ele pega os jogos de hoje.
    """
    # Se o frontend não mandar data, assume que é hoje
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    matches = stats_service.fetch_upcoming_matches(date_str=date, league_id=league_id, season=season)

    if not matches:
        return {
            "message": f"Nenhum jogo agendado encontrado para a data {date}.", 
            "total": 0, 
            "matches": []
        }

    return {
        "date_searched": date,
        "total": len(matches),
        "matches": matches
    }
    
@app.post("/bets/")
def place_bet(bet: BetCreate, current_user: dict = Depends(get_current_user)):
    """
    Regista um novo bilhete de aposta no histórico do utilizador 
    e desconta a stake (valor apostado) da sua banca atual.
    """
    user_id = current_user['id']
    
    # 1. Validação de segurança: o utilizador tem saldo suficiente?
    current_bankroll = db_manager.get_user_bankroll(user_id)
    
    if current_bankroll < bet.stake:
        raise HTTPException(
            status_code=400, 
            detail=f"Saldo insuficiente. A sua banca atual é de R$ {current_bankroll:.2f}, mas tentou apostar R$ {bet.stake:.2f}."
        )

    # 2. Registar o bilhete na base de dados (o método já atualiza a banca automaticamente)
    db_manager.register_bet(
        user_id=user_id,
        match_string=bet.match_string,
        market=bet.market,
        odd=bet.odd_taken,
        stake=bet.stake,
        ev=bet.expected_ev,
        ai_justification=bet.ai_justification
    )

    # 3. Obter o saldo atualizado para atualizar o ecrã no frontend
    new_bankroll = db_manager.get_user_bankroll(user_id)

    return {
        "message": "Bilhete registado com sucesso!",
        "status": "PENDING",
        "stake_deducted": bet.stake,
        "new_bankroll": new_bankroll
    }
    
@app.get("/bets/me")
def get_my_bets(current_user: dict = Depends(get_current_user)):
    """
    Retorna o histórico completo de apostas do usuário logado.
    """
    query = """
        SELECT id, match_string, market, odd_taken, stake, expected_ev, status, profit, created_at 
        FROM bets 
        WHERE user_id = %s 
        ORDER BY created_at DESC;
    """
    try:
        with db_manager._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (current_user['id'],))
                bets = cursor.fetchall()
                
                # O psycopg2 RealDictCursor já entrega um dicionário, 
                # mas garantimos que datas sejam formatadas para JSON
                for bet in bets:
                    bet['created_at'] = bet['created_at'].isoformat()
                    # Convertemos decimais para float para o JSON não reclamar
                    bet['odd_taken'] = float(bet['odd_taken'])
                    bet['stake'] = float(bet['stake'])
                    bet['profit'] = float(bet['profit'])
                    
                return bets
    except Exception as e:
        print(f"❌ Erro ao buscar histórico: {e}")
        raise HTTPException(status_code=500, detail="Erro ao buscar histórico de apostas.")
    
@app.on_event("startup")
async def startup_event():
    # Inicia o settler em uma thread separada
    Thread(target=start_settler_loop, daemon=True).start()
    
@app.post("/bets/")
def place_bet(bet: BetCreate, current_user: dict = Depends(get_current_user)):
    user_id = current_user['id']
    
    # Validação de banca
    current_bankroll = db_manager.get_user_bankroll(user_id)
    if current_bankroll < bet.stake:
        raise HTTPException(status_code=400, detail="Saldo insuficiente.")

    # Registre incluindo o fixture_id
    db_manager.register_bet(
        user_id=user_id,
        fixture_id=bet.fixture_id, # <--- Passe para o DB
        match_string=bet.match_string,
        market=bet.market,
        odd=bet.odd_taken,
        stake=bet.stake,
        ev=bet.expected_ev,
        ai_justification=bet.ai_justification
    )

    return {"message": "Alvo registrado!", "new_bankroll": db_manager.get_user_bankroll(user_id)}

@app.get("/users/dashboard")
def get_dashboard(current_user: dict = Depends(get_current_user)):
    """Rota para alimentar o Dashboard da HomeScreen."""
    stats = db_manager.get_dashboard_stats(current_user['id'])
    return stats

@app.get("/users/dashboard-stats")
def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    """
    Retorna os dados consolidados para o Dashboard Premium da HomeScreen.
    """
    stats = db_manager.get_user_dashboard_metrics(current_user['id'])
    
    # Adicionamos o bankroll atual para sincronizar tudo em uma chamada só
    stats["current_bankroll"] = db_manager.get_user_bankroll(current_user['id'])
    
    return stats