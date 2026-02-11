import os
import re
import logging
import shutil
import subprocess
import zipfile
import time
import tempfile
import threading
import json
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
            "message": message,
        }
        # Force immediate print to Docker console
        print(f"{level}: {message}", flush=True)

        self.history.append(entry)
        if len(self.history) > 1000:
            self.history.pop(0)

        for listener in self.listeners:
            try:
                listener(entry)
            except Exception:
                pass


logger = RenamerLogger()

# Global State
stop_event = threading.Event()


def sanitize_filename(name):
    if not name:
        return ""
    return re.sub(r'[<>:"/\\|?*]', "", str(name)).strip()


def get_audio_bitrate(file_path):
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=bit_rate",
            "-of", "default=noprint_wrappers=1:nokey=1", file_path,
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            return 0
        val = result.stdout.strip()
        return int(val) if val.isdigit() else 0
    except Exception as e:
        logger.error(f"Error checking bitrate for {file_path}: {e}")
        return 0


def get_image_width(file_path):
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width",
            "-of", "default=noprint_wrappers=1:nokey=1", file_path,
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            return 0
        val = result.stdout.strip()
        return int(val) if val.isdigit() else 0
    except Exception as e:
        logger.error(f"Error checking image width for {file_path}: {e}")
        return 0


def resize_image_if_needed(file_info):
    if stop_event.is_set():
        return
    full_path, root, file_name = file_info
    max_width = 600

    try:
        width = get_image_width(full_path)
        if width == 0 or width <= max_width:
            return

        logger.info(f"Resizing image {file_name} ({width}px -> {max_width}px)...")
        temp_path = os.path.join(root, f"temp_{file_name}")

        cmd = [
            "ffmpeg", "-i", full_path, "-vf", f"scale={max_width}:-1",
            "-q:v", "6", "-y", temp_path,
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if result.returncode == 0:
            os.replace(temp_path, full_path)
            logger.info(f"Resized {file_name} successfully.")
        else:
            logger.error(f"FFmpeg error resizing {file_name}: {result.stderr}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
    except Exception as e:
        logger.error(f"Error resizing {file_name}: {e}")


def convert_single_file(file_info):
    if stop_event.is_set():
        return
    full_path, root, file_name = file_info
    temp_path = os.path.join(root, f"temp_{file_name}")

    try:
        bitrate = get_audio_bitrate(full_path)
        if 92000 <= bitrate <= 100000:
            return

        logger.info(f"Converting {file_name} to 96k (Current: {bitrate})...")
        cmd = [
            "ffmpeg", "-i", full_path, "-codec:a", "libmp3lame",
            "-b:a", "96k", "-y", temp_path,
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if result.returncode == 0:
            os.replace(temp_path, full_path)
            logger.info(f"Converted {file_name} successfully.")
        else:
            logger.error(f"FFmpeg error on {file_name}: {result.stderr}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

    except Exception as e:
        logger.error(f"Error converting {file_name}: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)


def convert_folder_to_96k(folder_path):
    logger.info(f"Optimizing folder: {folder_path}...")
    mp3_files = []
    image_files = []

    for root, dirs, files in os.walk(folder_path):
        for file_name in files:
            lower = file_name.lower()
            if lower.endswith(".mp3"):
                mp3_files.append((os.path.join(root, file_name), root, file_name))
            elif lower.endswith((".jpg", ".jpeg", ".png")):
                image_files.append((os.path.join(root, file_name), root, file_name))

    workers = 1
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        if mp3_files:
            executor.map(convert_single_file, mp3_files)
        if image_files:
            executor.map(resize_image_if_needed, image_files)


def normalize_abridged_status(raw_status):
    if not raw_status:
        return ""
    return (
        str(raw_status).lower().strip()
        .replace("\u00e4", "ae")
        .replace("\u00f6", "oe")
        .replace("\u00fc", "ue")
        .replace("\u00df", "ss")
        .replace("Ã¤", "ae")
        .replace("Ã¶", "oe")
        .replace("Ã¼", "ue")
        .replace("ÃŸ", "ss")
        .replace("ÃƒÂ¶", "oe")
        .replace("ÃƒÂ¼", "ue")
        .replace("ÃƒÆ’Ã‚Â¶", "oe")
        .replace("ÃƒÆ’Ã‚Â¼", "ue")
        .replace("Ã£Â¶", "oe")
        .replace("Ã£Â¼", "ue")
    )


def cleanup_takedowns(db: Session, library_path: str):
    logger.info("Scanning for TAKEDOWN content...")
    forbidden_books = db.query(Book).filter(Book.takedown == True).all()
    forbidden_eans = set([b.ean for b in forbidden_books])

    if not forbidden_eans:
        return

    trash_dir = os.path.join(library_path, "_DUPLICATES_TO_DELETE")
    os.makedirs(trash_dir, exist_ok=True)

    for root, dirs, files in os.walk(library_path):
        if stop_event.is_set():
            return
        if "_DUPLICATES_TO_DELETE" in root:
            continue

        found_takedown_ean = None
        for file_name in files:
            if file_name.lower().endswith((".jpg", ".jpeg")):
                name_no_ext = os.path.splitext(file_name)[0]
                if name_no_ext in forbidden_eans:
                    found_takedown_ean = name_no_ext
                    break

        if found_takedown_ean:
            logger.warning(f"Removing takedown content: {found_takedown_ean} in {root}")
            target_path = os.path.join(trash_dir, os.path.basename(root))
            if os.path.exists(target_path):
                target_path += f"_{int(time.time())}"
            try:
                shutil.move(root, target_path)
            except Exception as e:
                logger.error(f"Failed to move takedown folder: {e}")


def cleanup_metadata_files(library_path):
    """No-op maintenance hook. metadata.json is intentionally kept for ABS imports."""
    return


def flatten_single_subfolder(folder_path):
    """If folder contains exactly one subfolder, move its contents one level up."""
    items = os.listdir(folder_path)
    if len(items) != 1:
        return
    sub_path = os.path.join(folder_path, items[0])
    if not os.path.isdir(sub_path):
        return

    for name in os.listdir(sub_path):
        shutil.move(os.path.join(sub_path, name), folder_path)
    os.rmdir(sub_path)


def build_final_title(book, safe_title):
    # Do not encode abridged/unabridged in folder names.
    return safe_title


def merge_folder_contents(src_dir, dst_dir):
    """Move source contents into destination without creating a second book folder."""
    for name in os.listdir(src_dir):
        src_item = os.path.join(src_dir, name)
        dst_item = os.path.join(dst_dir, name)

        if os.path.isdir(src_item):
            os.makedirs(dst_item, exist_ok=True)
            merge_folder_contents(src_item, dst_item)
            if os.path.exists(src_item):
                try:
                    os.rmdir(src_item)
                except OSError:
                    pass
        else:
            if os.path.exists(dst_item):
                base, ext = os.path.splitext(name)
                dst_item = os.path.join(dst_dir, f"{base}_{int(time.time())}{ext}")
            shutil.move(src_item, dst_item)


def cleanup_duplicate_suffix_folders(library_path):
    """Merge legacy duplicate folders like 'Title_1770793951' into 'Title'."""
    suffix_pattern = re.compile(r"^(.+)_\d{8,}$")
    merged_count = 0

    for root, dirs, files in os.walk(library_path):
        if stop_event.is_set():
            return
        if "_DUPLICATES_TO_DELETE" in root:
            continue

        for dir_name in list(dirs):
            match = suffix_pattern.match(dir_name)
            if not match:
                continue
            base_name = match.group(1)
            duplicate_path = os.path.join(root, dir_name)
            base_path = os.path.join(root, base_name)
            if not os.path.isdir(base_path):
                continue
            try:
                logger.warning(f"Merging duplicate folder '{dir_name}' into '{base_name}'.")
                merge_folder_contents(duplicate_path, base_path)
                shutil.rmtree(duplicate_path, ignore_errors=True)
                merged_count += 1
            except Exception as dup_err:
                logger.error(f"Failed to merge duplicate folder '{dir_name}': {dup_err}")

    if merged_count > 0:
        logger.info(f"Maintenance: Merged {merged_count} duplicate folder(s).")


def write_metadata_file(folder_path, ean, narrator, abridged_status):
    metadata = {"isbn": ean}

    if abridged_status:
        metadata["abridged_status"] = abridged_status
        status_norm = normalize_abridged_status(abridged_status)
        if "ungekuerzt" in status_norm or "unabridged" in status_norm:
            metadata["abridged"] = False
        elif "gekuerzt" in status_norm or "abridged" in status_norm:
            metadata["abridged"] = True

    if narrator:
        narrators = []
        for part in narrator.split(";"):
            part = part.strip()
            if not part:
                continue
            if "," in part:
                last, first = part.split(",", 1)
                narrators.append(f"{first.strip()} {last.strip()}".strip())
            else:
                narrators.append(part)
        if narrators:
            metadata["narrators"] = narrators

    metadata_path = os.path.join(folder_path, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as mf:
        json.dump(metadata, mf, ensure_ascii=False, indent=2)


def process_ean_folder(db: Session, library_path: str, ean: str, source_path: str):
    if stop_event.is_set():
        return False

    book = db.query(Book).filter(Book.ean == ean).first()
    if not book:
        logger.debug(f"Ignored Unknown EAN folder: {ean}")
        return False

    if book.takedown:
        logger.warning(f"TAKEDOWN {ean}. Deleting.")
        trash_dir = os.path.join(library_path, "_DUPLICATES_TO_DELETE")
        os.makedirs(trash_dir, exist_ok=True)
        target = os.path.join(trash_dir, ean)
        if os.path.exists(target):
            target = f"{target}_{int(time.time())}"
        shutil.move(source_path, target)
        return True

    safe_author = sanitize_filename(book.author or "Unknown")
    safe_title = sanitize_filename(book.title or "Unknown")
    final_title = build_final_title(book, safe_title)

    author_dir = os.path.join(library_path, safe_author)
    final_path = os.path.join(author_dir, final_title)
    os.makedirs(author_dir, exist_ok=True)

    if os.path.abspath(source_path) != os.path.abspath(final_path):
        if os.path.exists(final_path):
            logger.warning(f"Target '{final_title}' exists. Merging into existing folder.")
            merge_folder_contents(source_path, final_path)
            if os.path.exists(source_path):
                shutil.rmtree(source_path, ignore_errors=True)
        else:
            shutil.move(source_path, final_path)

    convert_folder_to_96k(final_path)

    try:
        write_metadata_file(final_path, ean, book.narrator, book.abridged_status)
    except Exception as meta_err:
        logger.warning(f"Could not write metadata.json: {meta_err}")

    logger.info(f"Finished: {os.path.basename(final_path)}")
    return True


def run_once(library_path):
    if not os.path.exists(library_path):
        logger.error(f"Library path not found: {library_path}")
        return

    db: Session = SessionLocal()
    try:
        # Phase 0: Security & Pre-Cleanup
        cleanup_takedowns(db, library_path)
        cleanup_duplicate_suffix_folders(library_path)

        # Phase 1: Unzip outside library, then move directly into final structure.
        current_items = os.listdir(library_path)
        zip_files = [
            i for i in current_items if os.path.isfile(os.path.join(library_path, i)) and i.lower().endswith(".zip")
        ]

        if zip_files:
            logger.info(f"Phase 1: Found {len(zip_files)} zip(s) to extract.")
            for item in zip_files:
                if stop_event.is_set():
                    break
                item_path = os.path.join(library_path, item)
                temp_dir = None
                try:
                    logger.info(f"Unzipping {item}...")
                    ean = os.path.splitext(item)[0]
                    temp_dir = tempfile.mkdtemp(prefix=f"renamer_{ean}_")

                    with zipfile.ZipFile(item_path, "r") as zip_ref:
                        zip_ref.extractall(temp_dir)

                    flatten_single_subfolder(temp_dir)
                    processed = process_ean_folder(db, library_path, ean, temp_dir)
                    if processed:
                        os.remove(item_path)
                    else:
                        logger.warning(f"No DB match for {ean}. Keeping zip '{item}'.")
                except Exception as e:
                    logger.error(f"Zip extraction error for {item}: {e}")
                finally:
                    if temp_dir and os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir, ignore_errors=True)

        if stop_event.is_set():
            return

        # Phase 2: Process existing EAN folders in root.
        current_items = os.listdir(library_path)
        ean_folders = [
            i for i in current_items if os.path.isdir(os.path.join(library_path, i)) and re.match(r"^\d{13}$", i)
        ]

        if ean_folders:
            logger.info(f"Phase 2: Processing {len(ean_folders)} book folder(s)...")
            for item in ean_folders:
                if stop_event.is_set():
                    break
                process_ean_folder(db, library_path, item, os.path.join(library_path, item))

        # Phase 3: Maintenance
        if not stop_event.is_set():
            cleanup_metadata_files(library_path)

    except Exception as e:
        logger.error(f"Critical Scan Error: {e}")
    finally:
        db.close()
    logger.info("Scan Cycle Complete.")