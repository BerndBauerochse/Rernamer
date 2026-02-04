# Audiobook Renamer Web – Projektdokumentation

## Übersicht

Der **Audiobook Renamer Web** ist eine Docker-basierte Anwendung zur automatischen Organisation, Optimierung und Bereinigung von Hörbuch-Bibliotheken. Er überwacht ein Verzeichnis, entpackt ZIP-Dateien, identifiziert Hörbücher anhand ihrer EAN (ISBN), benennt sie nach dem Schema `Autor/Titel` um und optimiert Audio- sowie Bilddateien.

Die Steuerung erfolgt über ein modernes Web-Interface.

## Features

### 1. Automatisierung & Sortierung

- **ZIP-Handling**: Automatisches Entpacken von `.zip`-Dateien.
- **Flattening**: Erkennt und korrigiert unnötige Unterordner-Strukturen (z. B. `Titel/EAN/Audio.mp3` -> `Titel/Audio.mp3`).
- **Identifizierung**: Scannt Ordner nach 13-stelligen EAN-Nummern und gleicht sie mit einer lokalen Datenbank ab.
- **Strukturierung**: Verschiebt erkannte Hörbücher automatisch in `Autor/Titel`-Ordner.

### 2. Qualitäts-Optimierung

- **Audio**: Konvertiert MP3-Dateien automatisch auf **96 kbit/s** (CBR), falls die Bitrate abweicht. Das sorgt für einheitliche Qualität und spart Speicherplatz.
- **Cover**: Skaliert Cover-Bilder (`.jpg`, `.jpeg`) automatisch auf maximal **600px** Breite herunter.

### 3. Datenbank & Updates

- **Datenquelle**: Nutzt einen **n8n Webhook** (JSON) statt einer fehleranfälligen Excel-Datei.
- **Manuelles Update**: Über den Button **"Update DB"** im Web-Interface.
- **Automatisches Update**: Ein integrierter Scheduler führt jeden **Sonntag um 03:00 Uhr** automatisch ein Datenbank-Update durch.
- **Takedown-Schutz**: Erkennt Bücher, die rechtlich gesperrt ("Takedown") sind.

### 4. Scheduler (Zeitplan)

- **Auto-Update**: Wöchentliche Aktualisierung der Metadaten (siehe oben).

## Technische Architektur

### Backend (Python/FastAPI)

- Läuft im Docker-Container.
- Nutzt `ffmpeg` für Medienbearbeitung.
- Greift über einen speziellen "Root-Mount" (`/host_mnt`) auf das Dateisystem des Servers zu, wodurch in der UI beliebige Server-Pfade eingegeben werden können.
- Datenbank: SQLite (`metadata.db`).

### Frontend (React/Vite)

- Modernes "Glassmorphism"-Design.
- Kommuniziert via **WebSockets** mit dem Backend, um Live-Logs im Terminal-Fenster anzuzeigen.
- Ermöglicht Konfiguration des Bibliothek-Pfads und Steuerung des Dienstes.

## Installation & Deployment

### Voraussetzungen

- Linux-Server (z.B. Ubuntu, Debian, CasaOS)
- Docker & Docker Compose

### Schritt-für-Schritt Installation

1.  **Paket hochladen** (von Windows aus):

    ```powershell
    scp "audiobook_renamer_deploy.zip" root@DEINE-SERVER-IP:~/
    ```

2.  **Auf dem Server installieren**:

    ```bash
    # Alten Ordner entfernen (falls vorhanden)
    rm -rf audiobook_renamer_web

    # Entpacken
    unzip audiobook_renamer_deploy.zip
    cd audiobook_renamer_web

    # Starten
    docker compose up -d --build
    ```

3.  **Interface aufrufen**:
    - Adresse: `http://DEINE-SERVER-IP:8091`

### Einrichtung im Web-Interface

1.  Gehe auf den Reiter **Settings**.
2.  Trage deinen **echten Server-Pfad** zu den Hörbüchern ein (z. B. `/DATA/Media/audiobooks`).
    - _Hinweis:_ Der Renamer übersetzt diesen Pfad intern automatisch, du musst keine Docker-Volumes mehr anpassen.
3.  Klicke auf **Save**.
4.  Gehe zum **Dashboard** und klicke optional auf **"Update DB"** (beim ersten Mal empfohlen).
5.  Klicke auf **"Run Scan"**.

## Wichtige Pfade im Container

- `/app/data`: Hier liegt die `metadata.db`. Dieser Ordner ist als Volume gemountet (`./data` auf dem Server), damit die Datenbank bei Updates erhalten bleibt.
- `/host_mnt`: Hier ist das Root-Verzeichnis des Servers eingehängt (Read/Write).

## Fehlerbehebung

