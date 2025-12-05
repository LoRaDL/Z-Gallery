import os
import re
import datetime
from PIL import Image
import config

# --- 共享常量 (现已统一在 config.py 中管理) ---
THUMBNAIL_DIR = config.THUMBNAIL_DIR
THUMBNAIL_SIZE = config.THUMBNAIL_SIZE
THUMBNAIL_QUALITY = config.THUMBNAIL_QUALITY
MAX_SIMILAR_RESULTS = config.MAX_SIMILAR_RESULTS
DEFAULT_SEARCH_THRESHOLD = config.DEFAULT_SEARCH_THRESHOLD
IMAGES_PER_PAGE = config.IMAGES_PER_PAGE

# 确保缩略图目录存在（调用方也可再检查）
os.makedirs(THUMBNAIL_DIR, exist_ok=True)

# --- 共享的辅助函数 ---
def get_publication_date(full_path):
    """
    通过优先级策略获取发布日期。
    返回 (datetime对象, 来源字符串)
    优先级：EXIF -> 文件名解析 (YYYY[-_]MM[-_]DD 等) -> 文件系统 ctime
    """
    # 策略 1: EXIF
    try:
        with Image.open(full_path) as img:
            exif_data = getattr(img, "_getexif", lambda: None)()
            if exif_data:
                for tag_id in [36867, 306]:
                    if tag_id in exif_data:
                        date_str = exif_data[tag_id]
                        try:
                            return datetime.datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S'), "EXIF"
                        except Exception:
                            pass
    except Exception:
        pass

    # 策略 2: 从文件名解析 YYYY[-_]MM[-_]DD 或 YYYYMMDD
    filename = os.path.basename(full_path)
    match = re.match(r'^(?P<year>\d{4})[-_]? (?P<month>\d{2})[-_]? (?P<day>\d{2})'.replace(" ",""), filename)
    if match:
        try:
            parts = match.groupdict()
            return datetime.datetime(int(parts['year']), int(parts['month']), int(parts['day'])), "Filename"
        except Exception:
            pass

    # 策略 3: 使用文件创建时间 (ctime)
    try:
        ctime = os.path.getctime(full_path)
        return datetime.datetime.fromtimestamp(ctime), "File System (ctime)"
    except Exception:
        # 最后兜底，返回当前时间
        return datetime.datetime.now(), "Fallback"

def normalize_path(path):
    """统一规范化文件路径处理"""
    return path.replace('\\', '/')

def generate_timestamp_seed():
    """生成时间戳种子用于随机排序"""
    import time
    return int(time.time() * 1000)

def create_thumbnail(src_path, dest_path, size=THUMBNAIL_SIZE, quality=THUMBNAIL_QUALITY):
    """创建缩略图的标准函数"""
    try:
        with Image.open(src_path) as img:
            img.thumbnail(size)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(dest_path, "JPEG", quality=quality)
        return True
    except Exception as e:
        print(f"Failed to create thumbnail: {e}")
        return False

def calculate_phash(image_path):
    """计算图像的感知哈希值"""
    try:
        import imagehash
        with Image.open(image_path) as img:
            return str(imagehash.phash(img))
    except Exception as e:
        print(f"Failed to calculate phash: {e}")
        return None

def build_artwork_query(filters, sort_key=None, offset=None, limit=None):
    """
    统一的artworks查询构建器
    返回: (base_query, params)
    """
    where_clauses = []
    params = []

    # 图搜图处理
    if filters.get('similar_to'):
        try:
            similar_ids = [int(id) for id in filters['similar_to'].split(',') if id.strip()]
            if similar_ids:
                placeholders = ','.join(['?'] * len(similar_ids))
                where_clauses.append(f"id IN ({placeholders})")
                params.extend(similar_ids)
            else:
                where_clauses.append("1=0")
        except ValueError:
            where_clauses.append("1=0")
    else:
        # 艺术家、平台、分类筛选器
        for key in ['artist', 'source_platform', 'category']:
            if filters.get(key):
                where_clauses.append(f"{key} = ?")
                params.append(filters[key])

        # 评分筛选器
        rating_filter = filters.get('rating_filter')
        if rating_filter:
            if rating_filter == 'unrated':
                where_clauses.append("rating IS NULL")
            elif rating_filter.endswith('_plus'):
                try:
                    min_rating = int(rating_filter.split('_')[0])
                    where_clauses.append("rating >= ?")
                    params.append(min_rating)
                except (ValueError, IndexError):
                    pass
            else:
                try:
                    specific_rating = int(rating_filter)
                    if 1 <= specific_rating <= 10:
                        where_clauses.append("rating = ?")
                        params.append(specific_rating)
                except (ValueError, IndexError):
                    pass

        # 分类筛选器
        classification_filter = filters.get('classification_filter')
        if classification_filter:
            if classification_filter == 'unspecified':
                where_clauses.append("classification IS NULL")
            elif classification_filter in ['sfw', 'mature', 'nsfw']:
                where_clauses.append("classification = ?")
                params.append(classification_filter)

        # 文本搜索
        if filters.get('q'):
            search_term = f"%{filters['q']}%"
            where_clauses.append("(title LIKE ? OR artist LIKE ? OR tags LIKE ? OR ai_caption LIKE ? OR ai_tags LIKE ?)")
            params.extend([search_term] * 5)

    # 构建基础查询
    base_query = "FROM artworks"
    if where_clauses:
        base_query += " WHERE " + " AND ".join(where_clauses)

    # 添加排序
    if sort_key:
        sort_map = {
            'rating': 'rating DESC, publication_date DESC',
            'newest': 'publication_date DESC',
            'oldest': 'publication_date ASC',
            'latest_added': 'last_modified_date DESC'
        }
        order_by = sort_map.get(sort_key, 'publication_date DESC')
        if 'random' in sort_key or sort_key == 'random':
            order_by = get_random_sort_order(filters)
        base_query += f" ORDER BY {order_by}"

    # 添加分页
    if limit and offset is not None:
        base_query += f" LIMIT {limit} OFFSET {offset}"

    return base_query, params

def get_random_sort_order(filters):
    """基于种子的简单随机排序算法"""
    seed = filters.get('seed', generate_timestamp_seed())
    try:
        seed = int(seed)
        # 原始简单的随机算法公式
        return f"((id * {seed}) % 1000000)"
    except ValueError:
        return 'publication_date DESC'
