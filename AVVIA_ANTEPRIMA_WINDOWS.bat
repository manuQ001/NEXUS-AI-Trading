@echo off
setlocal
cd /d "%~dp0"
echo ================================================
echo NEXUS AI 2.7 - ANTEPRIMA PAPER TRADING
echo ================================================
echo Questa copia usa un database LOCALE nella cartella corrente.
echo Non elimina o aggiorna automaticamente la versione precedente.
echo.
where py >nul 2>&1
if errorlevel 1 (
  echo Python Launcher non trovato. Installa Python 3 e riprova.
  pause
  exit /b 1
)
py -3 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3 non disponibile. Controlla: py -0p
  pause
  exit /b 1
)
echo Avvio server locale su http://127.0.0.1:8765
echo Se la porta e occupata, chiudi prima la vecchia versione NEXUS.
echo Nessuna chiave API. Nessun ordine reale.
echo.
py -3 src\server.py
echo.
echo NEXUS terminato. Premi un tasto per chiudere.
pause >nul
