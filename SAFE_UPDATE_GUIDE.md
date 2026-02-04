# Safe Update Guide - Audiobook Renamer v2.1

**Datum**: 2026-01-27  
**Änderung**: Abridged Status Integration (Hörspiel, Gekürzt, Ungekürzt)

---

## 🎯 Ziel

Sicheres Update ohne Datenverlust und mit Rollback-Option.

---

## ⚠️ Was wird geändert?

### Code-Änderungen:
- ✅ `backend/renamer_core.py` - Umbenennung mit Status
- ✅ `backend/main.py` - API-Suche mit Status
- ❌ **KEINE** Änderungen an:
  - Datenbank-Schema
  - Frontend
  - Docker-Konfiguration
  - ZIP-Handling
  - Audio-/Cover-Optimierung

### Neue Funktionalität:
- Ordner werden mit Status benannt: `Titel_Hsp`, `Titel (gekuerzt)`, `Titel (ungekuerzt)`

---

## 📋 Schritt-für-Schritt Update

### **Phase 1: Backup (WICHTIG!)**

#### 1.1 Datenbank sichern
```bash
# Auf dem Server (via SSH)
cd audiobook_renamer_web
cp data/metadata.db data/metadata.db.backup_$(date +%Y%m%d)
```

#### 1.2 Aktuelle Container-Konfiguration sichern
```bash
# Container-ID und Version notieren
docker ps | grep audiobook
docker logs audiobook-renamer > logs_backup_$(date +%Y%m%d).txt
```

---

### **Phase 2: Paralleles Testen (Optional aber empfohlen)**

Du kannst die neue Version **parallel** zur alten testen:

#### 2.1 Deployment-Paket erstellen
```powershell
# Auf deinem Windows-Client
cd C:\Users\inuit\antigravity\audiobook_renamer_web

# Paket erstellen (ohne data-Ordner!)
Compress-Archive -Path backend,frontend,Dockerfile,docker-compose.yml,README.md,PROJECT_DOCUMENTATION.md -DestinationPath audiobook_renamer_deploy_v21.zip -Force
```

#### 2.2 Auf Server hochladen
```powershell
# Von Windows aus
scp audiobook_renamer_deploy_v21.zip root@DEINE-SERVER-IP:~/
```

#### 2.3 Parallel-Installation auf Server
```bash
# Auf dem Server
cd ~

# Neuen Test-Ordner erstellen
unzip audiobook_renamer_deploy_v21.zip -d audiobook_renamer_web_v21
cd audiobook_renamer_web_v21

# Datenbank aus alter Installation kopieren
mkdir -p data
cp ../audiobook_renamer_web/data/metadata.db ./data/

# docker-compose.yml für Test-Port anpassen
nano docker-compose.yml
```

**Ändere in `docker-compose.yml`:**
```yaml
services:
  renamer:
    container_name: audiobook-renamer-v21-test  # <-- NEU
    ports:
      - "8092:8000"  # <-- NEU (statt 8091)
```

#### 2.4 Test-Container starten
```bash
docker compose up -d --build
```

#### 2.5 Test-Zugriff
```
Alte Version: http://SERVER-IP:8091
Neue Version: http://SERVER-IP:8092  ← TEST
```

---

### **Phase 3: Funktionstests**

#### 3.1 Test 1: Web-UI verfügbar?
- [ ] Öffne `http://SERVER-IP:8092`
- [ ] Dashboard lädt?
- [ ] Settings lädt?
- [ ] Logs werden angezeigt?

#### 3.2 Test 2: Datenbank geladen?
- [ ] Klicke auf "Settings" → "Show Inventory"
- [ ] Werden Titel angezeigt?
- [ ] Sind Covers sichtbar?

#### 3.3 Test 3: API funktioniert?
```bash
# Test-Anfrage
curl "http://SERVER-IP:8092/api/abs/search?q=Harry%20Potter"
```

Erwartete Antwort: JSON mit matches

#### 3.4 Test 4: Scan-Test (TROCKENTEST)

**WICHTIG**: Teste NICHT im echten Library-Ordner!

```bash
# Test-Ordner erstellen
mkdir -p /tmp/renamer_test
echo "test" > /tmp/renamer_test/9783000000001.zip
```

1. Gehe zu Settings
2. Ändere Library Path auf `/host_mnt/tmp/renamer_test`
3. Klicke "Save"
4. Klicke "Run Scan"
5. Beobachte Logs

#### 3.5 Test 5: Namensschema-Test (Optional)

Falls du ein echtes ZIP-File mit bekannter EAN hast:

```bash
# Kopiere ein Test-ZIP (NICHT im echten Library!)
cp /DATA/Media/audiobooks/9783257243048.zip /tmp/renamer_test/
```

**Erwartetes Verhalten:**
- ZIP wird entpackt
- DB-Lookup erfolgt
- Falls `abridged_status = "Hörspiel"` → Ordner endet mit `_Hsp`
- Falls `abridged_status = "Gekürzt"` → Ordner endet mit `(gekuerzt)`
- etc.

---

### **Phase 4: Produktions-Update**

**NUR wenn alle Tests erfolgreich waren!**

