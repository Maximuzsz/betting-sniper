# Betting Sniper

This is a Streamlit application that uses a combination of mathematical models and AI to find value in sports betting markets.

## Setup

1.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

2.  **Set up environment variables:**

    Create a `.env` file in the root of the project and add the following variables:

    ```
    ODDS_API_KEY="SUA_CHAVE_ODDS_API"
    GEMINI_KEY="SUA_CHAVE_GEMINI"
    POSTGRES_USER="admin"
    POSTGRES_PASSWORD="admin123"
    POSTGRES_DB="sniper_db"
    POSTGRES_HOST="localhost"
    POSTGRES_PORT="5432"
    ```

    Replace `"SUA_CHAVE_ODDS_API"` and `"SUA_CHAVE_GEMINI"` with your actual API keys.

## Running the application

```bash
streamlit run app.py
```
