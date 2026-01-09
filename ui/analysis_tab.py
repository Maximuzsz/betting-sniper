import streamlit as st
from db.queries import save_to_db
from utils.math_engine import PoissonEngine

def calculate_kelly_criterion(prob_real, odd_casa, bankroll, fraction=0.125):
    if prob_real <= 0 or odd_casa <= 1: return 0.0, 0.0
    b = odd_casa - 1
    p = prob_real
    q = 1 - p
    kelly_percentage = (b * p - q) / b
    safe_percentage = max(0, kelly_percentage * fraction)
    stake = bankroll * safe_percentage
    return stake, safe_percentage * 100

def show_analysis_tab(user_id, liga_selecionada, services):
    odds_service, ai_service, news_service, math_engine, stats_service = services
    
    with st.container():
        if 'matches_data' in st.session_state and st.session_state['matches_data']:
            match_options = {f"{m['home_team']} vs {m['away_team']}": m for m in st.session_state['matches_data']}
            selected_match_name = st.selectbox("Selecione um Jogo:", list(match_options.keys()), index=None, placeholder="Escolha uma partida para analisar")

            if selected_match_name:
                match_data = match_options[selected_match_name]
                
                current_match_key = f"{match_data['home_team']}_{match_data['away_team']}"
                if 'last_match_key' not in st.session_state or st.session_state['last_match_key'] != current_match_key:
                    st.session_state['last_match_key'] = current_match_key
                    st.session_state.setdefault('hs', 1.5); st.session_state.setdefault('hc', 1.2)
                    st.session_state.setdefault('as', 1.3); st.session_state.setdefault('ac', 1.4)
                    if 'analysis_results' in st.session_state:
                        del st.session_state['analysis_results']

                # Lógica de busca de odds mais robusta
                bookmakers = match_data.get('bookmakers', [])
                
                # Tenta encontrar na Bet365 primeiro
                odds_data = next((book['markets'][0]['outcomes'] for book in bookmakers if book['key'] == 'bet365'), None)
                
                # Se não encontrar, pega o primeiro bookmaker disponível que tenha o mercado 'h2h'
                if not odds_data:
                    for book in bookmakers:
                        if book.get('markets') and book['markets'][0].get('key') == 'h2h':
                            odds_data = book['markets'][0]['outcomes']
                            st.warning(f"Odds da Bet365 não encontradas. Usando odds de '{book['title']}'.")
                            break
                
                if odds_data:
                    odds = {o['name']: o['price'] for o in odds_data}
                else:
                    st.error("Nenhuma odd de 'vencedor' (h2h) encontrada para este jogo.")
                    st.stop()

                # Botão para puxar estatísticas automaticamente
                if st.button("📊 Puxar Estatísticas", help="Busca as médias de gols marcados e sofridos para os times"):
                    with st.spinner("Buscando estatísticas..."):
                        h_stats = stats_service.get_team_stats(match_data['home_team'], liga_selecionada[0], liga_selecionada[1])
                        a_stats = stats_service.get_team_stats(match_data['away_team'], liga_selecionada[0], liga_selecionada[1])
                        
                        if h_stats and h_stats.get('scored_avg') is not None:
                            st.session_state['hs'] = float(h_stats['scored_avg'])
                            st.session_state['hc'] = float(h_stats['conceded_avg'])
                        else:
                            st.warning(f"Não foi possível obter estatísticas para {match_data['home_team']}.")

                        if a_stats and a_stats.get('scored_avg') is not None:
                            st.session_state['as'] = float(a_stats['scored_avg'])
                            st.session_state['ac'] = float(a_stats['conceded_avg'])
                        else:
                            st.warning(f"Não foi possível obter estatísticas para {match_data['away_team']}.")
                        
                        st.rerun()

                col1, col2 = st.columns(2)
                with col1:
                    st.caption(f"🏠 {match_data['home_team']}")
                    st.metric("Odd", f"{odds.get(match_data['home_team'], 0):.2f}")
                    h_s = st.number_input("Gols Marcados (média)", 0.0, 5.0, key="hs", step=0.1)
                    h_c = st.number_input("Gols Sofridos (média)", 0.0, 5.0, key="hc", step=0.1)
                with col2:
                    st.caption(f"✈️ {match_data['away_team']}")
                    st.metric("Odd", f"{odds.get(match_data['away_team'], 0):.2f}")
                    a_s = st.number_input("Gols Marcados (média)", 0.0, 5.0, key="as", step=0.1)
                    a_c = st.number_input("Gols Sofridos (média)", 0.0, 5.0, key="ac", step=0.1)

                if st.button("🚀 EXECUTAR ANÁLISE", type="primary", use_container_width=True):
                    with st.spinner("Analisando notícias, calculando probabilidades e consultando IA..."):
                        news = news_service.get_match_context(match_data['home_team'], match_data['away_team'], liga_selecionada[1])
                        math_res = math_engine.calculate_probabilities({'scored': h_s, 'conceded': h_c}, {'scored': a_s, 'conceded': a_c})
                        ai_res = ai_service.analyze_context(match_data, math_res, news)
                        st.session_state['analysis_results'] = {
                            'news': news, 'math_res': math_res, 'ai_res': ai_res,
                            'inputs': {'h_s': h_s, 'h_c': h_c, 'a_s': a_s, 'a_c': a_c},
                            'odds': {'home': odds.get(match_data['home_team'], 0), 'away': odds.get(match_data['away_team'], 0)}
                        }
                    st.rerun()

                if 'analysis_results' in st.session_state:
                    res = st.session_state['analysis_results']
                    st.info(f"🧠 Análise da IA: {res['ai_res'].get('analise_textual', 'N/A')}")

                    prob_h = max(0.01, min(0.99, res['math_res']['home_win'] + res['ai_res'].get('delta_home', 0)))
                    prob_a = max(0.01, min(0.99, res['math_res']['away_win'] + res['ai_res'].get('delta_away', 0)))
                    ev_h = (prob_h * res['odds']['home']) - 1
                    ev_a = (prob_a * res['odds']['away']) - 1
                    
                    current_balance = st.session_state.get('current_balance', 0)
                    kelly_fraction = st.session_state.get('kelly_fraction', 0.1)

                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(f"**{match_data['home_team']}**")
                        stake_h, _ = calculate_kelly_criterion(prob_h, res['odds']['home'], current_balance, kelly_fraction)
                        st.metric("Prob. Real 🆚 EV", f"{prob_h:.1%}", f"{ev_h:+.1%}")
                        if ev_h > 0.05:
                            st.success(f"Valor Encontrado! Stake Sugerida: R$ {stake_h:.2f}")
                            if st.button(f"💾 Registrar Aposta", key="btn_h"):
                                ok, msg = save_to_db(user_id, match_data, res['inputs'], res['odds'], res['math_res'], res['ai_res'], prob_h, ev_h, 'home', stake_h)
                                if ok: st.toast("Aposta Registrada!", icon="💰"); st.rerun()
                                else: st.error(msg)
                    with c2:
                        st.markdown(f"**{match_data['away_team']}**")
                        stake_a, _ = calculate_kelly_criterion(prob_a, res['odds']['away'], current_balance, kelly_fraction)
                        st.metric("Prob. Real 🆚 EV", f"{prob_a:.1%}", f"{ev_a:+.1%}")
                        if ev_a > 0.05:
                            st.success(f"Valor Encontrado! Stake Sugerida: R$ {stake_a:.2f}")
                            if st.button(f"💾 Registrar Aposta", key="btn_a"):
                                ok, msg = save_to_db(user_id, match_data, res['inputs'], res['odds'], res['math_res'], res['ai_res'], prob_a, ev_a, 'away', stake_a)
                                if ok: st.toast("Aposta Registrada!", icon="💰"); st.rerun()
                                else: st.error(msg)
        else:
            st.info("👈 Use o menu lateral para escanear uma liga e começar.")
