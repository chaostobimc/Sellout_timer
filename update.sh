#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# Sellout-Timer – Update-Skript
# ============================================================================
# Prüft ob Git installiert ist, zieht die neueste Version aus dem
# arena/019f6731-sellout-timer Branch und startet das Overlay neu.
#
# Aufruf:
#   chmod +x update.sh && ./update.sh
# ============================================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# ── Farben ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

GIT_BRANCH="arena/019f6731-sellout-timer"

# ── 1. Git prüfen / installieren ────────────────────────────────────────────
info "Prüfe Git-Installation …"

if command -v git &>/dev/null; then
    GIT_VERSION="$(git --version 2>&1)"
    ok "Git gefunden: $GIT_VERSION"
else
    warn "Git ist nicht installiert. Installiere Git …"
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y -qq git
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm git
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y git
    elif command -v brew &>/dev/null; then
        brew install git
    else
        error "Konnte Git nicht automatisch installieren."
        error "Bitte installiere Git manuell: https://git-scm.com/downloads"
        exit 1
    fi
    ok "Git installiert: $(git --version)"
fi

# ── 2. Prüfen ob wir uns in einem Git-Repo befinden ─────────────────────────
if [ ! -d ".git" ]; then
    error "Das ist kein Git-Repository!"
    error "Bitte klone das Repository zuerst:"
    error "  git clone https://github.com/chaostobimc/Sellout_timer.git"
    error "  cd Sellout_timer"
    exit 1
fi

# ── 3. Remote-URL prüfen / setzen ───────────────────────────────────────────
REMOTE_URL="$(git remote get-url origin 2>/dev/null || true)"
if [ -z "$REMOTE_URL" ]; then
    info "Setze Remote-URL auf origin …"
    git remote add origin https://github.com/chaostobimc/Sellout_timer.git
    ok "Remote origin hinzugefügt"
fi

# ── 4. Branch wechseln / erstellen ──────────────────────────────────────────
CURRENT_BRANCH="$(git branch --show-current 2>/dev/null || true)"

if [ "$CURRENT_BRANCH" != "$GIT_BRANCH" ]; then
    info "Wechsle zu Branch $GIT_BRANCH …"
    # Prüfen ob Branch lokal existiert
    if git show-ref --verify "refs/heads/$GIT_BRANCH" &>/dev/null; then
        git checkout "$GIT_BRANCH"
    else
        # Branch von Remote holen
        git fetch origin "$GIT_BRANCH" 2>/dev/null || git fetch origin
        if git show-ref --verify "refs/remotes/origin/$GIT_BRANCH" &>/dev/null; then
            git checkout -b "$GIT_BRANCH" "origin/$GIT_BRANCH"
        else
            error "Branch $GIT_BRANCH existiert weder lokal noch auf remote."
            error "Verfügbare Branches:"
            git branch -a
            exit 1
        fi
    fi
    ok "Jetzt auf Branch $GIT_BRANCH"
fi

# ── 5. Lokale Änderungen sichern (stash) ────────────────────────────────────
if ! git diff --quiet HEAD 2>/dev/null; then
    warn "Es gibt lokale Änderungen. Diese werden zwischengespeichert (stash) …"
    git stash push -m "Auto-Stash vor Update $(date '+%Y-%m-%d %H:%M')"
    ok "Änderungen im Stash gesichert"
    STASHED=true
else
    STASHED=false
fi

# ── 6. Neueste Version pullen ───────────────────────────────────────────────
info "Hole neueste Version von $GIT_BRANCH …"

# Erst fetch, dann pull
git fetch origin "$GIT_BRANCH"

BEFORE="$(git rev-parse HEAD)"
git pull origin "$GIT_BRANCH" --ff-only 2>/dev/null || {
    warn "Fast-Forward nicht möglich – versuche Rebase …"
    git pull origin "$GIT_BRANCH" --rebase 2>/dev/null || {
        error "Update fehlgeschlagen. Bitte Konflikte manuell lösen:"
        error "  git status"
        exit 1
    }
}
AFTER="$(git rev-parse HEAD)"

if [ "$BEFORE" != "$AFTER" ]; then
    ok "Update erfolgreich! $(git log --oneline "$BEFORE..$AFTER" | wc -l) neue Commit(s)"
    git log --oneline "$BEFORE..$AFTER"
else
    ok "Bereits auf dem neuesten Stand."
fi

# ── 7. Gestashte Änderungen zurückholen ─────────────────────────────────────
if [ "$STASHED" = true ]; then
    STASH_LIST="$(git stash list 2>/dev/null)"
    if [ -n "$STASH_LIST" ]; then
        info "Hole zwischengespeicherte Änderungen zurück …"
        git stash pop 2>/dev/null || warn "Stash konnte nicht automatisch angewendet werden (git stash list)"
    fi
fi

echo ""
ok "═══════════════════════════════════════════════════════════════"
ok "  Update abgeschlossen! Starte das Overlay neu …"
ok "═══════════════════════════════════════════════════════════════"
echo ""

# ── 8. Überprüfen ob setup.sh existiert und ggf. Abhängigkeiten updaten ─────
if [ -f "setup.sh" ]; then
    info "Rufe setup.sh auf, um Abhängigkeiten zu aktualisieren …"
    echo ""
    bash setup.sh
else
    # Fallback: direkt mit UV starten
    if command -v uv &>/dev/null; then
        info "Starte main.py mit UV …"
        exec uv run main.py
    elif [ -f ".venv/bin/python" ]; then
        info "Starte main.py mit .venv …"
        exec .venv/bin/python main.py
    else
        info "Starte main.py mit python3 …"
        exec python3 main.py
    fi
fi
