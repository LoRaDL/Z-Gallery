# gallery_manager.py

# --- 依赖 ---
# 这个脚本需要 Pillow 库来读取图片元数据 (EXIF)
# 请通过 pip 安装: pip install Pillow
# --------------

import os
import re
import sqlite3
import datetime
import config
from PIL import Image
import traceback # 新增: 导入 traceback 模块
import imagehash

# --- 全局常量与辅助函数 (保持不变) ---
THUMBNAIL_DIR = os.path.join('static', 'thumbnails')
THUMBNAIL_SIZE = (400, 400)

def get_publication_date(full_path):
    """
    通过“优先级链条”策略获取最理想的发布日期。
    优先级: 1. EXIF元数据 -> 2. 文件创建时间 (ctime)
    返回一个元组: (datetime对象, 日期来源字符串)
    """
    # 策略 1: 尝试从 EXIF 元数据中读取
    try:
        with Image.open(full_path) as img:
            exif_data = img._getexif()
            if exif_data:
                # 常见的原始创作日期标签ID: 36867 (DateTimeOriginal), 306 (DateTime)
                for tag_id in [36867, 306]:
                    if tag_id in exif_data:
                        date_str = exif_data[tag_id]
                        # EXIF 时间格式通常是 'YYYY:MM:DD HH:MM:SS'
                        return datetime.datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S'), "EXIF"
    except Exception:
        # 如果文件格式不支持EXIF或解析失败，则静默跳过
        pass

    # 策略 2: 使用文件创建时间 (ctime) 作为兜底方案
    ctime = os.path.getctime(full_path)
    return datetime.datetime.fromtimestamp(ctime), "File System (ctime)"


# --- 全新的、统一的解析函数 ---
def parse_unified_structure(full_path, root_folder):
    """
    解析统一的目录结构，并智能地、健壮地处理平台名称和路径。
    """
    try:
        # --- 健壮性改进 1: 统一路径格式和大小写 ---
        norm_full_path = full_path.replace('\\', '/').lower()
        norm_root_folder = root_folder.replace('\\', '/').lower()

        if not norm_full_path.startswith(norm_root_folder):
            return None

        relative_path = os.path.relpath(full_path, root_folder)
        parts = relative_path.replace('\\', '/').split('/')

        if len(parts) < 3:
            return None

        platform = parts[0]
        artist = parts[1]
        filename = parts[-1]
        title = None

        # --- 健壮性改进 2: 修正平台名称检查 ---
        processed_platform_name = platform.replace(' ', '').lower()
        if processed_platform_name == 'zootopianewsnetwork':
            title = os.path.splitext(filename)[0]

        return {
            "source_platform": platform,
            "artist": artist,
            "title": title
            # 注意: 这个结构无法自动解析 category 和 series, 这些需要手动指定
        }
    except Exception as e:
        print(f"  [解析时异常] 在处理 {full_path} 时发生错误: {e}")
        return None

# --- 数据库操作区域 ---

