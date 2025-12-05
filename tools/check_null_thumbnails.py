import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)  # 切换工作目录到项目根目录

import sqlite3
import config

def check_null_thumbnails():
    conn = sqlite3.connect(config.DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM artworks WHERE thumbnail_filename IS NULL;")
    count = cursor.fetchone()[0]
    print(f"Number of records with NULL thumbnail_filename: {count}")
    conn.close()

if __name__ == "__main__":
    check_null_thumbnails()