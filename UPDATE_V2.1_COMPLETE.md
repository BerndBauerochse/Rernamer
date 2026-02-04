# Audiobook Renamer v2.1 - Vollständiges Update

**Datum**: 2026-01-27  
**Version**: v2.1 (Abridged Status + Metadata Integration)

---

## 🎯 Ziel des Updates

Behebung des Namenskonflikts bei unterschiedlichen Versionen (Hörspiel, Gekürzt, Ungekürzt) des gleichen Titels und Wiederherstellung der Audiobookshelf-Integration über `metadata.json`.

---

## 📋 Durchgeführte Änderungen

### **1. Ordnernamen-Schema (renamer_core.py)**

**Datei**: `backend/renamer_core.py` (Zeilen 253-279)

**Neue Namenslogik** basierend auf `abridged_status` aus der Datenbank:

| DB: `abridged_status` | Ordnername | Beispiel |
|----------------------|------------|----------|
| `NULL` / leer | `Titel` | `Schweinekopf al dente` |
| `"Gekürzt"` | `Titel (gekuerzt)` | `Schweinekopf al dente (gekuerzt)` |
| `"Ungekürzt"` | `Titel (ungekuerzt)` | `Sauerkrautkoma (ungekuerzt)` |
| `"Hörspiel"` | `Titel_Hsp` | `Grießnockerlaffäre_Hsp` |

**Code-Auszug**:
```python
final_title = safe_title
if book.abridged_status:
    status_lower = book.abridged_status.lower().strip()
    
    if "hörspiel" in status_lower or "hoerspiel" in status_lower or "hsp" in status_lower:
        final_title = f"{safe_title}_Hsp"
    elif "ungekürzt" in status_lower or "ungekuerzt" in status_lower or "unabridged" in status_lower:
        final_title = f"{safe_title} (ungekuerzt)"
    elif "gekürzt" in status_lower or "gekuerzt" in status_lower or "abridged" in status_lower:
        final_title = f"{safe_title} (gekuerzt)"
```

**Ergebnis**: Alle 4 Versionen eines Titels können jetzt parallel existieren ohne Konflikte.

---

### **2. metadata.json Integration (renamer_core.py)**

**Datei**: `backend/renamer_core.py` (Zeilen 290-310)

**Neue Funktionalität**: Nach dem Umbenennen wird eine `metadata.json` im Buch-Ordner erstellt.

**Inhalt der metadata.json**:
```json
{
  "isbn": "9783742441393",
  "narrators": [
    "Jonah Rausch"
  ]
}
```

**Narrator-Formatierung**:
- **Datenbank-Format**: `"Nachname, Vorname; Nachname2, Vorname2"`
- **metadata.json-Format**: `["Vorname Nachname", "Vorname2 Nachname2"]`

**Code-Auszug**:
```python
# Write metadata.json for Audiobookshelf
import json
metadata_path = os.path.join(new_book_path, "metadata.json")
metadata = {"isbn": ean}

# Format narrator: "Nachname, Vorname" -> "Vorname Nachname"
if book.narrator:
    narrators = []
    for part in book.narrator.split(';'):
        part = part.strip()
        if ',' in part:
            last, first = part.split(',', 1)
            narrators.append(f"{first.strip()} {last.strip()}")
        else:
            narrators.append(part)
    metadata["narrators"] = narrators

try:
    with open(metadata_path, 'w', encoding='utf-8') as mf:
        json.dump(metadata, mf, ensure_ascii=False, indent=2)
except Exception as meta_err:
    logger.warning(f"Could not write metadata.json: {meta_err}")
```

**Zweck**: Audiobookshelf kann über die ISBN die Custom Metadata Provider API aufrufen und Metadaten abrufen.

---

### **3. API-Updates (main.py)**

**Datei**: `backend/main.py` (Zeilen 655-690)

**Funktion**: `check_book_on_disk()` wurde aktualisiert, um Bücher mit dem neuen Namensschema zu finden.

**Such-Reihenfolge**:
1. **Mit Status-Suffix**: `Author/Title_Hsp/`, `Author/Title (ungekuerzt)/`, etc.
2. **Fallback ohne Status**: `Author/Title/` (für alte Bücher)
3. **Raw EAN**: `9783742441393/` (noch nicht umbenannt)

