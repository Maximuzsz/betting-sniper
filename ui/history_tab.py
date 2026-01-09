import streamlit as st
from sqlalchemy.orm import sessionmaker
from models.models import engine, Prediction, Match
from db.queries import resolve_bet

Session = sessionmaker(bind=engine)

def show_history_tab(user_id):
    st.header("📈 Desempenho e Histórico")
    session = Session()
    try:
        predictions = session.query(Prediction).filter_by(user_id=user_id).all()
        total_profit = sum(p.calculate_profit() for p in predictions)
        total_bets = len(predictions)
        won_bets = len([p for p in predictions if p.status == 'GREEN'])
        winrate = (won_bets / total_bets) * 100 if total_bets > 0 else 0

        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Lucro Total", f"R$ {total_profit:.2f}")
        kpi2.metric("Total de Apostas", total_bets)
        kpi3.metric("Taxa de Acerto", f"{winrate:.1f}%")

        st.divider()
        history = session.query(Prediction).filter_by(user_id=user_id).join(Match).order_by(Prediction.id.desc()).limit(50).all()
        
        if history:
            for p in history:
                with st.container(border=True):
                    cols = st.columns([3, 1, 1, 2])
                    match_label = f"{p.match.home_team} vs {p.match.away_team}"
                    cols[0].markdown(f"**{match_label}**<br><small>{p.match.commence_time.strftime('%d/%m/%Y %H:%M')}</small>", unsafe_allow_html=True)
                    cols[1].metric("Stake", f"R$ {p.stake:.2f}")
                    odd_show = p.odd_home_used if p.final_prob_home > 0.5 else p.odd_away_used
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
                        cols[3].markdown(f"<h5 style='color:{status_color};'>{p.status}</h5><h6>{profit_str}</h6>", unsafe_allow_html=True)
        else:
            st.info("Nenhum registro de aposta encontrado.")
    finally:
        session.close()
