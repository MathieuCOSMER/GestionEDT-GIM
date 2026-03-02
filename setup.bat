@echo off
echo ============================================
echo   Setup - Gestion EDT IUT GIM Toulon
echo ============================================
echo.

echo [1] Creation du venv...
python -m venv .venv
if errorlevel 1 (
    echo ERREUR: Python non trouve. Installez Python 3.10+ depuis python.org
    pause
    exit /b 1
)

echo [2] Activation du venv...
call .venv\Scripts\activate.bat

echo [3] Installation des dependances...
pip install -r requirements.txt -q

echo.
echo ============================================
echo   Setup termine !
echo ============================================
echo.
echo   Pour lancer le serveur :
echo     .venv\Scripts\activate
echo     python run.py
echo.
pause
