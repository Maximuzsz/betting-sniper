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
    st.title("🎯 Sniper Pro: Bem-vindo!")
    
    # Inicializa o estado da sessão se não existir
    if 'page' not in st.session_state:
        st.session_state.page = 'Login'

    # Funções para mudar de página
    def go_to_signup():
        st.session_state.page = 'Signup'
    def go_to_login():
        st.session_state.page = 'Login'

    if st.session_state.page == 'Login':
        st.header("Login")
        with st.form("login_form"):
            username = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")

            if submitted:
                user = authenticate_user(session, username, password)
                if user:
                    st.session_state['logged_in'] = True
                    st.session_state['user_id'] = user.id
                    st.session_state['username'] = user.username
                    st.session_state['kelly_fraction'] = user.kelly_fraction
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos.")
        
        st.button("Não tem uma conta? Crie uma!", on_click=go_to_signup)
    
    elif st.session_state.page == 'Signup':
        st.header("Criar Conta")
        with st.form("signup_form"):
            username = st.text_input("Escolha um usuário")
            password = st.text_input("Escolha uma senha", type="password")
            confirm_password = st.text_input("Confirme a senha", type="password")
            submitted = st.form_submit_button("Registrar")

            if submitted:
                if password == confirm_password:
                    success, message = register_user(session, username, password)
                    if success:
                        st.success(message)
                        go_to_login()
                        st.rerun()
                    else:
                        st.error(message)
                else:
                    st.error("As senhas não coincidem.")
        
        st.button("Já tem uma conta? Faça login!", on_click=go_to_login)

    return False
