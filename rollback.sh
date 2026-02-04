#!/bin/bash
# Rollback Script - Stellt alte Version wieder her

set -e

echo "=== Audiobook Renamer - Rollback ==="
echo ""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

INSTALL_DIR="$HOME/audiobook_renamer_web"

# Finde neuestes Backup
LATEST_BACKUP=$(ls -td $HOME/audiobook_renamer_backup_* 2>/dev/null | head -n 1)

if [ -z "$LATEST_BACKUP" ]; then
    echo -e "${RED}Fehler: Kein Backup gefunden!${NC}"
    echo "Erwarteter Pfad: $HOME/audiobook_renamer_backup_*"
    exit 1
fi

echo -e "${YELLOW}Gefundenes Backup: $LATEST_BACKUP${NC}"
echo ""

# Bestätigung
read -p "Rollback durchführen? (y/n): " CONFIRM
if [ "$CONFIRM" != "y" ]; then
    echo "Abbruch."
    exit 0
fi

# Container stoppen
echo -e "${CYAN}Stoppe Container...${NC}"
cd "$INSTALL_DIR"
docker compose down

# Code-Dateien wiederherstellen
echo -e "${CYAN}Stelle Code-Dateien wieder her...${NC}"

if [ -f "$LATEST_BACKUP/renamer_core.py.backup" ]; then
    cp "$LATEST_BACKUP/renamer_core.py.backup" "$INSTALL_DIR/backend/renamer_core.py"
    echo -e "${GREEN}✓ renamer_core.py wiederhergestellt${NC}"
fi

if [ -f "$LATEST_BACKUP/main.py.backup" ]; then
    cp "$LATEST_BACKUP/main.py.backup" "$INSTALL_DIR/backend/main.py"
    echo -e "${GREEN}✓ main.py wiederhergestellt${NC}"
fi

# Datenbank wiederherstellen (optional)
if [ -f "$LATEST_BACKUP/metadata.db.backup" ]; then
    read -p "Datenbank auch wiederherstellen? (y/n): " DB_RESTORE
    if [ "$DB_RESTORE" = "y" ]; then
        cp "$LATEST_BACKUP/metadata.db.backup" "$INSTALL_DIR/data/metadata.db"
        echo -e "${GREEN}✓ Datenbank wiederhergestellt${NC}"
    fi
fi

# Container neu starten
echo -e "${CYAN}Starte Container neu...${NC}"
docker compose up -d --build

echo ""
echo -e "${GREEN}=== Rollback abgeschlossen ===${NC}"
echo ""
echo "Container läuft wieder mit alter Version."
echo "Prüfe: http://DEINE-SERVER-IP:8091"
echo ""
