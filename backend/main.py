from fastapi import FastAPI, WebSocket, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import threading
import time
import os
import json
import asyncio
from database import SessionLocal, engine, Base
from models import Book
from sqlalchemy import func, or_
from datetime import datetime

# Create Tables
Base.metadata.create_all(bind=engine)

from renamer_core import run_once as run_renamer, logger, stop_event

# -----------------
# 1. DATABASE UPDATE LOGIC (Updated for n8n Webhook)
# -----------------
def update_database_from_url():
    # Production URL provided by User configuration
    url = config.get("n8n_webhook_url", "")
    
    if not url:
        logger.warning("No n8n Webhook URL configured. Skipping DB update.")
        return

    logger.info(f"Downloading metadata from n8n Webhook...")
    
    try:
        import requests
        # Timeout 60s for large JSON payload, ignore SSL errors (internal/proxy issues)
        response = requests.get(url, timeout=60, verify=False)
        response.raise_for_status()
        
        data = response.json()
        
        # Handle Array vs Single Object vs Wrapper
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # Check if wrapped in "data" or "results" or just single object
            if "data" in data and isinstance(data["data"], list):
                items = data["data"]
            else:
                items = [data]
        else:
             logger.error(f"Unexpected JSON format: {type(data)}")
             return

        logger.info(f"Received {len(items)} items from n8n.")

        # Database Update
        db = SessionLocal()
        count_updated = 0
        count_inserted = 0
        
        try:
            for item in items:
                # 1. READ FIELDS (Safe get)
                raw_ean = item.get("EAN")
                if not raw_ean: 
                    # Try alternate mapping just in case
                    raw_ean = item.get("EAN_digital")
                
                if not raw_ean: continue
                
                ean_str = str(raw_ean).strip()
                if ean_str.endswith('.0'): ean_str = ean_str[:-2] # Fix Excel number formatting if present
                if not ean_str: continue

                # Map other fields from JSON
                author_str = str(item.get("Autor") or "Unknown").strip()
                title_str = str(item.get("Titel") or "Unknown").strip()
                narrator_str = str(item.get("Sprecher") or "").strip() or None
                
                # FIX: Check VÖ/VÖ_digital AND Release Date 
                release_str = None
                for key in ["VÖ_digital", "VOE_digital", "Release Date", "ET"]:
                    if item.get(key):
                        release_str = str(item.get(key)).strip()
                        break
                        
                abridged_str = str(item.get("Abridged") or "").strip() or None
                if not abridged_str:
                     # Fallback for German field name from n8n
                     abridged_str = str(item.get("Gekuerzt_Ungekuerzt") or "").strip() or None
                desc_str = str(item.get("Beschreibung") or "").strip() or None
                
                # Takedown logic
                takedown_val = item.get("Takedown")
                is_takedown = False
                if takedown_val:
                    t_str = str(takedown_val).lower().strip()
                    if t_str in ["ja", "yes", "true", "1"]:
                         is_takedown = True

                # 2. UPDATE OR INSERT
                existing = db.query(Book).filter(Book.ean == ean_str).first()
                if existing:
                    existing.author = author_str
                    existing.title = title_str
                    existing.takedown = is_takedown
                    existing.release_date = release_str
                    existing.abridged_status = abridged_str
                    existing.narrator = narrator_str
                    existing.description = desc_str
                    count_updated += 1
                else:
                    new_book = Book(
                        ean=ean_str, 
                        author=author_str, 
                        title=title_str, 
                        takedown=is_takedown,
                        release_date=release_str,
                        abridged_status=abridged_str,
                        narrator=narrator_str,
                        description=desc_str
                    )
                    db.add(new_book)
                    count_inserted += 1
            
            db.commit()
            logger.info(f"DB Update success. Updated: {count_updated}, New: {count_inserted}")
            
        finally:
            db.close()
                
    except Exception as e:
        logger.error(f"DB Update Failed: {e}")

# -----------------
# 2. MAIN APP SETUP
# -----------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config
# Config
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# 1. Defaults
final_config = {
    "library_path": "/data/audiobooks",
    "n8n_webhook_url": ""
}

