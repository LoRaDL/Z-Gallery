"""
统一的作品入库接口
供 add_artwork、gallery_manager、批量导入等所有入库路径使用
"""

import os
import sqlite3
import shutil
from datetime import datetime
from PIL import Image
import imagehash
import config
import utils


def add_artwork_to_database(
    file_path,
    metadata,
    move_file=True,
    db_connection=None,
    check_duplicate=True
):
    """
    统一的入库接口
    
    参数:
        file_path: str - 文件当前位置（必须存在）
        metadata: dict - 元数据字典
            必填: artist, platform
            可选: title, tags, description, classification, category, rating, 
                  publication_date, creation_date, source_url
        move_file: bool - 是否需要移动文件到最终位置
        db_connection: sqlite3.Connection - 可选的数据库连接
        check_duplicate: bool - 是否检查重复
    
    返回:
        (success: bool, artwork_id: int or None, error: str or None)
    """
    
    # 验证文件存在
    if not os.path.exists(file_path):
        return (False, None, f"File not found: {file_path}")
    
    # 验证必填字段
    if not metadata.get('artist') or not metadata.get('platform'):
        return (False, None, "Artist and Platform are required")
    
    # 数据库连接
    own_connection = False
    if db_connection is None:
        db_connection = sqlite3.connect(config.DB_FILE)
        own_connection = True
    
    cursor = db_connection.cursor()
    
    try:
        # 检查重复
        if check_duplicate:
            # 如果标题为空，跳过重复检查，直接入库
            if not metadata.get('title'):
                pass  # 标题为空，不进行重复检查
            else:
                cursor.execute(
                    "SELECT id, phash FROM artworks WHERE source_platform = ? AND artist = ? AND title = ?",
                    (metadata['platform'], metadata['artist'], metadata['title'])
                )
                existing = cursor.fetchone()
                if existing:
                    existing_id, existing_phash = existing
                    
                    # 计算当前图片的phash
                    current_phash = _calculate_phash(file_path)
                    
                    # 如果phash相同，说明是真正的重复
                    if existing_phash and current_phash and existing_phash == current_phash:
                        return (False, None, f"Duplicate: {metadata['title']}")
                    
                    # 如果phash不同，说明是不同的图片但标题相同，进行改名
                    if current_phash != existing_phash:
                        original_title = metadata['title']
                        counter = 2
                        
                        # 寻找可用的标题
                        while True:
                            new_title = f"{original_title} ({counter})"
                            cursor.execute(
                                "SELECT id FROM artworks WHERE source_platform = ? AND artist = ? AND title = ?",
                                (metadata['platform'], metadata['artist'], new_title)
                            )
                            if not cursor.fetchone():
                                metadata['title'] = new_title
                                print(f"  📝 标题重复但图片不同，重命名为: {new_title}")
                                break
                            counter += 1
                            
                            # 防止无限循环
                            if counter > 100:
                                metadata['title'] = f"{original_title} ({datetime.now().strftime('%Y%m%d_%H%M%S')})"
                                break
        
        # 移动文件（如果需要）
        if move_file:
            target_dir = os.path.join(
                config.IMAGES_ROOT_FOLDER,
                metadata['platform'],
                metadata['artist']
            )
            os.makedirs(target_dir, exist_ok=True)
            
            filename = os.path.basename(file_path)
            final_path = os.path.join(target_dir, filename)
            
            # 处理文件名冲突
            if os.path.exists(final_path):
                name, ext = os.path.splitext(filename)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{name}_{timestamp}{ext}"
                final_path = os.path.join(target_dir, filename)
            
            shutil.move(file_path, final_path)
            file_path = final_path
        
        # 规范化路径
        normalized_path = file_path.replace('\\', '/')
        filename = os.path.basename(file_path)
        
        # 准备日期
        dates = _prepare_dates(metadata, file_path)
        
        # 计算phash
        phash_value = _calculate_phash(file_path)
        
        # 插入数据库
        cursor.execute("""
            INSERT INTO artworks (
                file_path, file_name, title, artist, source_platform,
                tags, description, rating, category, classification,
                creation_date, publication_date, last_modified_date,
                phash, source_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            normalized_path,
            filename,
            metadata.get('title'),
            metadata['artist'],
            metadata['platform'],
            metadata.get('tags', ''),
            metadata.get('description', ''),
            metadata.get('rating'),
            metadata.get('category', 'fanart_non_comic'),
            metadata.get('classification'),
            dates['creation_date'],
            dates['publication_date'],
            dates['last_modified_date'],
            phash_value,
            metadata.get('source_url')
        ))
        
        new_id = cursor.lastrowid
        
        # 生成缩略图
        thumbnail_filename = _create_thumbnail(file_path, new_id)
        
        # 更新thumbnail_filename
        cursor.execute(
            "UPDATE artworks SET thumbnail_filename = ? WHERE id = ?",
            (thumbnail_filename, new_id)
        )
        
        if own_connection:
            db_connection.commit()
        
        return (True, new_id, None)
        
    except Exception as e:
        if own_connection:
            db_connection.rollback()
        return (False, None, str(e))
    
    finally:
        if own_connection:
            db_connection.close()


def _prepare_dates(metadata, file_path):
    """准备日期字段"""
    
    # creation_date
    if metadata.get('creation_date'):
        creation_date = _parse_date(metadata['creation_date'])
    else:
        creation_date = datetime.fromtimestamp(os.path.getctime(file_path))
    
    # publication_date
    if metadata.get('publication_date'):
        publication_date = _parse_date(metadata['publication_date'])
    else:
        # 尝试EXIF
        publication_date = _extract_exif_date(file_path)
        if not publication_date:
            publication_date = creation_date
    
    # last_modified_date
    last_modified_date = datetime.now()
    
    return {
        'creation_date': creation_date,
        'publication_date': publication_date,
        'last_modified_date': last_modified_date
    }


def _parse_date(date_input):
    """灵活解析日期"""
    if isinstance(date_input, datetime):
        return date_input
    
    if isinstance(date_input, str):
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%Y:%m:%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%SZ',
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_input, fmt)
            except ValueError:
                continue
    
    return None


def _extract_exif_date(file_path):
    """从EXIF提取日期"""
    try:
        with Image.open(file_path) as img:
            exif_data = img._getexif()
            if exif_data:
                for tag_id in [36867, 306]:
                    if tag_id in exif_data:
                        date_str = exif_data[tag_id]
                        parsed = _parse_date(date_str)
                        if parsed:
                            return parsed
    except Exception:
        pass
    return None


def _calculate_phash(file_path):
    """计算感知哈希"""
    try:
        with Image.open(file_path) as img:
            return str(imagehash.phash(img))
    except Exception:
        return None


def _create_thumbnail(file_path, artwork_id):
    """生成缩略图"""
    thumbnail_filename = f"{artwork_id:06d}.jpg"
    thumb_path = os.path.join(utils.THUMBNAIL_DIR, thumbnail_filename)
    
    with Image.open(file_path) as img:
        img.thumbnail(utils.THUMBNAIL_SIZE)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.save(thumb_path, "JPEG", quality=85)
    
    return thumbnail_filename
