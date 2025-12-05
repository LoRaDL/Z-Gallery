# comics_manager.py

import os
import re
import sqlite3
import datetime
import config
from PIL import Image
import traceback
import imagehash
import natsort

# Comics database file
COMICS_DB_FILE = "zootopia_comics.db"
COMICS_ROOT_FOLDER = "./zootopia_comics"
COMICS_THUMBNAIL_DIR = "static/comics_thumbnails"

# Supported extensions for comic pages (images only)
COMIC_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')

def setup_comics_database():
    """Create comics database tables"""
    conn = sqlite3.connect(COMICS_DB_FILE)
    cursor = conn.cursor()

    # Comics table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS comics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        folder_path TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        artist TEXT,
        source_platform TEXT,
        tags TEXT,
        description TEXT,
        rating INTEGER,
        classification TEXT CHECK(classification IN ('sfw', 'mature', 'nsfw')),
        creation_date DATETIME NOT NULL,
        publication_date DATETIME,
        last_modified_date DATETIME NOT NULL,
        thumbnail_filename TEXT,
        page_count INTEGER DEFAULT 0
    )
    ''')

    # Comic pages table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS comic_pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        comic_id INTEGER NOT NULL,
        page_number INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        file_name TEXT NOT NULL,
        FOREIGN KEY (comic_id) REFERENCES comics (id)
    )
    ''')

    print(f"Comics database '{COMICS_DB_FILE}' ready.")
    conn.commit()
    conn.close()

def _ensure_comics_thumbnail_dir():
    """Ensure comics thumbnail directory exists"""
    if not os.path.exists(COMICS_THUMBNAIL_DIR):
        print(f"Creating comics thumbnail directory: {COMICS_THUMBNAIL_DIR}")
        os.makedirs(COMICS_THUMBNAIL_DIR)

def _create_comic_thumbnail(first_page_path, comic_id):
    """Create thumbnail from first page of comic"""
    try:
        thumbnail_filename = f"comic_{comic_id:06d}.jpg"
        thumb_path = os.path.join(COMICS_THUMBNAIL_DIR, thumbnail_filename)

        if os.path.exists(thumb_path):
            return thumbnail_filename

        with Image.open(first_page_path) as img:
            img.thumbnail((400, 400))
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(thumb_path, "JPEG", quality=85)
        return thumbnail_filename
    except Exception as e:
        print(f"Failed to create thumbnail for comic {comic_id}: {e}")
        return None



def _process_image_sequence(folder_path, comic_id, conn):
    """Process image sequence in folder"""
    cursor = conn.cursor()
    page_files = []

    # Find all image files
    for file in os.listdir(folder_path):
        if file.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')):
            page_files.append(file)

    # Sort naturally
    page_files = natsort.natsorted(page_files)

    for i, filename in enumerate(page_files):
        file_path = os.path.join(folder_path, filename).replace('\\', '/')

        cursor.execute('''
            INSERT INTO comic_pages (comic_id, page_number, file_path, file_name)
            VALUES (?, ?, ?, ?)
        ''', (comic_id, i+1, file_path, filename))

    return len(page_files)

def scan_and_import_comics():
    """Scan comics folder and import new comics"""
    _ensure_comics_thumbnail_dir()

    if not os.path.isdir(COMICS_ROOT_FOLDER):
        print(f"Comics root folder '{COMICS_ROOT_FOLDER}' does not exist.")
        return

    conn = sqlite3.connect(COMICS_DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print(f"\n--- Scanning comics folder: {COMICS_ROOT_FOLDER} ---")
    new_comics_count = 0

    # Scan subfolders
    for item in os.listdir(COMICS_ROOT_FOLDER):
        folder_path = os.path.join(COMICS_ROOT_FOLDER, item)
        if not os.path.isdir(folder_path):
            continue

        # Check if comic already exists
        cursor.execute("SELECT id FROM comics WHERE folder_path = ?", (folder_path.replace('\\', '/'),))
        if cursor.fetchone():
            continue

        print(f"\n[New Comic] Processing: {item}")

        # Get title from folder name
        title = item

        # Find files in folder
        files = []
        for file in os.listdir(folder_path):
            if file.lower().endswith(COMIC_EXTENSIONS):
                files.append(file)

        if not files:
            print("  [Skip] No supported files found")
            continue

        # Check if we have image files
        image_files = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'))]

        if not image_files:
            print("  [Skip] No image files found (PDF not supported)")
            continue

        # Insert comic record
        creation_date = datetime.datetime.now()
        cursor.execute('''
            INSERT INTO comics (folder_path, title, creation_date, last_modified_date)
            VALUES (?, ?, ?, ?)
        ''', (folder_path.replace('\\', '/'), title, creation_date, creation_date))

        comic_id = cursor.lastrowid
        page_count = 0

        # Process image sequence
        page_count = _process_image_sequence(folder_path, comic_id, conn)

        # Update page count
        cursor.execute("UPDATE comics SET page_count = ? WHERE id = ?", (page_count, comic_id))

        # Create thumbnail from first page
        if page_count > 0:
            cursor.execute("SELECT file_path FROM comic_pages WHERE comic_id = ? ORDER BY page_number LIMIT 1", (comic_id,))
            first_page = cursor.fetchone()
            if first_page:
                thumbnail_filename = _create_comic_thumbnail(first_page['file_path'], comic_id)
                if thumbnail_filename:
                    cursor.execute("UPDATE comics SET thumbnail_filename = ? WHERE id = ?", (thumbnail_filename, comic_id))

        new_comics_count += 1
        print(f"  [Success] Added comic '{title}' with {page_count} pages (ID: {comic_id})")

    conn.commit()
    conn.close()

    print(f"\n--- Import complete ---")
    print(f"Added {new_comics_count} new comics")

if __name__ == "__main__":
    setup_comics_database()
    scan_and_import_comics()
