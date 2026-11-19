@echo off
setlocal EnableExtensions
title NEXUS AI - Download automatico anteprima
echo ==================================================
echo    NEXUS AI - SCARICA E AVVIA ULTIMA ANTEPRIMA
echo ==================================================
echo.
echo Scarica l'ultimo codice dal repository GitHub ufficiale.
echo Non tocca la versione gia' installata o il suo database.
echo Richiede Windows PowerShell e Python 3.12.
echo.
where py >nul 2>&1
if errorlevel 1 (
  echo ERRORE: Python Launcher non disponibile.
  pause
  exit /b 1
)
py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo ERRORE: Python 3.12 non disponibile.
  pause
  exit /b 1
)
set "NEXUS_PREVIEW=%LOCALAPPDATA%\NEXUS-AI"
if not exist "%NEXUS_PREVIEW%" mkdir "%NEXUS_PREVIEW%"
set "NEXUS_ZIP=%TEMP%\nexus-ai-preview-%RANDOM%.zip"
set "NEXUS_EXTRACT=%NEXUS_PREVIEW%\preview-%RANDOM%-%RANDOM%"
echo Scarico da github.com/manuQ001/NEXUS-AI-Trading ...
powershell.exe -NoProfile -NonInteractive -Command "$ErrorActionPreference='Stop'; $u='https://github.com/manuQ001/NEXUS-AI-Trading/archive/refs/heads/main.zip'; Invoke-WebRequest -Uri $u -OutFile $env:NEXUS_ZIP -MaximumRedirection 5; Expand-Archive -LiteralPath $env:NEXUS_ZIP -DestinationPath $env:NEXUS_EXTRACT -Force"
if errorlevel 1 (
  echo ERRORE: download o estrazione non riusciti. Controlla la connessione.
  if exist "%NEXUS_ZIP%" del "%NEXUS_ZIP%"
  pause
  exit /b 1
)
if exist "%NEXUS_ZIP%" del "%NEXUS_ZIP%"
set "NEXUS_DIR=%NEXUS_EXTRACT%\NEXUS-AI-Trading-main"
if not exist "%NEXUS_DIR%\src\server.py" (
  echo ERRORE: pacchetto non riconosciuto.
  pause
  exit /b 1
)
if not exist "%NEXUS_DIR%\src\orderbook.py" (
  echo ERRORE: mancano i moduli nuovi. Download incompleto.
  pause
  exit /b 1
)
echo.
echo Eseguo i test locali PRIMA del primo avvio...
cd /d "%NEXUS_DIR%"
py -3.12 -m unittest discover -s tests -p "test_*.py"
if errorlevel 1 (
  echo ERRORE: test non superati. Anteprima NON avviata.
  pause
  exit /b 1
)
echo.
echo Test superati. Se hai NEXUS 2.5 aperto, chiudilo (CTRL+C).
echo La porta 8765 deve essere libera.
echo Directory anteprima: "%NEXUS_DIR%"
echo Il database della 2.5 NON viene copiato o modificato.
echo.
py -3.12 src\server.py
echo.
echo Anteprima chiusa. La versione precedente e' rimasta invariata.
pause
endlocal
