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

    def remove_listener(self, callback):
        try:
            self.listeners.remove(callback)
        except ValueError:
            pass

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


def normalize_ean(raw_ean):
    """Return a comparable ISBN/EAN representation."""
    if raw_ean is None:
        return ""

    value = str(raw_ean).strip()
    if value.endswith(".0") and value[:-2].isdigit():
        value = value[:-2]
    return re.sub(r"[\s-]", "", value)


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
    """Build a stable folder name that separates different audio versions."""
    status_norm = normalize_abridged_status(getattr(book, "abridged_status", None))
    if not status_norm:
        return safe_title

    if "hoerspiel" in status_norm or "hsp" in status_norm:
        return f"{safe_title}_Hsp"
    if any(keyword in status_norm for keyword in ("lesung", "lese", "reading", "narrated")):
        return f"{safe_title}_Lesung"
    if "ungekuerzt" in status_norm or "unabridged" in status_norm:
        return f"{safe_title} (ungekuerzt)"
    if "gekuerzt" in status_norm or "abridged" in status_norm:
        return f"{safe_title} (gekuerzt)"

    safe_status = sanitize_filename(getattr(book, "abridged_status", ""))
    return f"{safe_title} ({safe_status})" if safe_status else safe_title


def _remove_path(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.remove(path)


def _remove_generated_duplicate_variants(folder_path, file_name):
    """Remove timestamped copies created by older versions of the renamer."""
    base, ext = os.path.splitext(file_name)
    pattern = re.compile(rf"^{re.escape(base)}_\d{{10}}{re.escape(ext)}$", re.IGNORECASE)

    try:
        for candidate in os.listdir(folder_path):
            if pattern.match(candidate):
                duplicate_path = os.path.join(folder_path, candidate)
                _remove_path(duplicate_path)
                logger.info(f"Removed old duplicate track '{candidate}'.")
    except FileNotFoundError:
        pass


def merge_folder_contents(src_dir, dst_dir):
    """Merge source contents, replacing same-named destination files.

    The previous implementation appended ``_<timestamp>`` on conflicts. That
    creates a second copy of every track on every re-import and makes
    Audiobookshelf see duplicate tracks.
    """
    os.makedirs(dst_dir, exist_ok=True)

    for name in os.listdir(src_dir):
        src_item = os.path.join(src_dir, name)
        dst_item = os.path.join(dst_dir, name)

        if os.path.isdir(src_item):
            if os.path.exists(dst_item) and not os.path.isdir(dst_item):
                _remove_path(dst_item)
            os.makedirs(dst_item, exist_ok=True)
            merge_folder_contents(src_item, dst_item)
            if os.path.exists(src_item):
                try:
                    os.rmdir(src_item)
                except OSError:
                    pass
        else:
            _remove_generated_duplicate_variants(dst_dir, name)
            if os.path.exists(dst_item):
                _remove_path(dst_item)
            shutil.move(src_item, dst_item)


def read_folder_ean(folder_path):
    """Read the ISBN/EAN identifying a processed book folder, if available."""
    metadata_path = os.path.join(folder_path, "metadata.json")
    try:
        with open(metadata_path, "r", encoding="utf-8") as metadata_file:
            metadata = json.load(metadata_file)
        for key in ("isbn", "ean"):
            value = normalize_ean(metadata.get(key))
            if value:
                return value
    except (FileNotFoundError, OSError, ValueError, TypeError):
        pass

    # Older folders may not have metadata.json, but often contain an EAN-named
    # cover. This lets us protect them from being merged with another ISBN.
    try:
        for root, _, files in os.walk(folder_path):
            for file_name in files:
                stem = os.path.splitext(file_name)[0]
                if re.fullmatch(r"(?:\d{10}|\d{13})", stem):
                    return normalize_ean(stem)
    except OSError:
        pass
    return None


def find_folder_for_ean(author_dir, ean):
    """Find an existing author subfolder belonging to the given ISBN/EAN."""
    wanted_ean = normalize_ean(ean)
    if not wanted_ean or not os.path.isdir(author_dir):
        return None

    matches = []
    try:
        for name in os.listdir(author_dir):
            candidate = os.path.join(author_dir, name)
            if os.path.isdir(candidate) and read_folder_ean(candidate) == wanted_ean:
                matches.append(candidate)
    except OSError:
        return None

    # Prefer stable names over legacy timestamp-suffixed folders.
    matches.sort(key=lambda path: (bool(re.search(r"_\d{8,}$", os.path.basename(path))), path.lower()))
    return matches[0] if matches else None


def unique_ean_folder(author_dir, final_title, ean):
    """Return a deterministic free ISBN-qualified folder path."""
    wanted_ean = normalize_ean(ean)
    base_name = f"{final_title} [{wanted_ean}]"
    candidate = os.path.join(author_dir, base_name)
    counter = 2

    while os.path.exists(candidate):
        if read_folder_ean(candidate) == wanted_ean:
            return candidate
        candidate = os.path.join(author_dir, f"{base_name} ({counter})")
        counter += 1
    return candidate


def resolve_book_folder(library_path, safe_author, safe_title, book, ean):
    """Resolve a destination without ever merging different ISBNs."""
    author_dir = os.path.join(library_path, safe_author)
    final_title = build_final_title(book, safe_title)
    preferred_path = os.path.join(author_dir, final_title)
    wanted_ean = normalize_ean(ean)

    existing_path = find_folder_for_ean(author_dir, wanted_ean)
    if existing_path:
        if os.path.abspath(existing_path) == os.path.abspath(preferred_path):
            return preferred_path

        # Migrate an old base-name or timestamp-suffixed folder to the stable
        # status-aware name when that name is free.
        if not os.path.exists(preferred_path):
            shutil.move(existing_path, preferred_path)
            logger.info(
                f"Migrated existing ISBN {wanted_ean} to '{os.path.basename(preferred_path)}'."
            )
            return preferred_path

        # The preferred name belongs to another ISBN. Keep both books apart
        # with a deterministic ISBN suffix instead of a date suffix.
        disambiguated_path = unique_ean_folder(author_dir, final_title, wanted_ean)
        if not os.path.exists(disambiguated_path):
            shutil.move(existing_path, disambiguated_path)
            logger.info(
                f"Separated existing ISBN {wanted_ean} into '{os.path.basename(disambiguated_path)}'."
            )
            return disambiguated_path
        return existing_path

    if not os.path.exists(preferred_path):
        return preferred_path

    # A folder with no trustworthy identity is not safe to merge. A folder
    # with another ISBN is explicitly kept separate as well.
    return unique_ean_folder(author_dir, final_title, wanted_ean)


def find_existing_book_folder(library_path, book):
    """Locate a book folder for the inventory/API without choosing a new path."""
    safe_author = sanitize_filename(book.author or "Unknown")
    safe_title = sanitize_filename(book.title or "Unknown")
    author_dir = os.path.join(library_path, safe_author)
    wanted_ean = normalize_ean(book.ean)

    existing_path = find_folder_for_ean(author_dir, wanted_ean)
    if existing_path:
        return existing_path

    candidates = [
        os.path.join(author_dir, build_final_title(book, safe_title)),
        os.path.join(author_dir, safe_title),
    ]
    for candidate in candidates:
        if not os.path.isdir(candidate):
            continue
        candidate_ean = read_folder_ean(candidate)
        if not candidate_ean or candidate_ean == wanted_ean:
            return candidate

    ean_dir = os.path.join(library_path, str(book.ean))
    return ean_dir if os.path.isdir(ean_dir) else None


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
            duplicate_ean = read_folder_ean(duplicate_path)
            base_ean = read_folder_ean(base_path) if os.path.isdir(base_path) else None
            if duplicate_ean and base_ean and duplicate_ean != base_ean:
                logger.warning(
                    f"Keeping '{dir_name}': ISBN {duplicate_ean} differs from ISBN {base_ean}."
                )
                continue

            try:
                if os.path.exists(base_path):
                    if not duplicate_ean or not base_ean:
                        logger.warning(
                            f"Keeping '{dir_name}': cannot verify that it is the same ISBN as '{base_name}'."
                        )
                        continue
                    logger.warning(f"Merging duplicate folder '{dir_name}' into '{base_name}'.")
                    merge_folder_contents(duplicate_path, base_path)
                    shutil.rmtree(duplicate_path, ignore_errors=True)
                elif duplicate_ean:
                    shutil.move(duplicate_path, base_path)
                    logger.info(f"Renamed legacy folder '{dir_name}' to '{base_name}'.")
                else:
                    continue
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
    author_dir = os.path.join(library_path, safe_author)
    os.makedirs(author_dir, exist_ok=True)
    final_path = resolve_book_folder(library_path, safe_author, safe_title, book, ean)

    if os.path.abspath(source_path) != os.path.abspath(final_path):
        if os.path.exists(final_path):
            logger.warning(
                f"Target '{os.path.basename(final_path)}' exists. Replacing same-named files for ISBN {ean}."
            )
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
