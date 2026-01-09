import streamlit as st
import bcrypt
from sqlalchemy.orm import sessionmaker
from models.models import User, Wallet

# Função para hashear a senha
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

# Função para verificar a senha
def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

# Função para registrar um novo usuário
def register_user(session, username, password):
    if session.query(User).filter_by(username=username).first():
        return False, "Usuário já existe."
    
    hashed_password = hash_password(password)
    new_user = User(username=username, hashed_password=hashed_password)
    session.add(new_user)
    session.flush() # Garante que o ID do usuário seja gerado
    
    # Cria uma carteira para o novo usuário
    new_wallet = Wallet(balance=1000.0, user_id=new_user.id)
    session.add(new_wallet)
    
    session.commit()
    return True, "Usuário registrado com sucesso!"

# Função para autenticar o usuário
def authenticate_user(session, username, password):
    user = session.query(User).filter_by(username=username).first()
    if user and verify_password(password, user.hashed_password):
        return user
    return None

# Interface de Login/Registro
def show_login_signup_interface(session):
    # CSS para centralizar e estilizar
    st.markdown("""
        <style>
        div[data-testid="stVerticalBlock"] > div:has(div.stForm) {
            background-color: #262730;
            padding: 2rem;
            border-radius: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
            border: 1px solid #444;
        }
        .stButton>button {
            width: 100%;
            border-radius: 8px;
            font-weight: bold;
            text-transform: uppercase;
            letter-spacing: 1px;
            height: 3rem;
        }
        h1 { text-align: center; color: #4CAF50; font-size: 3rem !important; margin-bottom: 0; }
        .subtitle { text-align: center; color: #aaa; margin-bottom: 2rem; font-size: 1.2rem; }
        </style>
    """, unsafe_allow_html=True)

    # Centralizando o formulário
    col1, col2, col3 = st.columns([1, 1.5, 1])
    
    with col2:
        st.markdown("<h1>🎯 Sniper Pro</h1>", unsafe_allow_html=True)
        st.markdown("<p class='subtitle'>Inteligência Artificial para Apostas de Valor</p>", unsafe_allow_html=True)
        
        tab_login, tab_signup = st.tabs(["🔐 Login", "✨ Criar Conta"])

        with tab_login:
            with st.form("login_form"):
                username = st.text_input("Usuário", placeholder="Digite seu usuário")
                password = st.text_input("Senha", type="password", placeholder="Digite sua senha")
                st.markdown("<br>", unsafe_allow_html=True)
                submitted = st.form_submit_button("ACESSAR SISTEMA", type="primary")

                if submitted:
                    user = authenticate_user(session, username, password)
                    if user:
                        st.session_state['logged_in'] = True
                        st.session_state['user_id'] = user.id
                        st.session_state['username'] = user.username
                        st.session_state['kelly_fraction'] = user.kelly_fraction
                        st.toast("Login realizado com sucesso!", icon="🔓")
                        st.rerun()
                    else:
                        st.error("Usuário ou senha incorretos.")
        
        with tab_signup:
            with st.form("signup_form"):
                new_user = st.text_input("Escolha um usuário", placeholder="Ex: trader_pro")
                new_pass = st.text_input("Escolha uma senha", type="password")
                confirm_pass = st.text_input("Confirme a senha", type="password")
                st.markdown("<br>", unsafe_allow_html=True)
                submitted = st.form_submit_button("CRIAR CONTA", type="primary")

                if submitted:
                    if new_pass == confirm_pass:
                        if len(new_pass) < 4:
                            st.warning("A senha deve ter pelo menos 4 caracteres.")
                        elif len(new_user) < 3:
                            st.warning("O usuário deve ter pelo menos 3 caracteres.")
                        else:
                            success, message = register_user(session, new_user, new_pass)
                            if success:
                                st.success(message)
                                st.info("Conta criada! Acesse a aba de Login.")
                            else:
                                st.error(message)
                    else:
                        st.error("As senhas não coincidem.")

    return False
