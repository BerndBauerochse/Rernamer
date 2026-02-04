import os
import re
import logging
import shutil
import subprocess
import zipfile
import time
import threading
import concurrent.futures
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Book

# Configurable Logger
class RenamerLogger:
    def __init__(self):
        self.listeners = []
        self.history = []

    def add_listener(self, callback):
        self.listeners.append(callback)

    def info(self, message):
        self._emit("INFO", message)

    def error(self, message):
        self._emit("ERROR", message)

    def warning(self, message):
        self._emit("WARNING", message)

    def debug(self, message):
        # Optional: don't flood UI with debug unless requested
        # self._emit("DEBUG", message)
        pass

    def _emit(self, level, message):
        entry = {
            "timestamp": time.time(),
            "level": level,
            "message": message
        }
        # Force immediate print to Docker console
        print(f"{level}: {message}", flush=True)
        
        self.history.append(entry)
        # Keep history limited
        if len(self.history) > 1000:
            self.history.pop(0)
            
        for listener in self.listeners:
            try:
                listener(entry)
            except:
                pass

logger = RenamerLogger()

# Global State
stop_event = threading.Event()

def sanitize_filename(name):
    if not name:
        return ""
    safe = re.sub(r'[<>:"/\\|?*]', '', str(name)).strip()
    return safe

def get_audio_bitrate(file_path):
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "a:0", 
            "-show_entries", "stream=bit_rate", 
            "-of", "default=noprint_wrappers=1:nokey=1", file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            return 0
        val = result.stdout.strip()
        if val.isdigit():
            return int(val)
        return 0
    except Exception as e:
        logger.error(f"Error checking bitrate for {file_path}: {e}")
        return 0

def get_image_width(file_path):
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0", 
            "-show_entries", "stream=width", 
            "-of", "default=noprint_wrappers=1:nokey=1", file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            return 0
        val = result.stdout.strip()
        if val.isdigit():
            return int(val)
        return 0
    except Exception as e:
        logger.error(f"Error checking image width for {file_path}: {e}")
        return 0

def resize_image_if_needed(file_info):
    if stop_event.is_set(): return
    full_path, root, file = file_info
    MAX_WIDTH = 600
    
    try:
        width = get_image_width(full_path)
        if width == 0 or width <= MAX_WIDTH:
            return

        logger.info(f"Resizing image {file} ({width}px -> {MAX_WIDTH}px)...")
        temp_path = os.path.join(root, f"temp_{file}")
        
        cmd = [
            "ffmpeg", "-i", full_path, "-vf", f"scale={MAX_WIDTH}:-1", 
            "-q:v", "6", "-y", temp_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if result.returncode == 0:
            os.replace(temp_path, full_path)
            logger.info(f"Resized {file} successfully.")
        else:
            logger.error(f"FFmpeg error resizing {file}: {result.stderr}")
            if os.path.exists(temp_path): os.remove(temp_path)
    except Exception as e:
        logger.error(f"Error resizing {file}: {e}")

def convert_single_file(file_info):
    if stop_event.is_set(): return
    full_path, root, file = file_info
    temp_path = os.path.join(root, f"temp_{file}")
    
    try:
        bitrate = get_audio_bitrate(full_path)
        if 92000 <= bitrate <= 100000:
            return # Already ~96k

        logger.info(f"Converting {file} to 96k (Current: {bitrate})...")
        cmd = [
            "ffmpeg", "-i", full_path, "-codec:a", "libmp3lame", 
            "-b:a", "96k", "-y", temp_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if result.returncode == 0:
            os.replace(temp_path, full_path)
            logger.info(f"Converted {file} successfully.")
        else:
            logger.error(f"FFmpeg error on {file}: {result.stderr}")
            if os.path.exists(temp_path): os.remove(temp_path)

    except Exception as e:
        logger.error(f"Error converting {file}: {e}")
        if os.path.exists(temp_path): os.remove(temp_path)

def convert_folder_to_96k(folder_path):
    logger.info(f"Optimizing folder: {folder_path}...")
    mp3_files = []
    image_files = []
    
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            lower = file.lower()
            if lower.endswith(".mp3"):
                mp3_files.append((os.path.join(root, file), root, file))
            elif lower.endswith((".jpg", ".jpeg", ".png")):
                image_files.append((os.path.join(root, file), root, file))
    
    workers = 1 
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        if mp3_files: executor.map(convert_single_file, mp3_files)
        if image_files: executor.map(resize_image_if_needed, image_files)

def cleanup_takedowns(db: Session, library_path: str):
    logger.info("Scanning for TAKEDOWN content...")
    forbidden_books = db.query(Book).filter(Book.takedown == True).all()
    forbidden_eans = set([b.ean for b in forbidden_books])
    
    if not forbidden_eans: return

    trash_dir = os.path.join(library_path, "_DUPLICATES_TO_DELETE")
    os.makedirs(trash_dir, exist_ok=True)

    for root, dirs, files in os.walk(library_path):
        if stop_event.is_set(): return
        if "_DUPLICATES_TO_DELETE" in root: continue
            
        found_takedown_ean = None
        for file in files:
            if file.lower().endswith((".jpg", ".jpeg")):
                name_no_ext = os.path.splitext(file)[0]
                if name_no_ext in forbidden_eans:
                    found_takedown_ean = name_no_ext
                    break
        
        if found_takedown_ean:
            logger.warning(f"Removing takedown content: {found_takedown_ean} in {root}")
            target_path = os.path.join(trash_dir, os.path.basename(root))
            if os.path.exists(target_path): target_path += f"_{int(time.time())}"
            try:
                shutil.move(root, target_path)
            except Exception as e:
                logger.error(f"Failed to move takedown folder: {e}")

def cleanup_metadata_files(library_path):
    """Deletes metadata.json files older than 72 hours (3 days)."""
    limit = 72 * 3600  # 3 days in seconds
    now = time.time()
    count = 0
    
    # We only want to clean inside the library structure, not the root indiscriminately
    # But os.walk is safe enough if we check filename
    for root, dirs, files in os.walk(library_path):
        if stop_event.is_set(): return
        
        # Skip special folders
        if "_DUPLICATES_TO_DELETE" in root: continue

        if "metadata.json" in files:
            full_path = os.path.join(root, "metadata.json")
            try:
                mtime = os.path.getmtime(full_path)
                if now - mtime > limit:
                    os.remove(full_path)
                    count += 1
            except Exception as e:
                logger.debug(f"Error checking metadata file {full_path}: {e}")
    
    if count > 0:
        logger.info(f"Maintenance: Removed {count} old metadata.json files.")

def run_once(library_path):
    if not os.path.exists(library_path):
        logger.error(f"Library path not found: {library_path}")
        return

    db: Session = SessionLocal()
    try:
        # Phase 0: Security & Pre-Cleanup
        cleanup_takedowns(db, library_path)

        # Phase 1: Unzip Phase
        # We iterate specifically to find and extract all Zips first.
        # This ensures they are ready as folders for Phase 2.
        
        # Scan current items
        current_items = os.listdir(library_path)
        zip_files = [i for i in current_items if os.path.isfile(os.path.join(library_path, i)) and i.lower().endswith('.zip')]
        
        if zip_files:
            logger.info(f"Phase 1: Found {len(zip_files)} zip(s) to extract.")
            for item in zip_files:
                if stop_event.is_set(): break
                item_path = os.path.join(library_path, item)
                try:
                    logger.info(f"Unzipping {item}...")
                    folder_name = os.path.splitext(item)[0]
                    target_path = os.path.join(library_path, folder_name)
                    os.makedirs(target_path, exist_ok=True)
                    
                    with zipfile.ZipFile(item_path, 'r') as zip_ref:
                        zip_ref.extractall(target_path)
                    
                    # Flatten single sub-folder if present
                    items = os.listdir(target_path)
                    if len(items) == 1 and os.path.isdir(os.path.join(target_path, items[0])):
                        sub = os.path.join(target_path, items[0])
                        for s in os.listdir(sub):
                            shutil.move(os.path.join(sub, s), target_path)
                        os.rmdir(sub)
                        
                    os.remove(item_path)
                except Exception as e:
                    logger.error(f"Zip extraction error for {item}: {e}")
                    continue

        if stop_event.is_set(): return

        # Phase 2: Processing & Renaming Phase
        # Now we look for EAN folders (including those just extracted)
        current_items = os.listdir(library_path) # Refresh list!
        ean_folders = [i for i in current_items if os.path.isdir(os.path.join(library_path, i)) and re.match(r'^\d{13}$', i)]
        
        if ean_folders:
            logger.info(f"Phase 2: Processing {len(ean_folders)} book folder(s)...")
            
            for item in ean_folders:
                if stop_event.is_set(): break
                item_path = os.path.join(library_path, item)
                ean = item
                
                book = db.query(Book).filter(Book.ean == ean).first()
                if book:
                    if book.takedown:
                        logger.warning(f"TAKEDOWN {ean}. Deleting.")
                        shutil.move(item_path, os.path.join(library_path, "_DUPLICATES_TO_DELETE", ean))
                        continue

                    safe_author = sanitize_filename(book.author or "Unknown")
                    safe_title = sanitize_filename(book.title or "Unknown")
                    
                    # Naming Logic
                    final_title = safe_title
                    if book.abridged_status:
                        status_lower = book.abridged_status.lower().strip()
                        if "hörspiel" in status_lower or "hoerspiel" in status_lower or "hsp" in status_lower:
                            final_title = f"{safe_title}_Hsp"
                        elif "ungekürzt" in status_lower or "ungekuerzt" in status_lower or "unabridged" in status_lower:
                            final_title = f"{safe_title} (ungekuerzt)"
                        elif "gekürzt" in status_lower or "gekuerzt" in status_lower or "abridged" in status_lower:
                            final_title = f"{safe_title} (gekuerzt)"
                        else:
                            safe_abridged = sanitize_filename(book.abridged_status)
                            final_title = f"{safe_title} ({safe_abridged})"
                    
                    # Define destinations
                    author_dir = os.path.join(library_path, safe_author)
                    new_book_path = os.path.join(author_dir, final_title)
                    
                    if os.path.exists(new_book_path):
                        logger.warning(f"Target '{final_title}' already exists. Skipping move.")
                    else:
                        # 1. Optimize
                        convert_folder_to_96k(item_path)
                        
                        # 2. Move
                        os.makedirs(author_dir, exist_ok=True)
                        shutil.move(item_path, new_book_path)
                        
                        # 3. Metadata
                        import json
                        metadata_path = os.path.join(new_book_path, "metadata.json")
                        metadata = {"isbn": ean}
                        
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
                        
                        logger.info(f"Finished: {final_title}")
                else:
                    logger.debug(f"Ignored Unknown EAN folder: {ean}")

        # Phase 3: Maintenance
        if not stop_event.is_set():
             cleanup_metadata_files(library_path)

    except Exception as e:
        logger.error(f"Critical Scan Error: {e}")
    finally:
        db.close()
    logger.info("Scan Cycle Complete.")

