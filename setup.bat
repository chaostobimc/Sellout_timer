@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ===========================================================================
:: Sellout-Timer – Setup-Skript (Windows CMD)
:: ===========================================================================
:: Prüft Python, installiert UV, installiert alle Abhängigkeiten,
:: legt .env an falls nötig und startet das Overlay.
::
:: Aufruf:  Doppelklick oder setup.bat
:: ===========================================================================

cd /d "%~dp0"

echo.
echo [INFO]  Sellout-Timer Setup (Windows)
echo.

:: ── 1. Python prüfen ───────────────────────────────────────────────────────
echo [INFO]  Pruefe Python-Installation ...

set PYTHON=
where python >nul 2>&1
if !ERRORLEVEL! equ 0 ( set PYTHON=python ) else (
where python3 >nul 2>&1
if !ERRORLEVEL! equ 0 ( set PYTHON=python3 ) else (
where py >nul 2>&1
if !ERRORLEVEL! equ 0 ( set PYTHON=py )))

if "%PYTHON%"=="" (
    echo [ERROR] Python 3.10+ ist nicht installiert.
    echo.
    echo         Lade Python herunter von: https://www.python.org/downloads/
    echo         WICHTIG: Beim Installieren "Add Python to PATH" HAKEN!
    pause
    exit /b 1
)

%PYTHON% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Python 3.10 oder neuer wird benoetigt.
    %PYTHON% --version
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('%PYTHON% --version 2^>nul') do set PY_VERSION=%%i
echo [OK]    %PY_VERSION% gefunden (%PYTHON%)

:: ── 2. Virtuelle Umgebung erstellen ─────────────────────────────────────────
if not exist ".venv\" (
    echo [INFO]  Erstelle virtuelle Umgebung (.venv) ...
    %PYTHON% -m venv .venv
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Konnte virtuelle Umgebung nicht erstellen.
        pause
        exit /b 1
    )
    echo [OK]    .venv erstellt
) else (
    echo [OK]    .venv vorhanden
)

:: ── 3. UV installieren / checken ────────────────────────────────────────────
echo [INFO]  Pruefe UV (optional, beschleunigt die Installation) ...
where uv >nul 2>&1
if !ERRORLEVEL! equ 0 (
    for /f "tokens=*" %%i in ('uv --version 2^>nul') do echo [OK]    UV: %%i
) else (
    echo [WARN]  UV nicht gefunden – verwende pip (langsamer, aber funktioniert).
    echo [WARN]  UV installieren: powershell -c "irm https://astral.sh/uv/install.ps1 ^| iex"
    echo.
)

:: ── 4. Abhängigkeiten installieren ──────────────────────────────────────────
echo [INFO]  Installiere Python-Abhaengigkeiten ...

if exist "requirements.txt" (
    where uv >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        echo [INFO]  Installiere mit UV ...
        uv pip install -r requirements.txt 2>nul
        if !ERRORLEVEL! neq 0 (
            echo [WARN]  UV-Fehler, versuche pip ...
            call .venv\Scripts\pip install -r requirements.txt
        )
    ) else (
        call .venv\Scripts\pip install -r requirements.txt
    )
    if !ERRORLEVEL! equ 0 (
        echo [OK]    Abhaengigkeiten installiert
    ) else (
        echo [ERROR] Fehler bei der Installation der Abhaengigkeiten.
        pause
        exit /b 1
    )
) else (
    echo [WARN]  Keine requirements.txt gefunden!
)

:: ── 5. .env anlegen (falls nicht vorhanden) ─────────────────────────────────
if not exist ".env" (
    echo [WARN]  .env nicht gefunden ...
    if exist ".env.example" (
        copy .env.example .env >nul
        echo [OK]    .env wurde aus .env.example erstellt.
        echo [WARN]  👉 WICHTIG: Oeffne die .env mit einem Editor
        echo [WARN]     und trage deine Twitch-/Discord-Tokens ein!
    ) else (
        echo [WARN]  Keine .env.example – leere .env angelegt.
        type nul > .env
    )
) else (
    echo [OK]    .env vorhanden
)

echo.
echo ==================================================================
echo  Setup abgeschlossen!
echo ==================================================================
echo.
echo [INFO]  Starte main.py ...
echo.

:: ── 6. Overlay starten ─────────────────────────────────────────────────────
where uv >nul 2>&1
if !ERRORLEVEL! equ 0 (
    uv run main.py
) else (
    .venv\Scripts\python main.py
)

echo.
echo [INFO]  Overlay beendet.
pause