**Code-Logik**:
```python
def check_book_on_disk(book):
    # Construct final_title with abridged_status (same logic as renamer_core.py)
    final_title = safe_title
    if book.abridged_status:
        # ... apply status suffix ...
    
    # Search with status
    target_dir = os.path.join(lib_path, safe_author, final_title)
    if os.path.isdir(target_dir):
        # Found! Look for cover...
    
    # Fallback: Search without status
    if book.abridged_status:
        fallback_dir = os.path.join(lib_path, safe_author, safe_title)
        if os.path.isdir(fallback_dir):
            # Found old naming...
```

**Ergebnis**: API kann sowohl neue als auch alte Ordnerstrukturen finden.

---

## 🔧 Deployment

### **Auf dem Server durchgeführt**:

```bash
# 1. Code-Dateien aktualisiert
cd ~/audiobook_renamer_web
cp backend/renamer_core.py backend/renamer_core.py.backup
cp backend/main.py backend/main.py.backup

# 2. Neue Dateien hochgeladen
scp renamer_core.py root@94.130.65.4:~/audiobook_renamer_web/backend/
scp main.py root@94.130.65.4:~/audiobook_renamer_web/backend/

# 3. Container neu gebaut
docker stop audiobook-renamer
docker rm audiobook-renamer
docker build -t audiobook-renamer-v2:latest .
docker run -d --name audiobook-renamer -p 8091:8000 \
  -v /:/host_mnt \
  -v /root/audiobook_renamer_web/data:/app/data \
  -e PUID=0 -e PGID=0 \
  --restart unless-stopped \
  audiobook-renamer-v2:latest
```

---

## 📊 Audiobookshelf Integration

### **Konfiguration**:

**Custom Metadata Provider URL**:
```
http://172.17.0.1:8091/api/abs
```

**Wichtig**: 
- **NICHT** `http://audiobook-renamer:8000/api/abs` (DNS-Auflösung funktioniert nicht)
- **NICHT** `http://94.130.65.4:8091/api/abs` (funktioniert nur extern)
- **Richtig**: `http://172.17.0.1:8091/api/abs` (Docker Bridge IP)

**Autorisierungsheader**: Leer lassen (keine Authentifizierung erforderlich)

---

### **API-Response-Beispiel**:

```json
{
  "matches": [
    {
      "title": "Wie Demokratien sterben: Und was wir dagegen tun können",
      "subtitle": "ungekuerzt",
      "author": "Ziblatt, Daniel; Levitsky, Steven",
      "isbn": "9783742441256",
      "description": "Demokratien sterben mit einem Knall oder mit einem Wimmern...",
      "publishedYear": "2026",
      "publishedDate": "15.05.2026",
      "publisher": "Der Audio Verlag",
      "narrator": "Christian Tramitz",
      "cover": "http://94.130.65.4:8091/files/DATA/Media/audiobooks/Ziblatt%2C%20Daniel%3B%20Levitsky%2C%20Steven/Wie%20Demokratien%20sterben%20Und%20was%20wir%20dagegen%20tun%20k%C3%B6nnen%20%28ungekuerzt%29/9783742441256.jpg",
      "tags": ["ungekuerzt"]
    }
  ]
}
```

**Übertragene Felder**:
- ✅ `title` - Titel
- ✅ `subtitle` - Abridged Status
- ✅ `author` - Autor (formatiert)
- ✅ `isbn` - EAN/ISBN
- ✅ `description` - Beschreibung (wenn in DB vorhanden)
- ✅ `publishedYear` / `publishedDate` - Erscheinungsdatum
- ✅ `publisher` - Verlag ("Der Audio Verlag")
- ✅ `narrator` - Sprecher (formatiert: "Vorname Nachname")
- ✅ `cover` - Cover-URL (falls vorhanden)
- ✅ `tags` - Tags mit Abridged Status

---

## 🧪 Testen

### **Test 1: API-Funktionalität**

```bash
# Status-Check
curl http://localhost:8091/api/abs/status
# Erwartete Antwort:
# {"status":"ok","service":"Audiobook Renamer Metadata Provider","count":2908}

# Such-Test
curl "http://localhost:8091/api/abs/search?q=9783742441256"
# Sollte JSON mit Metadaten zurückgeben
```

### **Test 2: Neues Buch umbenennen**

