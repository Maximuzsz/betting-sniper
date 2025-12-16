# Betting Sniper

Streamlit application for sports betting analysis using mathematical models and AI.

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project root:

```
ODDS_API_KEY="your_key"
GEMINI_KEY="your_key"
POSTGRES_USER="admin"
POSTGRES_PASSWORD="admin123"
POSTGRES_DB="sniper_db"
POSTGRES_HOST="localhost"
POSTGRES_PORT="5432"
```

## Running

```bash
streamlit run app.py
```

## Features

- Automatic statistics fetching (free)
- Mathematical analysis with Poisson distribution
- AI analysis (Google Gemini)
- Bankroll management (Kelly Criterion)
