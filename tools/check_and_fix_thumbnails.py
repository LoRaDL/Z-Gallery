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
from PIL import Image, UnidentifiedImageError

THUMBNAIL_DIR = config.THUMBNAIL_DIR
THUMBNAIL_SIZE = config.THUMBNAIL_SIZE


def setup_database_connection():
    """建立数据库连接"""
    conn = sqlite3.connect(config.DB_FILE)
    conn.row_factory = sqlite3.Row  # 让返回的行可以像字典一样访问
    return conn


def get_records_with_null_thumbnails(conn):
    """获取所有thumbnail_filename为NULL的记录"""
    cursor = conn.cursor()
    cursor.execute("SELECT id, file_path FROM artworks WHERE thumbnail_filename IS NULL")
    return cursor.fetchall()


def get_all_artwork_records(conn):
    """获取所有artwork记录用于检查缩略图文件是否存在"""
    cursor = conn.cursor()
    cursor.execute("SELECT id, file_path, thumbnail_filename FROM artworks")
    return cursor.fetchall()


def create_thumbnail(full_path, thumbnail_filename):
    """为指定图片创建缩略图"""
    try:
        thumb_path = os.path.join(THUMBNAIL_DIR, thumbnail_filename)
        
        # 如果缩略图已存在，先删除它
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        
        with Image.open(full_path) as img:
            img.thumbnail(THUMBNAIL_SIZE)
            # 确保保存时是RGB，避免一些PNG格式问题
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(thumb_path, "JPEG", quality=config.THUMBNAIL_QUALITY)
        return True
    except Exception as e:
        print(f"  [!] 无法创建缩略图 {thumbnail_filename}: {e}")
        return False


def is_thumbnail_valid(thumb_path):
    """检查缩略图文件是否有效"""
    try:
        if not os.path.exists(thumb_path):
            return False
        with Image.open(thumb_path) as img:
            img.verify()  # 验证图片文件是否完整
        return True
    except (UnidentifiedImageError, Exception):
        return False


def fix_null_thumbnails(conn):
    """修复thumbnail_filename为NULL的记录"""
    null_records = get_records_with_null_thumbnails(conn)
    fixed_count = 0
    
    if not null_records:
        print("没有发现thumbnail_filename为NULL的记录。")
        return fixed_count
    
    print(f"发现 {len(null_records)} 条记录的thumbnail_filename为NULL，开始修复...")
    
    cursor = conn.cursor()
    for record in null_records:
        artwork_id = record['id']
        file_path = record['file_path']
        
        print(f"  处理 ID {artwork_id}: {file_path}")
        
        # 检查原文件是否存在
        if not os.path.exists(file_path):
            print(f"    [跳过] 原文件不存在: {file_path}")
            continue
        
        # 生成缩略图文件名
        thumbnail_filename = f"{artwork_id:06d}.jpg"
        
        # 创建缩略图
        if create_thumbnail(file_path, thumbnail_filename):
            # 更新数据库记录
            cursor.execute(
                "UPDATE artworks SET thumbnail_filename = ? WHERE id = ?",
                (thumbnail_filename, artwork_id)
            )
            print(f"    [成功] 已为ID {artwork_id} 创建缩略图 {thumbnail_filename}")
            fixed_count += 1
        else:
            print(f"    [失败] 无法为ID {artwork_id} 创建缩略图")
    
    conn.commit()
    print(f"修复完成，共修复了 {fixed_count} 条记录。\n")
    return fixed_count


def check_and_fix_missing_or_corrupted_thumbnails(conn):
    """检查并修复缺失或损坏的缩略图文件"""
    all_records = get_all_artwork_records(conn)
    fixed_count = 0
    
    print("开始检查所有缩略图文件是否存在或损坏...")
    
    for record in all_records:
        artwork_id = record['id']
        file_path = record['file_path']
        thumbnail_filename = record['thumbnail_filename']
        
        # 跳过thumbnail_filename为NULL的记录
        if not thumbnail_filename:
            continue
        
        thumb_path = os.path.join(THUMBNAIL_DIR, thumbnail_filename)
        
        # 检查缩略图是否存在且有效
        if not is_thumbnail_valid(thumb_path):
            print(f"  发现缺失或损坏的缩略图: {thumbnail_filename} (ID: {artwork_id})")
            
            # 检查原文件是否存在
            if not os.path.exists(file_path):
                print(f"    [跳过] 原文件不存在: {file_path}")
                continue
            
            # 重新创建缩略图
            if create_thumbnail(file_path, thumbnail_filename):
                print(f"    [成功] 重新创建缩略图 {thumbnail_filename}")
                fixed_count += 1
            else:
                print(f"    [失败] 无法重新创建缩略图 {thumbnail_filename}")
    
    print(f"检查完成，共修复了 {fixed_count} 个缺失或损坏的缩略图。\n")
    return fixed_count


def main():
    """主函数"""
    print("=== 缩略图检查和修复工具 ===\n")
    
    # 确保缩略图目录存在
    if not os.path.exists(THUMBNAIL_DIR):
        os.makedirs(THUMBNAIL_DIR)
    print(f"确保缩略图目录存在: {THUMBNAIL_DIR}")
    
    # 建立数据库连接
    conn = setup_database_connection()
    
    # 修复thumbnail_filename为NULL的记录
    fix_null_thumbnails(conn)
    
    # 检查并修复缺失或损坏的缩略图
    check_and_fix_missing_or_corrupted_thumbnails(conn)
    
    # 关闭数据库连接
    conn.close()
    
    print("所有检查和修复操作已完成。")


if __name__ == "__main__":
    main()