import streamlit as st
try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
from db.queries import save_to_db, get_wallet_balance
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

def find_odd(odds_dict, team_name):
    """Tenta encontrar a odd do time mesmo com pequenas variações no nome."""
    # 1. Tentativa exata
    if team_name in odds_dict:
        return odds_dict[team_name]
    # 2. Tentativa parcial (ex: 'Man City' in 'Manchester City')
    for key, val in odds_dict.items():
        if key in team_name or team_name in key:
            return val
    return 0.0

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
                odds_data = next((book['markets'][0]['outcomes'] for book in bookmakers if book['key'] == 'bet365' and book.get('markets')), None)
                
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

                # Busca odds de forma segura
                odd_home = find_odd(odds, match_data['home_team'])
                odd_away = find_odd(odds, match_data['away_team'])
                odd_draw = find_odd(odds, 'Draw') # A API geralmente retorna 'Draw'

                # --- PAINEL DE CONFRONTO (DESIGN MELHORADO) ---
                with st.container(border=True):
                    st.markdown("#### ⚔️ Dados do Confronto")
                    col1, col2, col3 = st.columns([1, 0.2, 1])
                    with col1:
                        st.markdown(f"**🏠 {match_data['home_team']}**")
                        st.caption(f"Odd: {odd_home:.2f}")
                        h_s = st.number_input("Gols Pró (Média)", 0.0, 5.0, key="hs", step=0.1, help="Média de gols marcados nos últimos jogos")
                        h_c = st.number_input("Gols Contra (Média)", 0.0, 5.0, key="hc", step=0.1, help="Média de gols sofridos nos últimos jogos")
                    with col2:
                        st.markdown("<h2 style='text-align: center; color: gray;'>VS</h2>", unsafe_allow_html=True)
                        st.markdown(f"<div style='text-align: center; color: #888;'><small>Empate</small><br><b>{odd_draw:.2f}</b></div>", unsafe_allow_html=True)
                    with col3:
                        st.markdown(f"**✈️ {match_data['away_team']}**")
                        st.caption(f"Odd: {odd_away:.2f}")
                        a_s = st.number_input("Gols Pró (Média)", 0.0, 5.0, key="as", step=0.1)
                        a_c = st.number_input("Gols Contra (Média)", 0.0, 5.0, key="ac", step=0.1)

                # --- GRÁFICO COMPARATIVO (RADAR) ---
                with st.expander("📊 Comparativo Tático (Radar)", expanded=False):
                    if PLOTLY_AVAILABLE:
                        # Normalização simples para visualização (0 a 5)
                        categories = ['Ataque (Gols Feitos)', 'Defesa (Solidez)', 'Equilíbrio']
                        
                        # Defesa: Invertemos o valor (quanto menos gols sofre, maior a nota)
                        # Assumindo média da liga ~1.35. Se sofre 0.5 é excelente (nota alta). Se sofre 2.0 é ruim.
                        def calc_def_score(conceded):
                            return max(0, 5 - (conceded * 2)) # Ex: 0.5 -> 4.0, 2.0 -> 1.0
                        
                        h_def_score = calc_def_score(h_c)
                        a_def_score = calc_def_score(a_c)
                        
                        # Equilíbrio: Relação Ataque/Defesa
                        h_bal = (h_s + h_def_score) / 2
                        a_bal = (a_s + a_def_score) / 2

                        fig = go.Figure()
                        fig.add_trace(go.Scatterpolar(
                            r=[h_s, h_def_score, h_bal], theta=categories, fill='toself', name=match_data['home_team'], line_color='green'
                        ))
                        fig.add_trace(go.Scatterpolar(
                            r=[a_s, a_def_score, a_bal], theta=categories, fill='toself', name=match_data['away_team'], line_color='red'
                        ))
                        fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 5])), showlegend=True, height=300, margin=dict(l=40, r=40, t=20, b=20))
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("Biblioteca 'plotly' não encontrada. Instale com `pip install plotly` para ver o gráfico.")

                if st.button("🚀 EXECUTAR ANÁLISE", type="primary", use_container_width=True):
                    with st.status("🤖 Iniciando Protocolo Sniper...", expanded=True) as status:
                        st.write("📰 Varrendo portais de notícias e escalações...")
                        news = news_service.get_match_context(match_data['home_team'], match_data['away_team'], liga_selecionada[1])
                        
                        st.write("🧮 Executando simulação de Monte Carlo/Poisson...")
                        math_res = math_engine.calculate_probabilities({'scored': h_s, 'conceded': h_c}, {'scored': a_s, 'conceded': a_c})
                        
                        st.write("🧠 Consultando Inteligência Artificial (Gemini)...")
                        ai_res = ai_service.analyze_context(match_data, math_res, news)
                        
                        # Recalcula odds no momento da análise para garantir consistência
                        current_odd_h = find_odd(odds, match_data['home_team'])
                        current_odd_a = find_odd(odds, match_data['away_team'])
                        current_odd_d = find_odd(odds, 'Draw')

                        st.session_state['analysis_results'] = {
                            'news': news, 'math_res': math_res, 'ai_res': ai_res,
                            'inputs': {'h_s': h_s, 'h_c': h_c, 'a_s': a_s, 'a_c': a_c},
                            'odds': {'home': current_odd_h, 'away': current_odd_a, 'draw': current_odd_d}
                        }
                        status.update(label="✅ Análise Concluída com Sucesso!", state="complete", expanded=False)
                    st.rerun()

                if 'analysis_results' in st.session_state:
                    res = st.session_state['analysis_results']
                    st.info(f"🧠 Análise da IA: {res['ai_res'].get('analise_textual', 'N/A')}")
                    
                    # Alerta se a IA não teve notícias suficientes para trabalhar
                    news_content = res.get('news', '')
                    if not news_content or len(news_content) < 100 or "No detailed news" in news_content or "Error accessing" in news_content:
                        st.warning("⚠️ **Atenção:** Não foram encontradas notícias recentes relevantes. A análise da IA está baseada majoritariamente em estatísticas e pode ignorar lesões de última hora.")

                    prob_h = max(0.01, min(0.99, res['math_res']['home_win'] + res['ai_res'].get('delta_home', 0)))
                    prob_a = max(0.01, min(0.99, res['math_res']['away_win'] + res['ai_res'].get('delta_away', 0)))
                    # O empate absorve o restante da probabilidade
                    prob_d = max(0.01, 1.0 - prob_h - prob_a)

                    ev_h = (prob_h * res['odds']['home']) - 1
                    ev_a = (prob_a * res['odds']['away']) - 1
                    ev_d = (prob_d * res['odds']['draw']) - 1

                    # Cálculo das Odds Justas (Fair Odds)
                    fair_odd_h = 1 / prob_h if prob_h > 0 else 0
                    fair_odd_a = 1 / prob_a if prob_a > 0 else 0
                    fair_odd_d = 1 / prob_d if prob_d > 0 else 0
                    
                    # CORREÇÃO: Busca o saldo real do banco de dados
                    current_balance = get_wallet_balance(user_id)
                    kelly_fraction = st.session_state.get('kelly_fraction', 0.1)

                    # --- EXIBIÇÃO PRINCIPAL (MATCH ODDS) ---
                    st.markdown("### 🏆 Resultado Final (Match Odds)")
                    c1, c2, c3 = st.columns(3)
                    
                    # Função auxiliar para exibir card de aposta
                    def show_bet_card(col, title, prob, fair_odd, book_odd, ev, side, key_suffix):
                        with col:
                            with st.container(border=True):
                                st.markdown(f"#### {title}")
                                
                                # Classificação de Confiança (Probabilidade de Acerto)
                                if prob >= 0.65:
                                    conf_label = "🔥 Muito Provável"
                                    conf_color = "green"
                                elif prob >= 0.45:
                                    conf_label = "✅ Provável"
                                    conf_color = "blue"
                                elif prob >= 0.30:
                                    conf_label = "⚠️ Arriscado"
                                    conf_color = "orange"
                                else:
                                    conf_label = "💣 Zebra (Difícil)"
                                    conf_color = "red"
                                
                                st.markdown(f":{conf_color}[**{conf_label}**]")
                                st.progress(prob, text=f"Chance: {prob:.1%}")
                                
                                # Comparativo de Odds
                                if book_odd > fair_odd:
                                    st.markdown(f"**Odd Justa:** :green[{fair_odd:.2f}]")
                                else:
                                    st.markdown(f"**Odd Justa:** :red[{fair_odd:.2f}]")
                                
                                st.metric("EV (Valor Esperado)", f"{ev:+.1%}", delta_color="normal" if ev < 0 else "inverse")
                                
                                if ev > 0.02: # Limiar de 2% para considerar valor
                                    stake, _ = calculate_kelly_criterion(prob, book_odd, current_balance, kelly_fraction)
                                    st.success(f"💎 **Stake: R$ {stake:.2f}**")
                                    if st.button(f"Apostar", key=f"btn_{key_suffix}", use_container_width=True):
                                        ok, msg = save_to_db(user_id, match_data, res['inputs'], res['odds'], res['math_res'], res['ai_res'], prob, ev, side, stake)
                                        if ok: st.toast("Aposta Registrada!", icon="💰"); st.rerun()
                                        else: st.error(msg)
                                else:
                                    st.caption("🚫 Sem valor.")

                    show_bet_card(c1, match_data['home_team'], prob_h, fair_odd_h, res['odds']['home'], ev_h, 'home', 'h')
                    show_bet_card(c2, "Empate", prob_d, fair_odd_d, res['odds']['draw'], ev_d, 'draw', 'd')
                    show_bet_card(c3, match_data['away_team'], prob_a, fair_odd_a, res['odds']['away'], ev_a, 'away', 'a')

                    # --- EXIBIÇÃO SECUNDÁRIA (MERCADOS ALTERNATIVOS) ---
                    st.divider()
                    st.markdown("### 📊 Insights de Mercados Alternativos (IA)")
                    
                    ac1, ac2 = st.columns(2)
                    with ac1:
                        trend_goals = res['ai_res'].get('tendencia_gols', 'Neutra')
                        color_g = "green" if "Alta" in trend_goals else "red" if "Baixa" in trend_goals else "gray"
                        st.markdown(f"**Gols (Over/Under):** :{color_g}[{trend_goals}]")
                        st.caption("Baseado na análise textual de desfalques ofensivos/defensivos.")
                        
                    with ac2:
                        trend_btts = res['ai_res'].get('tendencia_btts', 'Duvidoso')
                        color_b = "green" if "Sim" in trend_btts else "red" if "Não" in trend_btts else "gray"
                        st.markdown(f"**Ambos Marcam (BTTS):** :{color_b}[{trend_btts}]")
                        st.caption("Baseado no estilo de jogo e necessidade dos times.")
        else:
            st.info("👈 Use o menu lateral para escanear uma liga e começar.")