# 2. Override with Config File (Prioritized for local use)
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, 'r') as f:
            file_config = json.load(f)
            final_config.update(file_config)
            logger.info("Loaded config from file.")
    except json.JSONDecodeError:
        logger.error("Config file corrupted. Using defaults/env.")

# 3. Override with Environment Variables (Prioritized for Docker/Coolify)
# This allows usage without config.json
env_lib = os.getenv("LIBRARY_PATH")
if env_lib: 
    final_config["library_path"] = env_lib

env_webhook = os.getenv("N8N_WEBHOOK_URL")
if env_webhook: 
    final_config["n8n_webhook_url"] = env_webhook

# Apply
config = final_config

# State
is_running = False

class ConfigModel(BaseModel):
    library_path: str
    n8n_webhook_url: Optional[str] = None

@app.get("/api/config")
def get_config():
    return config

@app.post("/api/config")
def set_config(new_conf: ConfigModel):
    global config
    logger.info(f"Saving new config: {new_conf.dict()}")
    config = new_conf.dict()
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
        logger.info("Config saved successfully.")
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return {"status": "error", "message": str(e)}
    return config

@app.get("/api/status")
def get_status():
    return {"running": is_running}

# MANUAL TRIGGER FOR DATABASE UPDATE
@app.post("/api/update_db")
def trigger_update_db():
    def worker():
        logger.info("Starting manual DB update...")
        try:
            update_database_from_url()
        except Exception as e:
            logger.error(f"Manual DB update failed: {e}")

    threading.Thread(target=worker, daemon=True).start()
    return {"status": "DB Update Started"}


@app.post("/api/start")
def start_renamer():
    global is_running
    if is_running:
        return {"status": "Already running"}
    
    stop_event.clear()
    is_running = True
    
    # Handle Docker Host Mount Translation
    user_path = config["library_path"]
    if os.path.exists("/host_mnt") and not user_path.startswith("/host_mnt"):
        clean_path = user_path.lstrip("/")
        internal_path = os.path.join("/host_mnt", clean_path)
        logger.info(f"Using host path mapping: {user_path} -> {internal_path}")
    else:
        internal_path = user_path

    if not os.path.exists(internal_path):
         logger.error(f"Path not found: {internal_path} (Check if path exists on Server)")
         return {"status": "Error: Path not found"}

    def worker():
        global is_running
        logger.info("Renamer Core: Starting processing cycle...")
        
        # 1. NO AUTO UPDATE - Database is manual now
        # logger.info("Step 1: Updating Database from External Source...")
        # update_database_from_url()
        
        # 2. RUN RENAME
        logger.info("Scanning Folder Structure...")
        try:
            run_renamer(internal_path)
        except Exception as e:
            logger.error(f"Renamer Service crashed: {e}")
        finally:
            is_running = False
            logger.info("Renamer Service Cycle Completed.")

    threading.Thread(target=worker, daemon=True).start()
    return {"status": "Started"}

# Scheduler State
scheduler_active = False
scheduler_thread = None

def scheduler_loop():
    global scheduler_active, is_running
    logger.info("Auto-Scan Scheduler Started (runs every 60 min).")
    while scheduler_active:
        if not is_running:
             logger.info("Scheduler: Triggering scheduled cycle...")
             
             # Handle Docker Host Mount Translation
             user_path = config["library_path"]
             if os.path.exists("/host_mnt") and not user_path.startswith("/host_mnt"):
                clean_path = user_path.lstrip("/")
                internal_path = os.path.join("/host_mnt", clean_path)
             else:
                internal_path = user_path

             # Start scan in separate thread to not block scheduler
             stop_event.clear()
             is_running = True
             
             def scheduled_worker():
                 global is_running
                 try:
                    # SCHEDULER: ONLY RENAME, NO DB UPDATE
                    run_renamer(internal_path)
                 except Exception as e:
                    logger.error(f"Scheduled scan failed: {e}")
                 finally:
                    is_running = False
                    logger.info("Scheduler: Cycle finished. Waiting 60 min.")
             
             threading.Thread(target=scheduled_worker, daemon=True).start()
        
        # Sleep in chunks to allow faster stopping
        for _ in range(60): 
            if not scheduler_active: break
            time.sleep(60) # 60 * 60s = 1 hour

