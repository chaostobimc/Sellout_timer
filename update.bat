@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ===========================================================================
:: Sellout-Timer – Update-Skript (Windows CMD)
:: ===========================================================================
:: Prüft ob Git installiert ist, zieht die neueste Version aus dem
:: arena/019f6731-sellout-timer Branch und startet das Overlay neu.
::
:: Aufruf:  Doppelklick oder update.bat
:: ===========================================================================

cd /d "%~dp0"

echo.
echo [INFO]  Sellout-Timer Update (Windows)
echo.

set GIT_BRANCH=arena/019f6731-sellout-timer

:: ── 1. Git prüfen ───────────────────────────────────────────────────────────
echo [INFO]  Pruefe Git-Installation ...

where git >nul 2>&1
if !ERRORLEVEL! equ 0 (
    for /f "tokens=*" %%i in ('git --version 2^>nul') do echo [OK]    Git: %%i
) else (
    echo [ERROR] Git ist nicht installiert!
    echo.
    echo         Lade Git herunter von: https://git-scm.com/download/win
    echo         Installiere es (Standardeinstellungen sind OK).
    echo         Starte dann dieses Skript erneut.
    pause
    exit /b 1
)

:: ── 2. Prüfen ob wir in einem Git-Repo sind ─────────────────────────────────
if not exist ".git\" (
    echo [ERROR] Das ist kein Git-Repository!
    echo.
    echo         Klone das Repository zuerst:
    echo           git clone https://github.com/chaostobimc/Sellout_timer.git
    echo           cd Sellout_timer
    pause
    exit /b 1
)

:: ── 3. Remote setzen ────────────────────────────────────────────────────────
git remote get-url origin >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [INFO]  Setze Remote-URL ...
    git remote add origin https://github.com/chaostobimc/Sellout_timer.git
)

:: ── 4. Branch wechseln ──────────────────────────────────────────────────────
for /f "tokens=*" %%i in ('git branch --show-current 2^>nul') do set CURRENT_BRANCH=%%i

if not "!CURRENT_BRANCH!"=="%GIT_BRANCH%" (
    echo [INFO]  Wechsele zu Branch %GIT_BRANCH% ...
    git show-ref --verify refs/heads/%GIT_BRANCH% >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        git checkout %GIT_BRANCH%
    ) else (
        git fetch origin %GIT_BRANCH% >nul 2>&1 || git fetch origin >nul 2>&1
        git checkout -b %GIT_BRANCH% origin/%GIT_BRANCH%
    )
    echo [OK]    Jetzt auf Branch %GIT_BRANCH%
)

:: ── 5. Lokale Änderungen sichern ────────────────────────────────────────────
set STASHED=false
git diff --quiet HEAD >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [WARN]  Lokale Aenderungen werden zwischengespeichert (stash) ...
    git stash push -m "Auto-Stash vor Update %DATE% %TIME%" >nul
    echo [OK]    Aenderungen gesichert
    set STASHED=true
)

:: ── 6. Neueste Version pullen ───────────────────────────────────────────────
echo [INFO]  Hole neueste Version von %GIT_BRANCH% ...

git fetch origin %GIT_BRANCH%

for /f "tokens=*" %%i in ('git rev-parse HEAD') do set BEFORE=%%i

git pull origin %GIT_BRANCH% --ff-only >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [WARN]  Fast-Forward nicht moeglich, versuche Rebase ...
    git pull origin %GIT_BRANCH% --rebase >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Update fehlgeschlagen. Bitte Konflikte manuell loesen:
        echo          git status
        pause
        exit /b 1
    )
)

for /f "tokens=*" %%i in ('git rev-parse HEAD') do set AFTER=%%i

if not "!BEFORE!"=="!AFTER!" (
    echo [OK]    Update erfolgreich!
    git log --oneline !BEFORE!..!AFTER! 2>nul
) else (
    echo [OK]    Bereits auf dem neuesten Stand.
)

:: ── 7. Gestashte Änderungen zurück ──────────────────────────────────────────
if "%STASHED%"=="true" (
    echo [INFO]  Hole Aenderungen zurueck ...
    git stash pop >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo [WARN]  Stash konnte nicht automatisch angewendet werden
        echo         Pruefe: git stash list
    )
)

echo.
echo ==================================================================
echo  Update abgeschlossen!
echo ==================================================================
echo.

:: ── 8. setup.bat aufrufen → startet das Overlay ────────────────────────────
if exist "setup.bat" (
    echo [INFO]  Aktualisiere Abhaengigkeiten und starte ...
    echo.
    call setup.bat
) else (
    echo [INFO]  Starte main.py ...
    if exist ".venv\Scripts\python" (
        .venv\Scripts\python main.py
    ) else (
        python main.py
    )
    pause
)
