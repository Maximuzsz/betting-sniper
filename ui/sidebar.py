import streamlit as st
from db.queries import get_wallet_balance, update_wallet_balance, update_user_kelly_fraction

def show_sidebar(user_id, odds_service):
    with st.sidebar:
        current_balance = get_wallet_balance(user_id)
        st.header(f"💰 Banca: R$ {current_balance:.2f}")

        with st.expander("💵 Atualizar Banca"):
            with st.form("update_wallet_form"):
                new_balance = st.number_input("Novo Saldo", min_value=0.0, value=current_balance, step=100.0)
                submitted = st.form_submit_button("Atualizar")
                if submitted:
                    if update_wallet_balance(user_id, new_balance):
                        st.toast("Banca atualizada com sucesso!", icon="🎉")
                        st.rerun()
                    else:
                        st.error("Não foi possível atualizar a banca.")
        
        if st.button("Logout"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

        st.divider()
        st.header("⚙️ Configurações")
        
        def handle_kelly_update():
            new_fraction = st.session_state.kelly_slider
            update_user_kelly_fraction(user_id, new_fraction)

        st.slider(
            "Fração de Kelly", 
            min_value=0.01, 
            max_value=0.5, 
            value=st.session_state.get('kelly_fraction', 0.1), 
            format="%.2f",
            key="kelly_slider",
            on_change=handle_kelly_update
        )
        
        st.divider()
        st.header("🔍 Radar")
        opcoes_ligas = [
            ("soccer_brazil_campeonato", "🇧🇷 Brasileirão A"),
            ("soccer_epl", "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League"),
            ("soccer_spain_la_liga", "🇪🇸 La Liga"),
            ("soccer_uefa_champs_league", "🇪🇺 Champions")
        ]
        liga_selecionada = st.selectbox("Campeonato:", opcoes_ligas, format_func=lambda x: x[1])
        
        if st.button("🔄 Escanear", type="primary"):
            with st.spinner("Buscando jogos..."):
                matches = odds_service.get_upcoming_matches(liga_selecionada[0])
                if matches and isinstance(matches, list) and len(matches) > 0 and "error" not in matches[0]:
                    st.session_state['matches_data'] = matches
                    st.success(f"{len(matches)} jogos encontrados.")
                else:
                    st.warning("Nenhum jogo encontrado para esta liga.")
                    st.session_state['matches_data'] = []
    
    return liga_selecionada