@app.post("/api/scheduler")
def toggle_scheduler(enable: bool):
    global scheduler_active, scheduler_thread
    scheduler_active = enable
    
    if enable:
        if scheduler_thread is None or not scheduler_thread.is_alive():
            scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
            scheduler_thread.start()
        return {"status": "Scheduler Enabled"}
    else:
        # Loop will exit on next check
        return {"status": "Scheduler Disabled"}

@app.get("/api/scheduler")
def get_scheduler_status():
    return {"active": scheduler_active}

@app.post("/api/stop")
def stop_renamer():
    stop_event.set()
    logger.info("Stopping request received...")
    return {"status": "Stopping..."}

@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Send recent history first
    for entry in logger.history[-50:]:
        await websocket.send_json(entry)
    
    # Hook for new logs
    queue = asyncio.Queue()
    
    loop = asyncio.get_running_loop()
    
    def listener(entry):
        try:
            asyncio.run_coroutine_threadsafe(queue.put(entry), loop)
        except Exception:
            pass
            
    logger.add_listener(listener)
    
    try:
        while True:
            entry = await queue.get()
            await websocket.send_json(entry)
    except Exception:
        pass
    finally:
        pass

# -----------------
# 3. INVENTORY & STATIC FILE SERVING
# -----------------
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from urllib.parse import quote
import io
import re

# Mount the entire host FS (read-only effectively via web) to serve covers
# We mount /host_mnt to /files
if os.path.exists("/host_mnt"):
    app.mount("/files", StaticFiles(directory="/host_mnt"), name="files")

# -----------------
# 4. AUDIOBOOKSHELF CUSTOM PROVIDER API
# -----------------

@app.get("/api/abs/status")
def abs_status():
    return {"status": "ok", "service": "Audiobook Renamer Metadata Provider", "count": SessionLocal().query(Book).count()}

