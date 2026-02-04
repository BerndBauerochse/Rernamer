#!/bin/bash
# Safe Update Script für Server
# Führt ein sicheres Update mit Backup durch

set -e  # Exit bei Fehler

echo "=== Audiobook Renamer - Safe Update ==="
echo ""

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Variablen
INSTALL_DIR="$HOME/audiobook_renamer_web"
BACKUP_DIR="$HOME/audiobook_renamer_backup_$(date +%Y%m%d_%H%M%S)"

# Prüfe ob Installation existiert
if [ ! -d "$INSTALL_DIR" ]; then
    echo -e "${RED}Fehler: Installation nicht gefunden in $INSTALL_DIR${NC}"
    exit 1
fi

# Schritt 1: Backup
echo -e "${CYAN}Schritt 1: Backup erstellen...${NC}"
mkdir -p "$BACKUP_DIR"

# Backup der Code-Dateien
echo "- Sichere Code-Dateien..."
cp "$INSTALL_DIR/backend/renamer_core.py" "$BACKUP_DIR/renamer_core.py.backup" || true
cp "$INSTALL_DIR/backend/main.py" "$BACKUP_DIR/main.py.backup" || true

# Backup der Datenbank
if [ -f "$INSTALL_DIR/data/metadata.db" ]; then
    echo "- Sichere Datenbank..."
    cp "$INSTALL_DIR/data/metadata.db" "$BACKUP_DIR/metadata.db.backup"
    echo -e "${GREEN}✓ Datenbank gesichert${NC}"
else
    echo -e "${YELLOW}⚠ Warnung: Keine Datenbank gefunden${NC}"
fi

# Backup der Logs
if docker ps | grep -q audiobook-renamer; then
    echo "- Sichere Container-Logs..."
    docker logs audiobook-renamer > "$BACKUP_DIR/container.log" 2>&1 || true
fi

echo -e "${GREEN}✓ Backup erstellt in: $BACKUP_DIR${NC}"
echo ""

# Schritt 2: Container stoppen
echo -e "${CYAN}Schritt 2: Container stoppen...${NC}"
cd "$INSTALL_DIR"
docker compose down
echo -e "${GREEN}✓ Container gestoppt${NC}"
echo ""

# Schritt 3: Code-Update
echo -e "${CYAN}Schritt 3: Code aktualisieren...${NC}"

# Suche nach Deployment-Paket
if [ -f "$HOME/audiobook_renamer_deploy_v2.1_*.zip" ]; then
    DEPLOY_ZIP=$(ls -t $HOME/audiobook_renamer_deploy_v2.1_*.zip | head -n 1)
    echo "- Gefunden: $DEPLOY_ZIP"
    
    # Entpacke nur die Code-Dateien (überschreibe data nicht!)
    echo "- Extrahiere neue Code-Dateien..."
    unzip -o "$DEPLOY_ZIP" "backend/*" "frontend/*" -d "$INSTALL_DIR"
    
    echo -e "${GREEN}✓ Code aktualisiert${NC}"
else
    echo -e "${YELLOW}⚠ Kein Deployment-Paket gefunden${NC}"
    echo "  Bitte lade ein audiobook_renamer_deploy_v2.1_*.zip hoch"
    echo ""
    
    # Alternative: Manuelle Datei-Angabe
    read -p "Pfad zum Deployment-ZIP (oder Enter zum Überspringen): " MANUAL_ZIP
    if [ -n "$MANUAL_ZIP" ] && [ -f "$MANUAL_ZIP" ]; then
        unzip -o "$MANUAL_ZIP" "backend/*" "frontend/*" -d "$INSTALL_DIR"
        echo -e "${GREEN}✓ Code aktualisiert${NC}"
    else
        echo -e "${RED}Abbruch. Bitte zuerst Deployment-Paket hochladen.${NC}"
        exit 1
    fi
fi
echo ""

# Schritt 4: Container neu bauen
echo -e "${CYAN}Schritt 4: Container neu bauen...${NC}"
cd "$INSTALL_DIR"
docker compose up -d --build

echo -e "${GREEN}✓ Container gestartet${NC}"
echo ""

# Schritt 5: Warten auf Start
echo -e "${CYAN}Schritt 5: Warte auf Container-Start...${NC}"
sleep 5

# Schritt 6: Health Check
echo -e "${CYAN}Schritt 6: Health Check...${NC}"

# Prüfe ob Container läuft
if docker ps | grep -q audiobook-renamer; then
    echo -e "${GREEN}✓ Container läuft${NC}"
else
    echo -e "${RED}✗ Container läuft NICHT${NC}"
    echo "Logs:"
    docker logs audiobook-renamer --tail 50
    echo ""
    echo -e "${YELLOW}Rollback empfohlen! Führe aus: ./rollback.sh${NC}"
    exit 1
fi

# Prüfe Web-UI
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ | grep -q "200"; then
    echo -e "${GREEN}✓ Web-UI erreichbar${NC}"
else
    echo -e "${YELLOW}⚠ Web-UI nicht erreichbar (prüfe Port-Mapping)${NC}"
fi

echo ""
echo -e "${GREEN}=== Update abgeschlossen! ===${NC}"
echo ""
echo "Nächste Schritte:"
echo "1. Öffne http://DEINE-SERVER-IP:8091"
echo "2. Prüfe Dashboard und Logs"
echo "3. Optional: Klicke 'Update DB'"
echo "4. Teste mit einem ZIP-File"
echo ""
echo "Backup gespeichert in: $BACKUP_DIR"
echo "Bei Problemen: Führe ./rollback.sh aus"
echo ""
