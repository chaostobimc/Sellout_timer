# Wiederherstellung von OverlaySystem.exe – Statusbericht

## Was funktioniert hat
Die .exe war ein mit **PyInstaller** gebündeltes Python-3.12-Programm (FastAPI/uvicorn-Backend
für einen Twitch/Minecraft-Overlay mit Discord-Bot). Ich konnte:

- Das PyInstaller-Archiv vollständig entpacken (`pyinstxtractor-ng`)
- Alle **Ressourcen 1:1 originalgetreu wiederherstellen** (nicht kompiliert, daher perfekt):
  - `frontend/` (alert.html, sound.html, timer.html, test.html + ein .bak)
  - `assets/` (3 Bilddateien)
  - `config.json`, `.env`, `.env.example`
- Die 8 eigenen Python-Module aus dem Bytecode dekompilieren (`main.py` +
  `backend/{__init__,config,discord_bot,events,minecraft,time_manager,twitch,websocket_manager}.py`)

## Wichtige Einschränkung
Python **3.12** führt neue Bytecode-Opcodes ein (z. B. `LOAD_FAST_AND_CLEAR`,
`POP_JUMP_IF_NONE`), die vom Dekompiler (`pycdc`) noch nicht vollständig unterstützt werden.
Ergebnis: Imports, Klassen-/Funktionssignaturen, Docstrings und einfache Funktionen sind
**vollständig und korrekt**. Komplexere Funktionen (mit try/except, async-Loops,
Dataclasses, Comprehensions) sind teilweise nur als Gerüst vorhanden und mit
`# WARNING: Decompyle incomplete` markiert:

| Datei | unvollständige Abschnitte |
|---|---|
| main.py | 7 |
| backend/config.py | 1 |
| backend/discord_bot.py | 4 |
| backend/events.py | 10 |
| backend/minecraft.py | 10 |
| backend/time_manager.py | 11 |
| backend/twitch.py | 7 |
| backend/websocket_manager.py | 4 |

## Für die Lücken: `_disassembly_for_incomplete_parts/`
Dort liegt die vollständige rohe Bytecode-Disassemblierung jeder Datei. Daraus lässt
sich jede fehlende Funktion Zeile für Zeile manuell rekonstruieren – mühsam, aber
möglich. Wenn du willst, gehe ich mit dir gezielt einzelne Funktionen durch (z. B.
`TimeManager._ticker_loop`, `MinecraftLogScanner`, den Discord-Bot-Handler) und
rekonstruiere sie gemeinsam mit dir anhand der Disassemblierung + der Docstrings/Variablennamen,
die erhalten geblieben sind.

## Empfehlung
Bau dir jetzt sofort eine Backup-Routine für den Sourcecode (Git-Repo, auch privat/lokal),
damit das nicht nochmal passiert – die exe ist ja weiterhin lauffähig, aber der Quellcode
war nur in ihr "eingefroren".