@app.get("/api/abs/search")
def abs_search(q: str = None, title: str = None, author: str = None, isbn: str = None, mediaType: str = None, request: Request = None):
    # Log the incoming request
    clean_q = q or ""
    logger.info(f"ABS Search Request -> q='{clean_q}', title='{title}', author='{author}', isbn='{isbn}'")
    
    db = SessionLocal()
    try:
        # 1. Determine Search Strategy
        # If query is 13 digits, prioritize EAN search
        is_ean = False
        if isbn:
            q_str = isbn.replace("-", "").strip()
            is_ean = True
        elif clean_q and re.match(r'^\d{13}$', clean_q.strip()):
            q_str = clean_q.strip()
            is_ean = True
        else:
            q_str = clean_q.strip()
            
        search_filter = []
        
        # 2. Build Filters
        if is_ean:
             logger.info(f"Strategy: EAN Exact Match ({q_str})")
             matches = db.query(Book).filter(Book.takedown == False, Book.ean == q_str).all()
        else:
             # Token-based Search with "Abridged/Unabridged" Logic
             # This comes from the old "audiobook shelf" project main.py
             
             # Use title if q is empty (ABS sometimes sends only title)
             search_text = q_str if q_str else (title or "")
             
             clean_text = re.sub(r'[^\w\s]', ' ', search_text)
             raw_tokens = clean_text.split()
             
             title_tokens = []
             status_filters = []
             
             # Keywords to identify Status
             kw_unabridged = ["ungekürzt", "ungekuerzt", "unabridged"]
             kw_abridged = ["gekürzt", "gekuerzt", "abridged"]
             
             found_unabridged = False
             found_abridged = False
             
             for token in raw_tokens:
                t_lower = token.lower()
                if t_lower in kw_unabridged:
                    found_unabridged = True
                    continue # Do NOT search for this in Title
                if t_lower in kw_abridged:
                    found_abridged = True
                    continue # Do NOT search for this in Title
                title_tokens.append(token)
             
             # Apply Status Filters
             if found_unabridged:
                 logger.info("Detected 'Unabridged' keyword. Filtering...")
                 status_filters.append(
                    or_(
                        func.lower(Book.abridged_status).contains("ungekuerzt"),
                        func.lower(Book.abridged_status).contains("ungekürzt"),
                        func.lower(Book.abridged_status).contains("unabridged")
                    )
                )
             elif found_abridged:
                 logger.info("Detected 'Abridged' keyword. Filtering...")
                 status_filters.append(
                    or_(
                        func.lower(Book.abridged_status).contains("gekuerzt"),
                        func.lower(Book.abridged_status).contains("gekürzt"),
                        func.lower(Book.abridged_status).contains("abridged")
                    )
                )

             title_filters = []
             for token in title_tokens:
                if len(token) > 1: 
                    title_filters.append(func.lower(Book.title).contains(token.lower()))
            
             matches = []
             
             # ATTEMPT 1: Search with Author (if provided)
             if author:
                 clean_a = re.sub(r'[^\w\s]', ' ', author)
                 author_tokens = clean_a.split()
                 author_filters = []
                 for token in author_tokens:
                     if len(token) > 1:
                        author_filters.append(func.lower(Book.author).contains(token.lower()))
                 
                 if author_filters:
                     matches = db.query(Book).filter(
                         Book.takedown == False, 
                         *title_filters, 
                         *author_filters,
                         *status_filters
                     ).all()
            
             # ATTEMPT 2 (Fallback): If no matches, search ONLY by Title tokens
             if not matches and title_filters:
                matches = db.query(Book).filter(
                    Book.takedown == False, 
                    *title_filters,
                    *status_filters
                ).all()

        logger.info(f"ABS Search Found {len(matches)} matches.")

        # 3. Format Response
        response_data = []
        base_url = str(request.base_url).rstrip('/') if request else ""
        
        for b in matches:
            # Check existence (for sorting and covers)
            exists, web_cover_path = check_book_on_disk(b)
            
            # Format Narrator (Flip "Last, First" -> "First Last")
            narrator_val = b.narrator
            if narrator_val:
                raw_narrators = narrator_val.split(';')
                processed_narrators = []
                for n in raw_narrators:
                    n = n.strip()
                    if "," in n:
                        parts = n.split(",", 1)
                        if len(parts) == 2:
                            processed_narrators.append(f"{parts[1].strip()} {parts[0].strip()}")
                        else:
                            processed_narrators.append(n)
                    else:
                         processed_narrators.append(n)
                narrator_val = ", ".join(processed_narrators)
            
            # Cover URL calculation
            cover_url = None
            if web_cover_path:
                # web_cover_path comes from check_book_on_disk as /files/path...
                # We need to prepend base_url to be polite, or ABS might handle relative.
                # Ideally ABS can handle key 'cover' as URL.
                cover_url = f"{base_url}{web_cover_path}"

            try:
                # Extract year
                year_str = None
                if b.release_date:
                    m = re.search(r'\d{4}', str(b.release_date))
                    if m: year_str = m.group(0)
            except:
                year_str = None

            meta = {
                "title": b.title,
                "subtitle": b.abridged_status, # Important for UI!
                "author": b.author,
                "isbn": b.ean,
                "description": b.description,
                "publishedYear": year_str,
                "publishedDate": b.release_date,
                "publisher": "Der Audio Verlag",
                "narrator": narrator_val,
                "cover": cover_url,
                "tags": [],
                "_exists": exists
            }
            
            if b.abridged_status:
                meta["tags"].append(b.abridged_status)
                
            response_data.append(meta)
            
        # SORT: Exists first!
        response_data.sort(key=lambda x: x["_exists"], reverse=True)
        
        # Cleanup internal key
        for m in response_data:
            del m["_exists"]

        # 4. Return correct wrapper
        # The old code returned {"matches": [...]}. 
        return {"matches": response_data}
        
    except Exception as e:
        logger.error(f"ABS Search Error: {e}")
        return {"matches": []}
    finally:
        db.close()
        



def get_internal_library_path():
    """Resolves the user configured path to the internal container path"""
    user_path = config["library_path"]
    if os.path.exists("/host_mnt") and not user_path.startswith("/host_mnt"):
        clean_path = user_path.lstrip("/")
        return os.path.join("/host_mnt", clean_path)
    return user_path

