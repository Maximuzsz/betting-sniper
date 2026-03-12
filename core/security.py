import os
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone

# Configurações de Token (mantenha as suas)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "sniper_secreto_super_seguro_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

def get_password_hash(password: str) -> str:
    """Gera o hash da senha usando bcrypt puro."""
    # Transforma a string em bytes
    pwd_bytes = password.encode('utf-8')
    # Gera o salt e o hash
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    # Retorna como string para salvar no banco
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha bate com o hash salvo."""
    pwd_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(pwd_bytes, hashed_bytes)

def create_access_token(data: dict) -> str:
    """Gera o JWT (mantenha sua lógica atual)"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt