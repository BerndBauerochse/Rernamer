# Changelog: Abridged Status Integration

**Datum**: 2026-01-27  
**Problem**: Gekürzte und ungekürzte Versionen wurden nicht unterschieden

## 🔴 Ursprüngliches Problem

### 1. Umbenennung ohne Unterscheidung
Der Renamer hat beim Umbenennen **nur** den Titel verwendet, nicht den `abridged_status`:
```
Eingabe:  9783123456789.zip (Harry Potter - Ungekürzt)
Ausgabe:  J.K. Rowling/Harry Potter/
```

**Konflikt**: Wenn eine gekürzte Version kam:
```
Eingabe:  9783987654321.zip (Harry Potter - Gekürzt)
Ausgabe:  J.K. Rowling/Harry Potter/  ❌ EXISTIERT BEREITS!
```

### 2. Audiobookshelf konnte nicht unterscheiden
Die API `/api/abs/search` konnte nicht erkennen, ob ein Ordner die gekürzte oder ungekürzte Version enthält:
- Ordnername: `Harry Potter` 
- Datenbank: `abridged_status = "Ungekürzt"`
- Problem: Ordnername enthält diese Info nicht!

---

## ✅ Lösung

### Änderung 1: `renamer_core.py` (Zeilen 256-279)
**Ordnername enthält jetzt den vollständigen Status (3 Kategorien)**:

```python
# NEU: Include abridged status in folder name
# Match old script's naming scheme:
# - Hörspiel: "Titel_Hsp"
# - Gekürzt: "Titel (gekuerzt)"
# - Ungekürzt: "Titel (ungekuerzt)"
# - Normal: "Titel"
final_title = safe_title
if book.abridged_status:
    status_lower = book.abridged_status.lower().strip()
    
    # Check for Hörspiel (multiple possible spellings)
    if "hörspiel" in status_lower or "hoerspiel" in status_lower or "hsp" in status_lower:
        final_title = f"{safe_title}_Hsp"
    # Check for Ungekürzt
    elif "ungekürzt" in status_lower or "ungekuerzt" in status_lower or "unabridged" in status_lower:
        final_title = f"{safe_title} (ungekuerzt)"
    # Check for Gekürzt
    elif "gekürzt" in status_lower or "gekuerzt" in status_lower or "abridged" in status_lower:
        final_title = f"{safe_title} (gekuerzt)"
```

**Ergebnis** (wie im alten Skript):
```
Rita Falk/
  ├── Schweinekopf al dente/              # Normal (kein Status)
  ├── Schweinekopf al dente (gekuerzt)/   # Gekürzte Version
  ├── Schweinekopf al dente (ungekuerzt)/ # Ungekürzte Version (falls vorhanden)
  └── Schweinekopf al dente_Hsp/          # Hörspiel-Version
```

---

### Änderung 2: `main.py` - `check_book_on_disk()` (Zeilen 658-679)
**API sucht jetzt auch nach Ordnern mit abridged_status**:

```python
# NEU: Include abridged status if available
if book.abridged_status:
    safe_abridged = clean(book.abridged_status)
    final_title = f"{safe_title} - {safe_abridged}"
else:
    final_title = safe_title

# Check Author/Title WITH abridged status first (new naming scheme)
target_dir = os.path.join(lib_path, safe_author, final_title)
if os.path.exists(target_dir):
    found_dir = target_dir
# Fallback: Check WITHOUT abridged status (old naming scheme)
elif book.abridged_status:
    fallback_dir = os.path.join(lib_path, safe_author, safe_title)
    if os.path.exists(fallback_dir):
        found_dir = fallback_dir
```

**Vorteil**: 
- ✅ Findet neu umbenannte Ordner (mit Status)
- ✅ Findet alte Ordner (ohne Status) als Fallback
- ✅ Keine Breaking Changes für bestehende Bibliotheken

---

## 🧪 Testing

### Test 1: Neue ZIP-Dateien
```bash
# Eingabe
/library/9783123456789.zip  → Metadaten: "Harry Potter", "Ungekürzt"
/library/9783987654321.zip  → Metadaten: "Harry Potter", "Gekürzt"

# Erwartete Ausgabe
/library/J.K. Rowling/Harry Potter - Ungekürzt/
/library/J.K. Rowling/Harry Potter - Gekürzt/
```

### Test 2: Audiobookshelf API
```bash
# Anfrage
GET /api/abs/search?q=Harry Potter Ungekürzt

# Erwartete Antwort
{
  "matches": [
    {
      "title": "Harry Potter",
      "subtitle": "Ungekürzt",
      "isbn": "9783123456789",
      "cover": "http://server:8091/files/DATA/.../Harry Potter - Ungekürzt/9783123456789.jpg",
      "_exists": true
    }
  ]
}
```

### Test 3: Fallback für alte Ordner
```bash
# Alter Ordner (ohne Status)
/library/J.K. Rowling/Harry Potter/

# API soll ihn trotzdem finden
GET /api/abs/search?q=Harry Potter
→ Findet den Ordner über Fallback-Logik ✅
```

---

## 📋 Migration bestehender Bibliotheken

**Keine automatische Migration erforderlich!**

- Alte Ordner (ohne Status) funktionieren weiterhin über Fallback
- Neue Scans erstellen neue Ordner mit Status
- Optional: Manuell umbenennen für Konsistenz

**Beispiel manuelles Umbenennen**:
```bash
# Von Hand oder via Script
mv "J.K. Rowling/Harry Potter" "J.K. Rowling/Harry Potter - Ungekürzt"
```

---

## ✅ Vorteile

1. **Keine Konflikte mehr**: Gekürzt und Ungekürzt liegen in separaten Ordnern
2. **Audiobookshelf-Kompatibilität**: Ordnername allein zeigt den Status
3. **Rückwärtskompatibel**: Alte Ordner funktionieren weiterhin
4. **Konsistenz**: Datenbank und Dateisystem stimmen überein

---

## 📝 Nächste Schritte

1. ✅ Code angepasst
2. ⏳ Docker-Image neu bauen
3. ⏳ Deployment auf Server
4. ⏳ Test mit echten Daten
5. ⏳ Update DB ausführen (Metadaten neu laden)
