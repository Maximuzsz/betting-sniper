import streamlit as st
from datetime import datetime
from sqlalchemy.orm import sessionmaker
from models.models import engine, Match, Prediction, Wallet, User

Session = sessionmaker(bind=engine)

# --- FUNÇÕES DE CONSULTA E ATUALIZAÇÃO NO BANCO ---

def get_wallet_balance(user_id):
    session = Session()
    try:
        wallet = session.query(Wallet).filter_by(user_id=user_id).first()
        return wallet.balance if wallet else 0.0
    finally:
        session.close()

def update_wallet_balance(user_id, new_balance):
    """Define o saldo da carteira para um valor específico."""
    session = Session()
    try:
        wallet = session.query(Wallet).filter_by(user_id=user_id).first()
        if wallet:
            wallet.balance = new_balance
            wallet.updated_at = datetime.utcnow()
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        print(f"Erro ao atualizar a banca: {e}")
        return False
    finally:
        session.close()

def update_user_kelly_fraction(user_id, new_fraction):
    """Atualiza a fração de Kelly para um usuário específico."""
    session = Session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if user:
            user.kelly_fraction = new_fraction
            session.commit()
            st.session_state['kelly_fraction'] = new_fraction
            return True
        return False
    except Exception as e:
        session.rollback()
        print(f"Erro ao atualizar a fração de Kelly: {e}")
        return False
    finally:
        session.close()

def resolve_bet(prediction_id, result, user_id):
    session = Session()
    try:
        pred = session.query(Prediction).filter_by(id=prediction_id, user_id=user_id).first()
        if not pred or pred.status != 'PENDING':
            return False
        
        pred.status = result
        wallet = session.query(Wallet).filter_by(user_id=user_id).first()
        
        if result == 'GREEN':
            odd_final = pred.odd_home_used if pred.final_prob_home > 0.5 else pred.odd_away_used
            return_amount = pred.stake * odd_final
            wallet.balance += return_amount
        
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        print(f"Erro ao resolver aposta: {e}")
        return False
    finally:
        session.close()

def save_to_db(user_id, match_data, inputs, odds, math_res, ai_res, final_prob, ev, selected_side, stake):
    session = Session()
    try:
        wallet = session.query(Wallet).filter_by(user_id=user_id).first()
        if not wallet or wallet.balance < stake:
            return False, "Saldo insuficiente!"

        match_entry = session.query(Match).filter_by(home_team=match_data['home_team'], away_team=match_data['away_team']).first()
        if not match_entry:
            match_entry = Match(
                home_team=match_data['home_team'], away_team=match_data['away_team'],
                commence_time=datetime.fromisoformat(match_data['commence_time'].replace('Z', '+00:00')),
                league_key="manual_entry"
            )
            session.add(match_entry)
            session.flush()

        wallet.balance -= stake
        
        pred = Prediction(
            match_id=match_entry.id,
            user_id=user_id,
            input_home_goals_avg=float(inputs['h_s']),
            input_home_conceded_avg=float(inputs['h_c']),
            input_away_goals_avg=float(inputs['a_s']),
            input_away_conceded_avg=float(inputs['a_c']),
            bookmaker_name="Agregado",
            odd_home_used=float(odds['home']),
            odd_away_used=float(odds['away']),
            math_prob_home=float(math_res['home_win']),
            ai_delta_adjustment=float(ai_res.get('delta_home', 0)),
            final_prob_home=float(final_prob),
            expected_value=float(ev),
            is_value_bet=(ev > 0.05),
            ai_analysis_json=ai_res,
            stake=float(stake),
            status='PENDING'
        )
        session.add(pred)
        session.commit()
        return True, "Sucesso"
    except Exception as e:
        session.rollback()
        return False, str(e)
    finally:
        session.close()
