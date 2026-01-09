import streamlit as st
from db.queries import get_wallet_balance, update_wallet_balance, update_user_kelly_fraction, get_sidebar_stats

def show_sidebar(user_id, odds_service):
    with st.sidebar:
        st.markdown("## 🔫 Sniper Pro")
        
        # --- DASHBOARD FINANCEIRO ---
        current_balance = get_wallet_balance(user_id)
        stats = get_sidebar_stats(user_id)

        with st.container(border=True):
            st.metric("💰 Banca Atual", f"R$ {current_balance:.2f}", delta=f"{stats['total_profit']:+.2f} Lucro Total")
            
            c1, c2 = st.columns(2)
            c1.metric("Winrate", f"{stats['winrate']:.0f}%")
            c2.metric("ROI", f"{stats['roi']:.1f}%")
            
            if stats['pending_count'] > 0:
                st.caption(f"⏳ **{stats['pending_count']}** apostas em jogo (R$ {stats['pending_exposure']:.2f})")

        # --- GESTÃO DE BANCA ---
        with st.expander("💸 Ajustar Saldo"):
            with st.form("update_wallet_form"):
                new_balance = st.number_input("Novo Valor", min_value=0.0, value=current_balance, step=100.0)
                submitted = st.form_submit_button("Atualizar")
                if submitted:
                    if update_wallet_balance(user_id, new_balance):
                        st.toast("Banca atualizada!", icon="✅")
                        st.rerun()
        
        st.divider()
        
        # --- CONFIGURAÇÕES ---
        st.subheader("⚙️ Calibragem")
        
        def handle_kelly_update():
            new_fraction = st.session_state.kelly_slider
            update_user_kelly_fraction(user_id, new_fraction)

        # Define cor e rótulo baseados no valor
        k_val = st.session_state.get('kelly_fraction', 0.1)
        if k_val <= 0.05: k_label = "🛡️ Ultra Conservador"; k_color = "blue"
        elif k_val <= 0.15: k_label = "⚖️ Moderado (Recomendado)"; k_color = "green"
        elif k_val <= 0.25: k_label = "⚔️ Agressivo"; k_color = "orange"
        else: k_label = "🔥 Kamikaze (Alto Risco)"; k_color = "red"

        st.markdown(f"Perfil: :{k_color}[**{k_label}**]")

        st.slider(
            "Critério de Kelly (Risco)", 
            min_value=0.01, 
            max_value=0.5, 
            value=k_val, 
            format="%.2f",
            key="kelly_slider",
            help="Define a agressividade da gestão de banca. Recomendado: 0.10 (Conservador) a 0.25 (Agressivo).",
            on_change=handle_kelly_update
        )
        
        st.divider()
        
        # --- RADAR ---
        st.subheader("📡 Radar de Oportunidades")
        opcoes_ligas = [
            ("soccer_brazil_campeonato", "🇧🇷 Brasileirão A"),
            ("soccer_brazil_serie_b", "🇧🇷 Brasileirão B"),
            ("soccer_epl", "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League"),
            ("soccer_spain_la_liga", "🇪🇸 La Liga"),
            ("soccer_germany_bundesliga", "🇩🇪 Bundesliga"),
            ("soccer_italy_serie_a", "🇮🇹 Serie A"),
            ("soccer_france_ligue_one", "🇫🇷 Ligue 1"),
            ("soccer_portugal_primeira_liga", "🇵🇹 Primeira Liga"),
            ("soccer_netherlands_eredivisie", "🇳🇱 Eredivisie"),
            ("soccer_uefa_champs_league", "🇪🇺 Champions")
        ]
        liga_selecionada = st.selectbox("Selecionar Campeonato:", opcoes_ligas, format_func=lambda x: x[1])
        
        if st.button("🔄 Escanear Mercado", type="primary", use_container_width=True):
            with st.spinner("Buscando melhores odds..."):
                matches = odds_service.get_upcoming_matches(liga_selecionada[0])
                if matches and isinstance(matches, list) and len(matches) > 0 and "error" not in matches[0]:
                    st.session_state['matches_data'] = matches
                    st.success(f"✅ {len(matches)} jogos encontrados!")
                else:
                    st.warning("Nenhum jogo encontrado.")
                    st.session_state['matches_data'] = []

        st.divider()
        if st.button("🚪 Sair / Logout", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    
    return liga_selecionada
