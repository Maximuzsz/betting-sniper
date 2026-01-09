import streamlit as st
import os
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

from models.models import engine, init_db
from auth import show_login_signup_interface
from ui.sidebar import show_sidebar
from ui.analysis_tab import show_analysis_tab
from ui.history_tab import show_history_tab
from services import OddsService, AIService, NewsService, StatsService
from utils.math_engine import PoissonEngine

# --- CONFIGURAÇÃO INICIAL ---
load_dotenv()
st.set_page_config(page_title="Sniper Pro: Elite Betting", page_icon="🎯", layout="wide")
Session = sessionmaker(bind=engine)

# --- INICIALIZAÇÃO DO BANCO DE DADOS (executado apenas uma vez) ---
init_db()

# --- CSS CUSTOMIZADO ---
st.markdown("""
    <style>
    .big-font { font-size:24px !important; font-weight: bold; }
    /* Adicione outros estilos globais aqui, se necessário */
    </style>
""", unsafe_allow_html=True)


# --- FUNÇÃO PRINCIPAL DA APLICAÇÃO (APÓS LOGIN) ---
def run_app(user_id, username):
    st.title(f"🎯 Sniper Pro: Bem-vindo, {username}!")

    # Carrega serviços em cache
    @st.cache_resource
    def load_services():
        return (
            OddsService(os.getenv("ODDS_API_KEY")),
            AIService(os.getenv("GEMINI_KEY") or os.getenv("GEMINI_API_KEY")),
            NewsService(),
            PoissonEngine(league_avg_goals=1.35),
            StatsService()
        )
    services = load_services()
    odds_service = services[0]

    # --- RENDERIZAÇÃO DA UI ---
    liga_selecionada = show_sidebar(user_id, odds_service)
    
    tab_analise, tab_historico = st.tabs(["🕵️ Operação", "📈 Minha Carteira"])

    with tab_analise:
        show_analysis_tab(user_id, liga_selecionada, services)

    with tab_historico:
        show_history_tab(user_id)

# --- PONTO DE ENTRADA E CONTROLE DE FLUXO ---
def main():
    session = Session()
    try:
        if 'logged_in' not in st.session_state:
            st.session_state['logged_in'] = False

        if st.session_state['logged_in']:
            run_app(st.session_state['user_id'], st.session_state['username'])
        else:
            show_login_signup_interface(session)
    finally:
        session.close()

if __name__ == "__main__":
    main()