1. Lege ein ZIP-File (mit EAN-Name) in den Library-Ordner
2. Triggere "Run Scan" im Dashboard
3. Prüfe ob der Ordner korrekt benannt wurde:
   - Mit Hörspiel: `Autor/Titel_Hsp/`
   - Mit Ungekürzt: `Autor/Titel (ungekuerzt)/`
   - Mit Gekürzt: `Autor/Titel (gekuerzt)/`
4. Prüfe ob `metadata.json` existiert:
   ```bash
   cat "/DATA/Media/audiobooks/Autor/Titel/metadata.json"
   ```

### **Test 3: Audiobookshelf Match**

1. Öffne ein Buch in Audiobookshelf
2. Klicke "Match"
3. Wähle "DAV Datenbank" als Provider
4. Prüfe ob Metadaten korrekt übernommen werden

---

## ✅ Was funktioniert

### **Renamer**:
- ✅ Unterschiedliche Ordner für Hörspiel, Gekürzt, Ungekürzt
- ✅ `metadata.json` wird bei neuen Büchern erstellt
- ✅ ISBN und Narrator werden geschrieben
- ✅ Narrator-Format konvertiert: `"Nachname, Vorname"` → `"Vorname Nachname"`

### **API**:
- ✅ Liefert alle Metadaten aus der Datenbank
- ✅ Findet Bücher mit neuem und altem Namensschema
- ✅ Formatiert Narrator-Namen korrekt
- ✅ Gibt Cover-URLs zurück (wenn vorhanden)

### **Audiobookshelf**:
- ✅ Kann Custom Provider nutzen
- ✅ Ruft API erfolgreich auf
- ✅ Übernimmt Titel, Autor, ISBN, Sprecher, etc.
- ✅ Übernimmt Beschreibung (wenn in DB vorhanden)

---

## 🔄 Rollback

Falls Probleme auftreten:

```bash
cd ~/audiobook_renamer_web

# Container stoppen
docker stop audiobook-renamer
docker rm audiobook-renamer

# Alte Code-Dateien wiederherstellen
cp backend/renamer_core.py.backup backend/renamer_core.py
cp backend/main.py.backup backend/main.py

# Container neu bauen
docker build -t audiobook-renamer-v2:latest .
docker run -d --name audiobook-renamer -p 8091:8000 \
  -v /:/host_mnt \
  -v /root/audiobook_renamer_web/data:/app/data \
  -e PUID=0 -e PGID=0 \
  --restart unless-stopped \
  audiobook-renamer-v2:latest
```

---

## 📝 Wichtige Hinweise

### **Bestehende Bücher**:
- **Keine** automatische Umbenennung alter Bücher
- Alte Bücher behalten Namen ohne Status-Suffix
- API findet alte Bücher über Fallback-Suche
- Neue Bücher werden automatisch korrekt benannt

### **metadata.json**:
- Wird **nur** für **neue** Bücher erstellt
- Bestehende Bücher haben **keine** metadata.json
- Falls gewünscht: Script für nachträgliches Erstellen verfügbar

### **Beschreibungen**:
- Werden übertragen **wenn in DB vorhanden**
- Fehlende Beschreibungen = `null` in API
- Audiobookshelf zeigt dann keine Beschreibung an

---

## 🎉 Zusammenfassung

**Problem gelöst**:
- ✅ Namenskonflikte bei verschiedenen Versionen behoben
- ✅ Hörspiel, Gekürzt, Ungekürzt haben eigene Ordner
- ✅ Audiobookshelf kann Metadaten korrekt abrufen
- ✅ Narrator-Format automatisch konvertiert

**Alle Funktionen erhalten**:
- ✅ ZIP-Verarbeitung
- ✅ Audio-Optimierung (96kbps)
- ✅ Cover-Optimierung (max 600px)
- ✅ Takedown-Handling
- ✅ Web-Dashboard
- ✅ Live-Logs

**Neue Features**:
- ✅ Intelligente Ordnernamen mit Status
- ✅ metadata.json für Audiobookshelf
- ✅ Narrator-Formatierung
- ✅ Erweiterte API mit Tags

---

## 📞 Support

Bei Problemen:

1. **Logs prüfen**:
   ```bash
   docker logs audiobook-renamer --tail 50
   ```

2. **API testen**:
   ```bash
   curl http://localhost:8091/api/abs/status
   ```

3. **Datenbank prüfen**:
   ```bash
   sqlite3 /root/audiobook_renamer_web/data/metadata.db "SELECT * FROM books LIMIT 5;"
   ```

---

**Update erfolgreich abgeschlossen! 🚀**
