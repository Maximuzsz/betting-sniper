import streamlit as st
import os
import pandas as pd
import json 
from datetime import datetime
from dotenv import load_dotenv

# Importação dos módulos
from services import OddsService, AIService, NewsService
from math_engine import PoissonEngine
from models import engine, Match, Prediction, init_db
from sqlalchemy.orm import sessionmaker

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Sniper Pro: Elite Betting", page_icon="🎯", layout="wide")
load_dotenv()

# CSS Customizado
st.markdown("""
    <style>
    .big-font { font-size:24px !important; font-weight: bold; }
    .metric-card { background-color: #1e1e1e; border: 1px solid #333; padding: 15px; border-radius: 8px; margin-bottom: 10px; }
    .success-box { background-color: rgba(74, 222, 128, 0.1); border: 1px solid #4ade80; color: #4ade80; padding: 10px; border-radius: 5px; }
    .danger-box { background-color: rgba(248, 113, 113, 0.1); border: 1px solid #f87171; color: #f87171; padding: 10px; border-radius: 5px; }
    </style>
""", unsafe_allow_html=True)

ODDS_API_KEY = os.getenv("ODDS_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if not ODDS_API_KEY or not GEMINI_KEY:
    st.error("❌ Chaves de API ausentes no arquivo .env")
    st.stop()

# Conexão com Banco
Session = sessionmaker(bind=engine)

# --- FUNÇÕES AUXILIARES ---
def calculate_kelly_criterion(prob_real, odd_casa, bankroll, fraction=0.125):
    if prob_real <= 0 or odd_casa <= 1: return 0.0, 0.0
    b = odd_casa - 1
    p = prob_real
    q = 1 - p
    kelly_percentage = (b * p - q) / b
    safe_percentage = max(0, kelly_percentage * fraction)
    stake = bankroll * safe_percentage
    return stake, safe_percentage * 100

def save_to_db(match_data, inputs, odds, math_res, ai_res, final_prob, ev, selected_side):
    """
    Salva a oportunidade no banco de dados preenchendo TODOS os campos do modelo.
    """
    session = Session()
    try:
        # Tenta converter a data da API
        try:
            match_date = datetime.fromisoformat(match_data.get('commence_time', '').replace('Z', '+00:00'))
        except:
            match_date = datetime.now()

        # Verifica se o jogo já existe ou cria novo
        match_entry = session.query(Match).filter_by(
            home_team=match_data['home_team'], 
            away_team=match_data['away_team']
        ).first()
        
        if not match_entry:
            match_entry = Match(
                home_team=match_data['home_team'],
                away_team=match_data['away_team'],
                commence_time=match_date,
                league_key="manual_entry"
            )
            session.add(match_entry)
            session.flush()

        # Define qual ajuste de IA e qual Odd salvar com base na escolha (Casa ou Fora)
        ai_delta = ai_res.get('delta_home', 0) if selected_side == 'home' else ai_res.get('delta_away', 0)
        
        # Cria a predição completa
        pred = Prediction(
            match_id=match_entry.id,
            
            # Inputs Manuais
            input_home_goals_avg=float(inputs['h_s']),
            input_home_conceded_avg=float(inputs['h_c']),
            input_away_goals_avg=float(inputs['a_s']),
            input_away_conceded_avg=float(inputs['a_c']),
            
            # Odds do Momento
            bookmaker_name="Agregado", # Poderia vir da API se selecionado
            odd_home_used=float(odds['home']),
            odd_away_used=float(odds['away']),
            # Se tiver empate na API, salva, senão 0
            odd_draw_used=0.0, 
            
            # Resultados Matemáticos e IA
            math_prob_home=float(math_res['home_win']) if selected_side == 'home' else float(math_res['away_win']),
            ai_delta_adjustment=float(ai_delta),
            final_prob_home=float(final_prob), # Nome da coluna é final_prob_home mas usamos para a prob final da aposta
            
            # Valor e Decisão
            expected_value=float(ev),
            is_value_bet=(ev > 0.05),
            
            # O "Cérebro" da decisão
            ai_analysis_json=ai_res 
        )
        
        session.add(pred)
        session.commit()
        return True, "Sucesso"
        
    except Exception as e:
        session.rollback()
        return False, str(e)
    finally:
        session.close()

# --- MAIN APP ---
def main():
    # Inicializa tabelas se não existirem
    init_db()

    @st.cache_resource
    def load_services():
        return (
            OddsService(ODDS_API_KEY),
            AIService(GEMINI_KEY),
            NewsService(),
            PoissonEngine(league_avg_goals=1.35)
        )

    odds_service, ai_service, news_service, math_engine = load_services()

    # --- SIDEBAR ---
    with st.sidebar:
        st.header("💰 Gestão de Banca")
        bankroll = st.number_input("Banca Total (R$)", min_value=100.0, value=1000.0, step=50.0)
        kelly_fraction = st.slider("Agressividade (Kelly)", 0.05, 0.25, 0.10, format="%.2f")
        
        st.divider()
        st.header("🔍 Radar")
        
        opcoes_ligas = [
            ("soccer_brazil_campeonato", "🇧🇷 Brasileirão Série A"),
            ("soccer_brazil_serie_b", "🇧🇷 Brasileirão Série B"),
            ("soccer_epl", "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League"),
            ("soccer_spain_la_liga", "🇪🇸 La Liga"),
            ("soccer_uefa_champs_league", "🇪🇺 Champions League")
        ]
        
        liga_selecionada = st.selectbox("Campeonato:", opcoes_ligas, format_func=lambda x: x[1])
        
        if st.button("🔄 Escanear Oportunidades", type="primary"):
            with st.spinner(f"Buscando jogos..."):
                matches = odds_service.get_upcoming_matches(liga_selecionada[0])
                if matches and isinstance(matches, list) and len(matches) > 0 and "error" not in matches[0]:
                    st.session_state['matches_data'] = matches
                    st.success(f"✅ {len(matches)} jogos encontrados.")
                else:
                    st.warning("Nenhum jogo encontrado.")
                    st.session_state['matches_data'] = []

    # --- CORPO PRINCIPAL ---
    st.title("🎯 Sniper Pro: Central de Inteligência")
    
    tab_analise, tab_historico = st.tabs(["🕵️ Análise de Mercado", "📈 Histórico & Assertividade"])

    # === ABA 1: OPERAÇÃO ===
    with tab_analise:
        if 'matches_data' in st.session_state and st.session_state['matches_data']:
            
            match_options = {f"{m['home_team']} vs {m['away_team']}": m for m in st.session_state['matches_data']}
            selected_match_name = st.selectbox("Selecione o Confronto:", list(match_options.keys()), index=None)

            if selected_match_name:
                match_data = match_options[selected_match_name]
                
                odds = {}
                for book in match_data.get('bookmakers', []):
                    if book['key'] == 'bet365' or True: 
                        odds = {o['name']: o['price'] for o in book['markets'][0]['outcomes']}
                        break
                
                if not odds:
                    st.error("🚫 Sem odds disponíveis.")
                    st.stop()

                st.markdown("---")
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader(f"🏠 {match_data['home_team']}")
                    odd_h = odds.get(match_data['home_team'], 0)
                    st.metric("Odd Atual", f"{odd_h:.2f}")
                    h_s = st.number_input("Gols Feitos (Casa)", 0.0, 5.0, 1.45, step=0.1, key="hs")
                    h_c = st.number_input("Gols Sofridos (Casa)", 0.0, 5.0, 0.95, step=0.1, key="hc")

                with col2:
                    st.subheader(f"✈️ {match_data['away_team']}")
                    odd_a = odds.get(match_data['away_team'], 0)
                    st.metric("Odd Atual", f"{odd_a:.2f}")
                    a_s = st.number_input("Gols Feitos (Fora)", 0.0, 5.0, 1.15, step=0.1, key="as")
                    a_c = st.number_input("Gols Sofridos (Fora)", 0.0, 5.0, 1.35, step=0.1, key="ac")

                st.markdown("---")
                if st.button("🚀 EXECUTAR SNIPER ANALYSIS", type="primary", use_container_width=True):
                    
                    with st.status("🕵️ Processando Inteligência...", expanded=True) as status:
                        news = news_service.get_match_context(match_data['home_team'], match_data['away_team'], liga_selecionada[1])
                        math_res = math_engine.calculate_probabilities({'scored': h_s, 'conceded': h_c}, {'scored': a_s, 'conceded': a_c})
                        ai_res = ai_service.analyze_context(match_data, math_res, news)
                        status.update(label="✅ Análise Finalizada!", state="complete", expanded=False)

                    st.subheader("📊 Relatório de Decisão")
                    st.info(f"📝 **Analista:** {ai_res.get('analise_textual')}")

                    prob_h = max(0.01, min(0.99, math_res['home_win'] + ai_res.get('delta_home', 0)))
                    prob_a = max(0.01, min(0.99, math_res['away_win'] + ai_res.get('delta_away', 0)))
                    ev_h = (prob_h * odd_h) - 1
                    ev_a = (prob_a * odd_a) - 1

                    # Dados para salvar
                    inputs_db = {'h_s': h_s, 'h_c': h_c, 'a_s': a_s, 'a_c': a_c}
                    odds_db = {'home': odd_h, 'away': odd_a}

                    col_res1, col_res2 = st.columns(2)
                    
                    # CARD MANDANTE
                    with col_res1:
                        st.markdown(f"#### 🏠 {match_data['home_team']}")
                        stake_h, pct_h = calculate_kelly_criterion(prob_h, odd_h, bankroll, kelly_fraction)
                        c1, c2 = st.columns(2)
                        c1.metric("Probabilidade Real", f"{prob_h:.1%}")
                        c2.metric("Odd Justa", f"{1/prob_h:.2f}")
                        
                        if ev_h > 0.05:
                            st.markdown(f"<div class='success-box'>✅ <b>VALOR (+{ev_h:.1%})</b><br>Aposte R$ {stake_h:.2f}</div>", unsafe_allow_html=True)
                            if st.button(f"💾 Registrar ({match_data['home_team']})", key="btn_h"):
                                success, msg = save_to_db(match_data, inputs_db, odds_db, math_res, ai_res, prob_h, ev_h, 'home')
                                if success: st.toast("Salvo com sucesso!", icon="✅")
                                else: st.error(f"Erro ao salvar: {msg}")
                        else:
                            st.markdown(f"<div class='danger-box'>🚫 SEM VALOR</div>", unsafe_allow_html=True)

                    # CARD VISITANTE
                    with col_res2:
                        st.markdown(f"#### ✈️ {match_data['away_team']}")
                        stake_a, pct_a = calculate_kelly_criterion(prob_a, odd_a, bankroll, kelly_fraction)
                        c1, c2 = st.columns(2)
                        c1.metric("Probabilidade Real", f"{prob_a:.1%}")
                        c2.metric("Odd Justa", f"{1/prob_a:.2f}")
                        
                        if ev_a > 0.05:
                            st.markdown(f"<div class='success-box'>✅ <b>VALOR (+{ev_a:.1%})</b><br>Aposte R$ {stake_a:.2f}</div>", unsafe_allow_html=True)
                            if st.button(f"💾 Registrar ({match_data['away_team']})", key="btn_a"):
                                success, msg = save_to_db(match_data, inputs_db, odds_db, math_res, ai_res, prob_a, ev_a, 'away')
                                if success: st.toast("Salvo com sucesso!", icon="✅")
                                else: st.error(f"Erro ao salvar: {msg}")
                        else:
                            st.markdown(f"<div class='danger-box'>🚫 SEM VALOR</div>", unsafe_allow_html=True)

                    with st.expander("📄 Ver Notícias Extraídas"):
                        st.text(news)

        elif 'matches_data' not in st.session_state:
            st.info("👈 Comece atualizando a lista de jogos.")

    # === ABA 2: HISTÓRICO ===
    with tab_historico:
        st.header("📜 Histórico de Apostas")
        
        session = Session()
        try:
            history = session.query(Prediction).join(Match).order_by(Prediction.id.desc()).limit(50).all()
            
            if history:
                data = []
                for p in history:
                    match_label = f"{p.match.home_team} x {p.match.away_team}"
                    data.append({
                        "Data": p.match.commence_time.strftime("%d/%m") if p.match.commence_time else "N/A",
                        "Jogo": match_label,
                        "Odd": p.odd_home_used,
                        "Prob Real": f"{p.final_prob_home:.1%}",
                        "EV": f"{p.expected_value:.1%}",
                        "Delta IA": f"{p.ai_delta_adjustment:+.1%}",
                        "Status": "✅ Valor" if p.is_value_bet else "❌ Sem Valor"
                    })
                
                df = pd.DataFrame(data)
                st.dataframe(df, use_container_width=True)
            else:
                st.info("Nenhuma aposta salva. Tente registrar uma na aba de Análise.")
        except Exception as e:
            st.error(f"Erro ao ler histórico: {e}")
        finally:
            session.close()

if __name__ == "__main__":
    main()