def check_book_on_disk(book):
    """
    Returns (exists: bool, web_cover_path: str|None)
    web_cover_path is a URL path component starting with /files/...
    """
    lib_path = get_internal_library_path()
    
    # 1. Sanitize (Need to duplicate sanitize function here or import)
    def clean(n): return re.sub(r'[<>:"/\\|?*]', '', str(n)).strip() if n else "Unknown"
    
    safe_author = clean(book.author)
    safe_title = clean(book.title)
    
    # Calculate final_title using same logic as renamer_core.py
    final_title = safe_title
    if book.abridged_status:
        status_lower = book.abridged_status.lower().strip()
        
        # Check for Hörspiel
        if "hörspiel" in status_lower or "hoerspiel" in status_lower or "hsp" in status_lower:
            final_title = f"{safe_title}_Hsp"
        # Check for Ungekürzt
        elif "ungekürzt" in status_lower or "ungekuerzt" in status_lower or "unabridged" in status_lower:
            final_title = f"{safe_title} (ungekuerzt)"
        # Check for Gekürzt
        elif "gekürzt" in status_lower or "gekuerzt" in status_lower or "abridged" in status_lower:
            final_title = f"{safe_title} (gekuerzt)"
        else:
            # Unknown status
            safe_abridged = clean(book.abridged_status)
            final_title = f"{safe_title} ({safe_abridged})"
    
    found_dir = None
    
    # Check Author/Title WITH status suffix (new naming scheme)
    target_dir = os.path.join(lib_path, safe_author, final_title)
    if os.path.exists(target_dir):
        found_dir = target_dir
    # Fallback: Check Author/Title WITHOUT status (old naming scheme without differentiation)
    elif book.abridged_status:
        fallback_dir = os.path.join(lib_path, safe_author, safe_title)
        if os.path.exists(fallback_dir):
            found_dir = fallback_dir
    # Check EAN folder (not yet processed)
    if not found_dir:
        ean_dir = os.path.join(lib_path, book.ean)
        if os.path.exists(ean_dir):
            found_dir = ean_dir
            
    if found_dir:
        # Look for cover
        cover_file = None
        # Try EAN.jpg
        if os.path.exists(os.path.join(found_dir, f"{book.ean}.jpg")):
            cover_file = f"{book.ean}.jpg"
        else:
            # Any jpg
            for f in os.listdir(found_dir):
                if f.lower().endswith(('.jpg', '.jpeg')):
                    cover_file = f
                    break
        
        web_path = None
        if cover_file:
            # Construct path relative to /host_mnt
            # found_dir is e.g. /host_mnt/DATA/Media/books/Author/Title
            # We need to strip /host_mnt to get /DATA/Media/books/Author/Title/cover.jpg
            # Then prepend /files
            
            # Using simple string replace if starts with /host_mnt
            full_path = os.path.join(found_dir, cover_file)
            if full_path.startswith("/host_mnt"):
                rel_host = full_path.replace("/host_mnt", "", 1)
                # Ensure it starts with / for URL construction
                if not rel_host.startswith("/"): rel_host = "/" + rel_host
                web_path = f"/files{rel_host}"
        
        return True, web_path
            
    return False, None

