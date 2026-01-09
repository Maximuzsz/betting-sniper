import streamlit as st
import pandas as pd
from sqlalchemy.orm import sessionmaker
from models.models import engine, Prediction, Match
from db.queries import resolve_bet

Session = sessionmaker(bind=engine)

def show_history_tab(user_id):
    st.header("📈 Desempenho e Histórico")
    session = Session()
    try:
        # Busca todas as apostas ordenadas por data para o gráfico de evolução
        predictions = session.query(Prediction).filter_by(user_id=user_id).order_by(Prediction.created_at.asc()).all()
        
        total_profit = sum(p.calculate_profit() for p in predictions)
        total_bets = len(predictions)
        total_staked = sum(p.stake for p in predictions)
        won_bets = len([p for p in predictions if p.status == 'GREEN'])
        winrate = (won_bets / total_bets) * 100 if total_bets > 0 else 0
        roi = (total_profit / total_staked * 100) if total_staked > 0 else 0.0

        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Lucro Total", f"R$ {total_profit:.2f}")
        kpi2.metric("ROI", f"{roi:+.2f}%")
        kpi3.metric("Taxa de Acerto", f"{winrate:.1f}%")
        kpi4.metric("Total Apostas", total_bets)

        # --- GRÁFICOS (Abas) ---
        if predictions:
            tab_chart1, tab_chart2 = st.tabs(["📊 Evolução de Lucro", "🥧 Distribuição"])
            
            # Prepara dados
            data = []
            cumulative = 0
            for p in predictions:
                profit = p.calculate_profit()
                cumulative += profit
                data.append({'Data': p.created_at, 'Lucro Acumulado': cumulative, 'Status': p.status})
            
            df = pd.DataFrame(data)

            with tab_chart1:
                st.line_chart(df, x='Data', y='Lucro Acumulado', color="#00FF00")
            
            with tab_chart2:
                status_counts = df["Status"].value_counts()
                st.bar_chart(status_counts, color="#2E8B57" if status_counts.get('GREEN', 0) >= status_counts.get('RED', 0) else "#FF6347")

        st.divider()
        # Reverte a lista para mostrar os mais recentes primeiro na tabela
        history = predictions[::-1]
        
        if history:
            for p in history[:50]:
                with st.container(border=True):
                    cols = st.columns([3, 1, 1, 2])
                    match_label = f"{p.match.home_team} vs {p.match.away_team}"
                    
                    # Identifica em quem foi a aposta para exibir
                    side = p.selected_team if p.selected_team else ('home' if p.final_prob_home > 0.5 else 'away')
                    
                    if side == 'home': target_team = p.match.home_team
                    elif side == 'away': target_team = p.match.away_team
                    else: target_team = "Empate"
                    
                    cols[0].markdown(f"**{match_label}**<br>🎯 {target_team}<br><small>{p.match.commence_time.strftime('%d/%m/%Y %H:%M')}</small>", unsafe_allow_html=True)
                    cols[1].metric("Stake", f"R$ {p.stake:.2f}")
                    
                    if side == 'home': odd_show = p.odd_home_used
                    elif side == 'away': odd_show = p.odd_away_used
                    else: odd_show = p.odd_draw_used
                    
                    cols[2].metric("Odd", f"{odd_show:.2f}")
                    
                    if p.status == 'PENDING':
                        btn_cols = cols[3].columns(2)
                        if btn_cols[0].button("✅ Green", key=f"g_{p.id}"):
                            resolve_bet(p.id, 'GREEN', user_id); st.rerun()
                        if btn_cols[1].button("❌ Red", key=f"r_{p.id}"):
                            resolve_bet(p.id, 'RED', user_id); st.rerun()
                    else:
                        status_color = "green" if p.status == 'GREEN' else "red"
                        profit_val = p.calculate_profit()
                        profit_str = f"+R$ {profit_val:.2f}" if profit_val > 0 else f"R$ {profit_val:.2f}"
                        cols[3].markdown(f"<h4 style='color:{status_color}; text-align:right;'>{p.status}</h4><h5 style='text-align:right;'>{profit_str}</h5>", unsafe_allow_html=True)
                    
                    # Detalhes da Análise (Expander)
                    with st.expander("🧠 Ver Análise da IA e Detalhes"):
                        if p.ai_analysis_json:
                            st.json(p.ai_analysis_json)
                        else:
                            st.caption("Análise detalhada não disponível.")
        else:
            st.info("Nenhum registro de aposta encontrado.")
    finally:
        session.close()
