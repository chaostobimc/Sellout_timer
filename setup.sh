#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# Sellout-Timer – Setup-Skript
# ============================================================================
# Prüft Python, installiert UV, installiert alle Abhängigkeiten,
# legt .env an falls nötig und startet das Overlay.
#
# Aufruf:
#   chmod +x setup.sh && ./setup.sh
# ============================================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# ── Farben ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── 1. Python-Prüfung ──────────────────────────────────────────────────────
info "Prüfe Python-Installation …"

PYTHON=""
for cmd in python3 python3.12 python3.11 python3.10; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    error "Python 3.10+ ist nicht installiert."
    error ""
    error "Installiere Python z.B. mit deinem Paketmanager:"
    error "  Ubuntu/Debian:  sudo apt install python3 python3-pip python3-venv"
    error "  Arch Linux:     sudo pacman -S python python-pip"
    error "  macOS:          brew install python@3.12"
    error "  Windows:        https://www.python.org/downloads/"
    exit 1
fi

PY_VERSION="$($PYTHON --version 2>&1)"
info "Gefunden: $PY_VERSION ($PYTHON)"

# Prüfe Python-Version >= 3.10
PY_MAJOR=$($PYTHON -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$($PYTHON -c 'import sys; print(sys.version_info.minor)')
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    error "Python 3.10 oder neuer wird benötigt (gefunden: $PY_VERSION)"
    exit 1
fi
ok "Python-Version ausreichend"

# ── 2. UV installieren (falls nicht vorhanden) ──────────────────────────────
info "Prüfe UV (Python-Projektmanager) …"

if command -v uv &>/dev/null; then
    UV_EXEC="uv"
    UV_VERSION="$(uv --version 2>&1)"
    ok "UV bereits installiert: $UV_VERSION"
else
    warn "UV ist nicht installiert. Installiere UV …"
    # UV installiert sich selbst (offizielles Script)
    if command -v curl &>/dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget &>/dev/null; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        error "Weder curl noch wget gefunden. Installiere curl oder wget und versuche es erneut."
        exit 1
    fi

    # UV ins PATH bringen (das Install-Script legt es in ~/.cargo/bin/)
    if [ -f "$HOME/.cargo/bin/uv" ]; then
        export PATH="$HOME/.cargo/bin:$PATH"
    fi
    if command -v uv &>/dev/null; then
        ok "UV installiert: $(uv --version)"
    else
        error "UV konnte nicht installiert werden. Bitte manuell installieren: https://docs.astral.sh/uv/#installation"
        exit 1
    fi
fi

UV_EXEC="uv"

# ── 3. .env anlegen (falls nicht vorhanden) ─────────────────────────────────
if [ ! -f ".env" ]; then
    warn ".env nicht gefunden – lege .env aus .env.example an …"
    if [ -f ".env.example" ]; then
        cp .env.example .env
        ok ".env wurde aus .env.example erstellt."
        warn "  👉 Passe jetzt die Tokens in der .env an:"
        warn "     TWITCH_CLIENT_ID, TWITCH_USER_TOKEN, TWITCH_BROADCASTER_ID"
        warn "     DISCORD_BOT_TOKEN, DISCORD_ADMIN_USER_IDS"
        echo ""
    else
        warn ".env.example nicht gefunden – leere .env angelegt."
        touch .env
    fi
else
    ok ".env vorhanden"
fi

# ── 4. Abhängigkeiten installieren ──────────────────────────────────────────
info "Installiere Python-Abhängigkeiten mit UV …"

# Erstelle ggf. eine virtuelle Umgebung (UV macht das automatisch)
if [ ! -d ".venv" ]; then
    info "Erstelle virtuelle Umgebung (.venv) …"
    "$UV_EXEC" venv --python "$PYTHON" 2>/dev/null || "$UV_EXEC" venv 2>/dev/null || $PYTHON -m venv .venv
    ok "Virtuelle Umgebung erstellt"
fi

# requirements.txt installieren
if [ -f "requirements.txt" ]; then
    "$UV_EXEC" pip install -r requirements.txt 2>/dev/null || \
        "$UV_EXEC" pip sync requirements.txt 2>/dev/null || \
        .venv/bin/pip install -r requirements.txt
    ok "Abhängigkeiten installiert"
else
    warn "Keine requirements.txt gefunden – überspringe Installation"
fi

echo ""
ok "═══════════════════════════════════════════════════════════════"
ok "  Setup abgeschlossen! Starte das Overlay …"
ok "═══════════════════════════════════════════════════════════════"
echo ""

# ── 5. Overlay starten ─────────────────────────────────────────────────────
info "Starte main.py …"
echo ""

# Mit UV ausführen (falls .venv existiert, nutzt UV es automatisch)
exec "$UV_EXEC" run main.py