#### 4.1 Alte Version stoppen
```bash
cd ~/audiobook_renamer_web
docker compose down
```

#### 4.2 Code-Dateien austauschen
```bash
# Backup der alten Code-Dateien
cp backend/renamer_core.py backend/renamer_core.py.backup
cp backend/main.py backend/main.py.backup

# Neue Dateien kopieren
cp ~/audiobook_renamer_web_v21/backend/renamer_core.py backend/
cp ~/audiobook_renamer_web_v21/backend/main.py backend/
```

#### 4.3 Produktions-Container neu starten
```bash
docker compose up -d --build
```

#### 4.4 Logs überwachen
```bash
docker logs -f audiobook-renamer
```

Prüfe auf Fehler beim Start.

---

### **Phase 5: Validierung**

#### 5.1 Produktions-Tests
- [ ] Web-UI erreichbar: `http://SERVER-IP:8091`
- [ ] Logs zeigen keine Fehler
- [ ] "Update DB" funktioniert
- [ ] API antwortet: `curl "http://SERVER-IP:8091/api/abs/search?q=test"`

#### 5.2 Echter Scan-Test
**ERST wenn alles funktioniert:**

1. Lege ein neues ZIP-File in deinen Library-Ordner
2. Triggere "Run Scan"
3. Prüfe ob Ordnername korrekt ist (mit Status-Suffix)

---

## 🔄 Rollback-Plan

Falls etwas schief geht:

### Methode 1: Code zurücksetzen
```bash
cd ~/audiobook_renamer_web

# Container stoppen
docker compose down

# Alte Code-Dateien wiederherstellen
cp backend/renamer_core.py.backup backend/renamer_core.py
cp backend/main.py.backup backend/main.py

# Container neu starten
docker compose up -d --build
```

### Methode 2: Kompletter Rollback
```bash
# Neue Version komplett löschen
cd ~
docker compose -f audiobook_renamer_web/docker-compose.yml down
rm -rf audiobook_renamer_web

# Ordner umbenennen (falls du die alte Version noch hast)
# ODER: Alte Version neu deployen
```

### Methode 3: Datenbank zurücksetzen (selten nötig)
```bash
cd ~/audiobook_renamer_web/data
cp metadata.db.backup_DATUM metadata.db
```

---

## 📊 Vergleichstabelle

| Feature | Alte Version | Neue Version |
|---------|--------------|--------------|
| ZIP entpacken | ✅ | ✅ |
| DB-Lookup | ✅ | ✅ |
| Audio-Optimierung | ✅ | ✅ |
| Cover-Optimierung | ✅ | ✅ |
| Takedown-Check | ✅ | ✅ |
| Ordnername ohne Status | ✅ | ✅ (Fallback) |
| Ordnername mit Status | ❌ | ✅ **NEU** |
| Hörspiel `_Hsp` | ❌ | ✅ **NEU** |
| Gekürzt `(gekuerzt)` | ❌ | ✅ **NEU** |
| Ungekürzt `(ungekuerzt)` | ❌ | ✅ **NEU** |

---

## ✅ Checkliste

### Vor dem Update:
- [ ] Datenbank gesichert (`metadata.db.backup`)
- [ ] Container-Logs gesichert
- [ ] Test-Container gestartet (Port 8092)
- [ ] Alle Tests erfolgreich

### Nach dem Update:
- [ ] Produktions-Container läuft
- [ ] Web-UI erreichbar
- [ ] Logs zeigen keine Fehler
- [ ] API funktioniert
- [ ] Test-Scan erfolgreich

### Bei Problemen:
- [ ] Rollback-Code bereit
- [ ] Backup vorhanden
- [ ] Log-Dateien gesichert

---

## 🆘 Troubleshooting

### Problem: Container startet nicht
```bash
# Logs prüfen
docker logs audiobook-renamer

# Häufige Ursachen:
# - Syntax-Fehler in Python → Logs zeigen Traceback
# - Port bereits belegt → docker-compose.yml prüfen
```

**Lösung**: Rollback auf alte Code-Dateien (siehe oben)

### Problem: Web-UI zeigt Fehler
```bash
# Browser-Console öffnen (F12)
# Netzwerk-Tab prüfen

# API-Verbindung testen
curl http://SERVER-IP:8091/api/config
```

### Problem: Ordner werden nicht umbenannt
```bash
# Logs in Echtzeit ansehen
docker logs -f audiobook-renamer

# Prüfe ob:
# 1. EAN in Datenbank existiert
# 2. abridged_status gesetzt ist
# 3. Keine Fehler beim Sanitize
```

---

## 📞 Support

Falls du Probleme hast, sammle folgende Infos:

1. **Container-Logs**:
   ```bash
   docker logs audiobook-renamer > problem_logs.txt
   ```

2. **DB-Check**:
   ```bash
   sqlite3 data/metadata.db "SELECT ean, title, abridged_status FROM books LIMIT 5;"
   ```

3. **Test-Anfrage**:
   ```bash
   curl -v "http://SERVER-IP:8091/api/abs/search?q=test" > api_test.txt
   ```

Dann können wir gezielt debuggen! 🔍