@app.get("/inventory", response_class=HTMLResponse)
async def inventory_ui():
    """Simple Inventory UI matching the old style"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Audiobook Inventory</title>
        <style>
            body { font-family: sans-serif; margin: 20px; background: #f0f2f5; color: #333; }
            h1 { color: #1a1a1a; }
            .toolbar { margin-bottom: 20px; }
            button { padding: 10px 20px; background: #4f46e5; color: white; border: none; cursor: pointer; border-radius: 6px; font-weight: 500; }
            button:hover { background: #4338ca; }
            table { width: 100%; border-collapse: collapse; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden; }
            th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
            th { background-color: #f8f9fa; font-weight: 600; text-transform: uppercase; font-size: 0.85rem; color: #666; }
            img.cover { height: 60px; width: 60px; object-fit: cover; border-radius: 4px; background: #eee; }
            .status-ok { color: #059669; font-weight: bold; background: #d1fae5; padding: 4px 8px; border-radius: 4px; font-size: 0.85rem; }
            .status-missing { color: #dc2626; font-weight: bold; background: #fee2e2; padding: 4px 8px; border-radius: 4px; font-size: 0.85rem; }
            tr:hover { background-color: #f8fafc; }
            a { text-decoration: none; color: inherit; }
            .back-link { display: inline-block; margin-bottom: 20px; color: #666; }
            .back-link:hover { color: #333; }
        </style>
    </head>
    <body>
        <a href="/" class="back-link">← Back to Dashboard</a>
        <h1>📚 Audiobook Library Inventory</h1>
        <div class="toolbar">
            <button onclick="window.location.href='/api/export_inventory'">📥 Export Excel (Missing & Found)</button>
        </div>
        <table>
            <thead>
                <tr>
                    <th width="80">Cover</th>
                    <th>EAN</th>
                    <th>Author</th>
                    <th>Title</th>
                    <th>Rel. Date</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody id="table-body">
                <tr><td colspan="6" style="text-align:center; padding: 40px;">Loading library data...</td></tr>
            </tbody>
        </table>

        <script>
            fetch('/api/inventory')
                .then(response => response.json())
                .then(data => {
                    const tbody = document.getElementById('table-body');
                    tbody.innerHTML = '';
                    
                    data.forEach(book => {
                        const tr = document.createElement('tr');
                        
                        let imgHtml = '<div style="width:60px;height:60px;background:#eee;border-radius:4px;"></div>';
                        if (book.has_cover && book.relative_cover_path) {
                            // Ensure URL encoding for weird chars in filenames
                            // We only escape the segments, but the path is already absolute starting with /files
                            // For simplicity, just encode spaces? No, full encodeURI might break slashes.
                            // The backend returns a ready-to-use path like /files/DATA/...
                            // Browsers handle most chars automatically in src
                            imgHtml = `<img src="${book.relative_cover_path}" class="cover" loading="lazy">`;
                        }

                        tr.innerHTML = `
                            <td>${imgHtml}</td>
                            <td style="font-family:monospace; color:#666;">${book.ean}</td>
                            <td>${book.author || '-'}</td>
                            <td>${book.title || '-'}</td>
                            <td>${book.release_date || '-'}</td>
                            <td>
                                <span class="${book.exists ? 'status-ok' : 'status-missing'}">
                                    ${book.exists ? 'IN LIBRARY' : 'MISSING'}
                                </span>
                            </td>
                        `;
                        tbody.appendChild(tr);
                    });
                })
                .catch(err => {
                    document.getElementById('table-body').innerHTML = '<tr><td colspan="6" style="color:red; text-align:center;">Error loading data. Check Logs.</td></tr>';
                    console.error(err);
                });
        </script>
    </body>
    </html>
    """

@app.get("/api/inventory")
def get_inventory_api():
    db = SessionLocal()
    try:
        # Filter: Exclude Takedowns
        books = db.query(Book).filter(Book.takedown == False).all()
        results = []
        
        for book in books:
            exists, cover_path = check_book_on_disk(book)
            results.append({
                "ean": book.ean,
                "author": book.author,
                "title": book.title,
                "release_date": book.release_date,
                "exists": exists,
                "has_cover": cover_path is not None,
                "relative_cover_path": cover_path
            })
        
        # Sort by Author
        results.sort(key=lambda x: (x['author'] or "").lower())
        return results
    finally:
        db.close()

@app.get("/api/export_inventory")
def export_inventory():
    # Pandas removed. JSON export instead.
    db = SessionLocal()
    try:
        books = db.query(Book).filter(Book.takedown == False).all()
        data = []
        for book in books:
            exists, _ = check_book_on_disk(book)
            data.append({
                "EAN": book.ean,
                "Author": book.author,
                "Title": book.title,
                "Release Date": book.release_date,
                "Status": "In Library" if exists else "Missing"
            })
        
        # Return JSON direct for now
        return data
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    # Use 0.0.0.0 for docker
    uvicorn.run(app, host="0.0.0.0", port=8000)
else:
    if os.path.isdir("/app/frontend_dist"):
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory="/app/frontend_dist", html=True), name="static")
