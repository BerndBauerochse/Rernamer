# Audiobook Renamer Web

A premium web-based interface for your Audiobook Renamer tool.

## Features
- **Web Dashboard**: Control the renamer from any browser.
- **Live Logs**: See real-time progress of what the renamer is doing.
- **Settings**: Configure your library path directly from the UI.
- **Dockerized**: Easy to deploy on any server (CasaOS, Synology, etc.).

## Migration / Setup Guide

### 1. Preparation
Copy this entire folder `audiobook_renamer_web` to your new server.

### 2. Data Migration
You need to bring your existing database and library.
1. Create a `data` folder inside this directory:
   ```bash
   mkdir data
   ```
2. Copy your existing `metadata.db` file (from your old setup) into this `data` folder.

### 3. Docker Configuration
Open `docker-compose.yml` and adjust the volumes to match your server's file system:

```yaml
volumes:
  - /path/to/your/actual/audiobooks:/app/library  <-- CHANGE THIS
  - ./data:/app/data                              <-- This stores the DB
```

### 4. Run
Run the application using Docker Compose:

```bash
docker-compose up -d --build
```

Access the interface at: `http://<your-server-ip>:8090`

## Usage
1. Go to **Settings** in the web UI.
2. Verify the Library Path matches what is mounted inside the container (default `/app/library`).
3. Click **Run Scan** on the Dashboard.