- **Log-Ausgabe**: Fehler werden rot im Web-Terminal angezeigt.
- **Keine Verbindung**: Prüfe mit `docker ps`, ob der Container `audiobook-renamer` läuft.
- **Rechte-Probleme**: Der Container läuft standardmäßig mit `PUID=0` (Root), um auf alle Festplatten zugreifen zu können.

## Changelog / Erreichte Meilensteine (Januar 2026)

### 1. Robuster Excel/Datenbank-Import

- **Problem**: Der Download von `dav-titel.info` lieferte oft korrupte Header (`Workbook corruption`) oder falsche Encodings (`utf-8` Error), da es sich teilweise um HTML-Tabellen oder alte XLS-Dateien handelte.
- **Lösung**: Implementierung einer **Magic-Byte-Erkennung**. Das Backend prüft nun die ersten 8 Bytes der Datei und entscheidet intelligent, ob es sich um `XLS`, `XLSX` oder `CSV/Text` handelt. Defekte XLS-Header werden automatisch repariert (`ignore_workbook_corruption=True`).

### 2. Inventory UI Redesign (Compact Fixed Layout)

- **Problem**: Die Tabelle "Inventory" war instabil; Spaltenbreiten sprangen beim Sortieren, und Inhalte wurden rechts aus dem Bildschirm gedrückt.
- **Lösung**: Umstellung auf `table-fixed` (Fixed Layout).
  - **Fest definierte Breiten** für Metadaten: Cover (64px), EAN (128px), Datum (96px), Status (96px).
  - **Prozentuale Aufteilung** für Text: Autor (ca. 16%) und Titel (Rest ca. 33%).
  - **Truncation**: Lange Texte werden sauber mit `...` gekürzt, voller Text erscheint als Tooltip beim Maus-Hover.
  - **Padding reduziert**: `px-3` statt `px-6` für eine kompaktere Darstellung, damit alle Spalten auch auf kleineren Screens sichtbar bleiben.

### 3. Usability & Defaults

- **Default Path**: Der Standard-Bibliothekspfad wurde auf `/host_mnt/DATA/Media/audiobooks` gesetzt (passend für CasaOS), damit er nach einem Reset nicht neu eingetippt werden muss.
- **Auto-Create DB**: Die Datenbanktabellen werden nun beim Start automatisch initialisiert, falls sie fehlen.

### 4. Deployment & Caching (V2)

- **Problem**: Aggressives Caching von Docker und Browsern verhinderte, dass UI-Updates sichtbar wurden.
- **Lösung**:
  - Wechsel des Ports von **8090** auf **8091**.
  - Umbenennung des Docker-Images auf `audiobook-renamer-v2`.
  - Diese Änderungen erzwingen einen sauberen Neustart und umgehen alle Caches.

### 5. Audiobookshelf Integration (Neu in V18)

- **Feature**: Der Renamer kann nun als "Custom Metadata Provider" in Audiobookshelf genutzt werden.
- **Vorteil**: Nutzt die gleichen Metadaten wie der Renamer (DAV-Titel), unterscheidet korrekt zwischen gekürzt/ungekürzt und formatiert Sprecher automatisch.
- **Einrichtung in ABS**:
  - URL: `http://DEINE-SERVER-IP:8091/api/abs`
  - Der Provider sucht tolerant nach Titel/Autor und priorisiert Dateien, die bereits lokal "renamed" wurden.

## Wichtiger Hinweis zur Datenbank

Da wir beim Deployment den kompletten Ordner löschen (`rm -rf`), wird auch die Datenbank `metadata.db` gelöscht.
**Nach jedem Update muss daher einmalig auf "Update DB" im Dashboard geklickt werden!**

### 6. n8n Integration & Refactoring (Ende Jan 2026)

- **Wechsel auf n8n**: Die Datenbank-Updates erfolgen nun über einen n8n-Webhook. Dies entfernt die Abhängigkeit von instabilen Excel-Downloads und schweren Bibliotheken (`pandas`, `openpyxl`, `xlrd`).
- **Code-Bereinigung**: Entfernung von `httpx` (verursachte Abstürze) und `pandas` zur Reduzierung der Image-Größe und Erhöhung der Stabilität.
- **Datums-Fix**: Korrekte Zuweisung des Veröffentlichungsdatums durch Mapping auf `VÖ_digital` aus n8n.
- **Scheduler**: Implementierung eines automatischen wöchentlichen Updates (Sonntags 03:00 Uhr).
- **UI-Anpassungen (Partial)**: Versuch, Bestätigungs-Popups zu entfernen.
  - _Known Issue_: Bei einigen Nutzern erscheinen trotz Code-Änderung weiterhin Popups (vermutlich Caching-Problem im Browser oder Build-Prozess). Workaround: Browser-Cache leeren (Strg+F5).
