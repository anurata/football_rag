@echo off
chcp 65001 > nul
echo ========================================================
echo  ⚽ J-League Tactical Analysis RAG Dashboard 起動中...
echo ========================================================
python -m streamlit run app.py
pause

