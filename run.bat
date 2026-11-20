@echo off
rem One command to set up and start the dashboard (Windows). Needs Python 3.11+.
cd /d "%~dp0"
if not exist .venv (
  echo Setting up ^(first time only, a few minutes^)...
  python -m venv .venv
  .venv\Scripts\python -m pip install -q --upgrade pip
  .venv\Scripts\pip install -q -r requirements.txt
)
if not exist .env copy .env.example .env
echo Opening http://localhost:8501
.venv\Scripts\streamlit run app.py
