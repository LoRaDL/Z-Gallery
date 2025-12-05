# cleanup_rated_images.py
import os
import sqlite3
import sys
import shutil
import datetime
from pathlib import Path

# 添加项目根目录到Python路径
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)  # 切换工作目录到项目根目录

# --- 配置区 ---
# 确认数据库文件名正确
DB_FILE = "zootopia_gallery.db"

# 定义要删除的评级 (1 表示1星)
RATING_TO_DELETE = 1

# 缩略图文件夹的相对路径
THUMBNAIL_DIR = os.path.join('static', 'thumbnails')

# 垃圾箱目录（将被移动到这里，而不是删除）
TRASH_DIR = os.path.join('.', 'trash')

def cleanup_images():
    """
    执行查找、统计、确认并删除指定评级的图片和数据库记录的流程。
    """
    print("--- 图片清理脚本 ---")

    # 1. 安全检查: 确认数据库文件存在
    if not os.path.exists(DB_FILE):
        print(f"错误: 数据库文件 '{DB_FILE}' 未找到。请确保此脚本与数据库在同一目录下。")
        sys.exit(1)

    conn = None
    try:
        # 2. 连接数据库并查询目标记录
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row # 让我们能通过列名访问数据
        cursor = conn.cursor()
        print(f"已连接到数据库 '{DB_FILE}'。")

        print(f"正在查找所有评级为 {RATING_TO_DELETE} 星的图片...")
        cursor.execute(
            "SELECT id, file_path, thumbnail_filename FROM artworks WHERE rating = ?",
            (RATING_TO_DELETE,)
        )
        records_to_delete = cursor.fetchall()
        count = len(records_to_delete)

        if count == 0:
            print(f"没有找到评级为 {RATING_TO_DELETE} 星的图片。无需任何操作。")
            return

        # 3. 统计并向用户确认
        print(f"\n发现 {count} 张评级为 {RATING_TO_DELETE} 星的图片将被永久删除。")
        print("此操作将同时删除数据库记录和对应的图片文件（原图和缩略图）。")
        print("此操作不可逆！")
        
        choice = input("你确定要继续吗？ (输入 'yes' 删除): ")
        if choice.lower() != 'yes':
            print("操作已取消。")
            return

        # 4. 执行删除操作（改为移动到垃圾箱）
        print("\n开始将文件移动到垃圾箱并删除数据库记录...")
        deleted_files_count = 0
        deleted_records_count = 0

        # 确保垃圾箱及缩略图子目录存在
        try:
            os.makedirs(TRASH_DIR, exist_ok=True)
            trash_thumbs_dir = os.path.join(TRASH_DIR, 'thumbnails')
            os.makedirs(trash_thumbs_dir, exist_ok=True)
        except OSError as e:
            print(f"无法创建垃圾箱目录 '{TRASH_DIR}': {e}")
            # 继续执行，但移动操作可能失败
            trash_thumbs_dir = os.path.join(TRASH_DIR, 'thumbnails')

        for row in records_to_delete:
            artwork_id = row['id']
            original_path = row['file_path']
            thumbnail_filename = row['thumbnail_filename']

            # a. 移动原图文件到垃圾箱
            if original_path and os.path.exists(original_path):
                try:
                    base = os.path.basename(original_path)
                    target = os.path.join(TRASH_DIR, base)
                    if os.path.exists(target):
                        ts = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
                        name, ext = os.path.splitext(base)
                        target = os.path.join(TRASH_DIR, f"{name}_{ts}{ext}")
                    shutil.move(original_path, target)
                    print(f"  - [文件已移至垃圾箱] ID {artwork_id:06d}: {target}")
                    deleted_files_count += 1
                except OSError as e:
                    print(f"  - [文件移动失败] ID {artwork_id:06d}: {e}")
            else:
                print(f"  - [文件未找到] ID {artwork_id:06d}: {original_path} (已跳过)")

            # b. 移动缩略图文件到垃圾箱缩略图子目录
            if thumbnail_filename:
                thumb_path = os.path.join(THUMBNAIL_DIR, thumbnail_filename)
                if os.path.exists(thumb_path):
                    try:
                        target_thumb = os.path.join(trash_thumbs_dir, thumbnail_filename)
                        if os.path.exists(target_thumb):
                            ts = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
                            name, ext = os.path.splitext(thumbnail_filename)
                            target_thumb = os.path.join(trash_thumbs_dir, f"{name}_{ts}{ext}")
                        shutil.move(thumb_path, target_thumb)
                        print(f"  - [缩略图已移至垃圾箱] ID {artwork_id:06d}: {target_thumb}")
                    except OSError as e:
                        print(f"  - [缩略图移动失败] ID {artwork_id:06d}: {e}")
                else:
                    print(f"  - [缩略图未找到] ID {artwork_id:06d}: {thumb_path} (已跳过)")
            
            # c. 从数据库中删除记录 (暂不提交)
            cursor.execute("DELETE FROM artworks WHERE id = ?", (artwork_id,))
            deleted_records_count += 1

        # 5. 提交所有数据库更改
        conn.commit()
        print("\n所有数据库记录删除操作已提交。")

    except sqlite3.Error as e:
        print(f"\n数据库操作发生错误: {e}")
        if conn:
            conn.rollback() # 如果中途出错，回滚所有数据库更改
    finally:
        if conn:
            conn.close()
            print("数据库连接已关闭。")

    print("\n--- 清理流程完成！---")
    print(f"总共移动了 {deleted_files_count} 个图片文件到垃圾箱（包括原图与缩略图）。")
    print(f"总共删除了 {deleted_records_count} 条数据库记录。")

if __name__ == "__main__":
    cleanup_images()