def setup_database():
    """连接数据库并创建最新的表结构"""
    conn = sqlite3.connect(config.DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS artworks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT NOT NULL UNIQUE,
        file_name TEXT NOT NULL,
        thumbnail_filename TEXT,
        phash TEXT,
        title TEXT,
        creation_date DATETIME NOT NULL,
        publication_date DATETIME,
        last_modified_date DATETIME NOT NULL,
        artist TEXT,
        source_platform TEXT,
        source_url TEXT,
        rating INTEGER,
        tags TEXT,
        description TEXT,
        classification TEXT CHECK(classification IN ('sfw', 'mature', 'nsfw')),
        category TEXT NOT NULL DEFAULT 'fanart_non_comic'
            CHECK(category IN ('fanart_comic', 'fanart_non_comic', 'real_photo', 'other'))
    )
    ''')
    print(f"数据库 '{config.DB_FILE}' 已准备就绪。")
    conn.commit()
    conn.close()

def _ensure_thumbnail_dir():
    """确保缩略图目录存在"""
    if not os.path.exists(THUMBNAIL_DIR):
        print(f"创建缩略图目录: {THUMBNAIL_DIR}")
        os.makedirs(THUMBNAIL_DIR)

def _create_thumbnail(full_path, filename):
    """为指定图片创建缩略图"""
    try:
        thumb_path = os.path.join(THUMBNAIL_DIR, filename)
        if os.path.exists(thumb_path):
            return True # 缩略图已存在
        
        with Image.open(full_path) as img:
            img.thumbnail(THUMBNAIL_SIZE)
            # 确保保存时是RGB，避免一些PNG格式问题
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(thumb_path, "JPEG", quality=85)
        return True
    except Exception as e:
        print(f"  [!] 无法创建缩略图 for {filename}: {e}")
        return False

def scan_and_update_database():
    """扫描统一的根文件夹，只添加新文件，并对新文件进行详细的调试输出。"""
    # 确保缩略图目录存在
    if not os.path.exists(THUMBNAIL_DIR):
        os.makedirs(THUMBNAIL_DIR)
    
    # 检查根目录是否已配置
    if not config.IMAGES_ROOT_FOLDER or "path/to/your" in config.IMAGES_ROOT_FOLDER:
        print("错误: 请先在 config.py 中正确配置 'IMAGES_ROOT_FOLDER'！")
        return
    if not os.path.isdir(config.IMAGES_ROOT_FOLDER):
        print(f"错误: 配置的路径 '{config.IMAGES_ROOT_FOLDER}' 不是一个有效的文件夹。")
        return

    conn = sqlite3.connect(config.DB_FILE)
    # 让返回的行可以像字典一样访问
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print(f"\n--- 开始扫描根目录 (最终调试模式): {config.IMAGES_ROOT_FOLDER} ---")
    new_files_count = 0
    total_files_scanned = 0
    skipped_count = 0

    # 递归遍历所有子文件夹
    for dirpath, _, filenames in os.walk(config.IMAGES_ROOT_FOLDER):
        for filename in filenames:
            total_files_scanned += 1
            original_path = os.path.join(dirpath, filename)
            full_path = original_path.replace('\\', '/')

            # 检查数据库
            cursor.execute("SELECT id FROM artworks WHERE file_path = ?", (full_path,))
            existing_record = cursor.fetchone()
            
            # --- 核心改动: 如果记录已存在，则安静地跳过 ---
            if existing_record:
                skipped_count += 1
                continue
            
            # --- 从这里开始，处理所有“新”文件，并打印详细信息 ---
            print(f"\n[新文件] 发现: {full_path}")
            
            # 检查文件扩展名
            if not filename.lower().endswith(config.SUPPORTED_EXTENSIONS):
                print("  [跳过] 原因: 文件扩展名不受支持。")
                continue

            try:
                # 1. 使用统一的解析函数
                parsed_data = parse_unified_structure(full_path, config.IMAGES_ROOT_FOLDER)
                
                print(f"  [解析结果] parsed_data = {parsed_data}")

                if not parsed_data:
                    print("  [拒绝] 原因: 解析函数返回 None，目录结构不符合预期。")
                    continue

                # 2. 获取日期信息 (使用 original_path 进行文件系统操作)
                file_creation_date = datetime.datetime.fromtimestamp(os.path.getctime(original_path))
                publication_date_obj, _ = get_publication_date(original_path)
                last_modified_date = datetime.datetime.now()

                # 计算感知哈希 (phash)
                phash_value = None
                try:
                    with Image.open(original_path) as _img_for_hash:
                        phash_value = str(imagehash.phash(_img_for_hash))
                except Exception as e:
                    print(f"  [警告] 计算 phash 失败: {e}")
                    phash_value = None

                # 3. 插入记录以获取ID，确保 file_path 存储的是规范化后的路径
                columns = ['file_path', 'file_name', 'creation_date', 'publication_date', 'last_modified_date', 'phash']
                values = [
                    full_path, filename,
                    file_creation_date.strftime("%Y-%m-%d %H:%M:%S"),
                    publication_date_obj.strftime("%Y-%m-%d %H:%M:%S"),
                    last_modified_date.strftime("%Y-%m-%d %H:%M:%S"),
                    phash_value
                ]

                # 将从路径中解析出的数据动态添加到列和值的列表中
                for key, value in parsed_data.items():
                    if value is not None:
                        columns.append(key)
                        values.append(value)

                column_names_str = ", ".join(columns)
                placeholders_str = ", ".join(["?"] * len(values))
                sql_query = f"INSERT INTO artworks ({column_names_str}) VALUES ({placeholders_str})"
                
                cursor.execute(sql_query, values)
                
                # 4. 获取ID并生成缩略图
                new_id = cursor.lastrowid
                thumbnail_filename = f"{new_id:06d}.jpg"
                
                # 创建缩略图时，使用原始路径来打开文件
                with Image.open(original_path) as img:
                    img.thumbnail(THUMBNAIL_SIZE)
                    if img.mode != 'RGB': img = img.convert('RGB')
                    img.save(os.path.join(THUMBNAIL_DIR, thumbnail_filename), "JPEG", quality=85)
                
                # 5. 更新记录，存入缩略图文件名
                cursor.execute(
                    "UPDATE artworks SET thumbnail_filename = ? WHERE id = ?",
                    (thumbnail_filename, new_id)
                )
                
                new_files_count += 1
                print(f"  [成功] 已添加入库 (ID: {new_id:06d})")
            
            except Exception as e:
                print(f"  [致命错误] 处理文件时发生未知异常: {e}")
                traceback.print_exc()

    # 提交所有数据库更改
    conn.commit()
    conn.close()

    print("\n--- 扫描完成 (最终调试模式) ---")
    print(f"共扫描 {total_files_scanned} 个文件。")
    print(f"跳过了 {skipped_count} 个已存在的记录。")
    print(f"发现 {new_files_count} 张新图片已添加到数据库。")
    print("------------------\n")

def backfill_publication_dates():
    """(一次性函数) 为数据库中已存在但缺少发布日期的记录填充该字段"""
    conn = sqlite3.connect(config.DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, file_path FROM artworks WHERE publication_date IS NULL")
    records_to_update = cursor.fetchall()
    
    if not records_to_update:
        print("所有记录都已有发布日期，无需填充。")
        conn.close()
        return

    print(f"\n开始为 {len(records_to_update)} 条旧记录回填发布日期...")
    updated_count = 0
    for record_id, file_path in records_to_update:
        # Note: file_path from DB might be normalized (forward slashes)
        # For os.path.exists and Image.open, we need a system-compatible path.
        # On Windows, this means converting back to backslashes if necessary,
        # or ensuring the original file system path is used.
        # For simplicity and robustness, we assume os.path.exists and Image.open
        # can handle forward slashes on Windows, or that the original file_path
        # was stored in a way that allows direct use.
        # If issues arise, file_path.replace('/', os.sep) might be needed here.
        if os.path.exists(file_path): 
            publication_date_obj, date_source = get_publication_date(file_path)
            cursor.execute(
                "UPDATE artworks SET publication_date = ? WHERE id = ?",
                (publication_date_obj.strftime("%Y-%m-%d %H:%M:%S"), record_id)
            )
            print(f"  -> 更新 ID {record_id} (来源: {date_source})")
            updated_count += 1
        else:
            print(f"  [!] 警告: 文件路径不存在，无法更新 ID {record_id}: {file_path}")
            
    conn.commit()
    conn.close()
    print(f"\n回填完成！共更新 {updated_count} 条记录。")

# --- 主程序入口 ---
if __name__ == "__main__":
    setup_database()
    
    scan_and_update_database()
