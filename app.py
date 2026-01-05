import sqlite3
import math
import time
import json
import datetime
import os
import re
import traceback
import sys
import subprocess
import shutil
from flask import Flask, render_template, request, g, redirect, url_for, abort, send_file, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image
import imagehash
import config
import utils
import logger
import artwork_importer

# --- App Configuration ---
app = Flask(__name__)
DATABASE = config.DB_FILE
COMICS_DATABASE = "zootopia_comics.db"
IMAGES_PER_PAGE = config.IMAGES_PER_PAGE

# --- Database Connection Handling ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def get_comics_db():
    db = getattr(g, '_comics_database', None)
    if db is None:
        db = g._comics_database = sqlite3.connect(COMICS_DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_comics_connection(exception):
    db = getattr(g, '_comics_database', None)
    if db is not None:
        db.close()

@app.context_processor
def utility_processor():
    def generate_url_params(key_to_change, new_value):
        """
        Generates a dictionary of URL parameters based on the current request's
        arguments, but with one key's value changed or removed.
        """
        # Start with a mutable copy of the current request arguments
        params = request.args.to_dict()

        # Update the value for the given key
        params[key_to_change] = new_value

        # If the new value is None, it means we want to remove this filter
        if new_value is None:
            params.pop(key_to_change, None)

        return params

    return dict(generate_url_params=generate_url_params, config=config)


# --- New Route: Rate Artwork ---
@app.route('/rate/<int:artwork_id>', methods=['POST'])
def rate_artwork(artwork_id):
    db = get_db()
    rating = request.form.get('rating', type=int)
    
    if not (1 <= rating <= 10):
        abort(400)
    
    # 更新数据库中的评分
    db.execute('UPDATE artworks SET rating = ? WHERE id = ?', (rating, artwork_id))
    db.commit()
    
    # 检查是否是AJAX请求 (通过X-Requested-With头部)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    # 始终返回JSON响应，评分后的页面逻辑由前端JS处理
    if is_ajax:
        return jsonify({'success': True, 'message': 'Rating updated successfully.', 'new_rating': rating})
    else:
        # 对于非AJAX请求（无JS设备），我们需要重定向回slide_view页面
        # 但要保留当前的筛选和排序参数
        if request.referrer and 'slide_view' in request.referrer:
            # 从referrer中提取当前作品的ID和参数
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(request.referrer)
            referrer_params = parse_qs(parsed_url.query)
            # 将参数列表转换为单个值
            referrer_params_single = {k: v[0] if isinstance(v, list) and len(v) > 0 else v for k, v in referrer_params.items()}
            current_id = referrer_params_single.get('id', None)
            
            # 获取下一张图片的数据
            next_artwork_response = get_navigation_image(current_id, referrer_params_single, 'next')
            next_artwork_data = next_artwork_response.get_json() if hasattr(next_artwork_response, 'get_json') else None
            
            # 构建重定向URL
            if isinstance(next_artwork_data, dict) and next_artwork_data.get('success'):
                # 保留其他筛选参数，只更新ID
                new_params = referrer_params_single.copy()
                new_params['id'] = next_artwork_data.get('artwork_id')
                # 移除'rating'筛选器
                new_params.pop('rating', None)
                query_string = '&'.join([f"{key}={value}" for key, value in new_params.items() if value is not None])
                return redirect(url_for('slide_view') + '?' + query_string + '#image-top')
            else:
                # 如果无法获取下一张图片，就留在当前页面
                return redirect(request.referrer + '#image-top')
        elif request.referrer:
            # 对于其他页面的评分，重定向回来源页面
            from urllib.parse import urlparse, parse_qs, urlencode
            parsed_url = urlparse(request.referrer)
            referrer_params = parse_qs(parsed_url.query)
            # 转换参数格式
            referrer_params_single = {k: v[0] if isinstance(v, list) and len(v) > 0 else v for k, v in referrer_params.items()}
            query_string = urlencode(referrer_params_single, doseq=True)
            final_url = f"{parsed_url.path}?{query_string}#artwork-{artwork_id}" if query_string else f"{parsed_url.path}#artwork-{artwork_id}"
            return redirect(final_url)
        else:
            return redirect(url_for('gallery') + '#artwork-' + str(artwork_id))


# --- Helper function ---
def get_distinct_values(column_name):
    db = get_db()
    query = f"SELECT DISTINCT {column_name} FROM artworks WHERE {column_name} IS NOT NULL ORDER BY {column_name}"
    return [row[column_name] for row in db.execute(query).fetchall()]

# --- Helper for the new page ---
def is_duplicate(platform, artist, title):
    """
    Checks if a specific platform + artist + title combination already exists.
    """
    db = get_db()
    # 核心修正: 在 SQL 查询中添加了 "AND title = ?"
    row = db.execute(
        "SELECT id FROM artworks WHERE source_platform = ? AND artist = ? AND title = ?",
        (platform, artist, title)
    ).fetchone()
    return row is not None

# --- Routes ---
@app.route('/')
@logger.performance_monitor('gallery_page')
def gallery():
    db = get_db()
    
    filters = request.args.to_dict()
    sort_key = filters.get('sort', 'random') # 默认进入随机模式

    # --- 使用新的统一查询构建器 ---
    base_query, params = utils.build_artwork_query(filters, sort_key)

    # --- 处理种子生成重定向 ---
    if 'random' in sort_key and 'seed' not in filters:
        # 使用工具函数生成种子
        seed = utils.generate_timestamp_seed()
        filters['seed'] = seed
        return redirect(url_for('gallery', **filters))

    # --- 添加分页 ---
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * IMAGES_PER_PAGE

    # --- 执行查询 ---
    count_row = db.execute("SELECT COUNT(id) " + base_query, params).fetchone()
    total_artworks = count_row[0] if count_row else 0
    total_pages = math.ceil(total_artworks / IMAGES_PER_PAGE) if total_artworks > 0 else 1

    # 只有在需要时才添加LIMIT子句
    main_query = "SELECT * " + base_query
    if IMAGES_PER_PAGE:
        main_query += f" LIMIT {IMAGES_PER_PAGE} OFFSET {offset}"

    artworks = db.execute(main_query, params).fetchall()

    # --- 应用瀑布流填充逻辑 ---
    # 获取宽高比数据
    aspect_ratios = {}
    try:
        ar_db = get_aspect_ratios_db()
        artwork_ids = [art['id'] for art in artworks]
        if artwork_ids:
            placeholders = ','.join('?' * len(artwork_ids))
            ar_query = f"SELECT artwork_id, aspect_ratio FROM aspect_ratios WHERE artwork_id IN ({placeholders})"
            ar_results = ar_db.execute(ar_query, artwork_ids).fetchall()
            aspect_ratios = {row['artwork_id']: row['aspect_ratio'] for row in ar_results}
    except Exception:
        # 如果宽高比数据库不存在或出错，使用空字典
        pass
    
    # 计算瀑布流布局：为每张卡片分配列号（固定4列，前端响应式调整）
    columns = 4
    column_heights = [0] * columns  # 记录每列的累计高度
    artwork_columns = []  # 记录每张卡片应该放在哪一列
    
    for art in artworks:
        # 获取宽高比，如果没有则使用默认值1.0
        aspect_ratio = aspect_ratios.get(art['id'], 1.0)
        # 计算卡片高度（假设宽度为1单位）
        card_height = 1.0 / aspect_ratio + 0.3  # 0.3是卡片信息区域的估算高度
        
        # 找到当前最短的列
        min_col = column_heights.index(min(column_heights))
        artwork_columns.append(min_col)
        
        # 更新该列的高度
        column_heights[min_col] += card_height

    return render_template('gallery.html', artworks=artworks, page=page, total_pages=total_pages,
                           total_artworks=total_artworks, current_sort=sort_key, current_filters=filters,
                           columns=columns, aspect_ratios=aspect_ratios, artwork_columns=artwork_columns)

def get_aspect_ratios_db():
    """获取宽高比数据库连接"""
    db = getattr(g, '_aspect_ratios_db', None)
    if db is None:
        db = g._aspect_ratios_db = sqlite3.connect('aspect_ratios.db')
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_aspect_ratios_connection(exception):
    db = getattr(g, '_aspect_ratios_db', None)
    if db is not None:
        db.close()

@app.route('/image-wall')
def image_wall():
    db = get_db()
    
    filters = request.args.to_dict()
    sort_key = filters.get('sort', 'random')
    columns = request.args.get('columns', 4, type=int)  # 默认4列
    
    
    # 使用统一查询构建器
    base_query, params = utils.build_artwork_query(filters, sort_key)
    
    # 处理种子生成重定向
    if 'random' in sort_key and 'seed' not in filters:
        seed = utils.generate_timestamp_seed()
        filters['seed'] = seed
        filters['columns'] = columns
        return redirect(url_for('image_wall', **filters))
    
    # 获取所有图片（无分页）
    main_query = "SELECT * " + base_query
    artworks = db.execute(main_query, params).fetchall()
    
    # 获取宽高比数据
    aspect_ratios = {}
    try:
        ar_db = get_aspect_ratios_db()
        artwork_ids = [art['id'] for art in artworks]
        if artwork_ids:
            placeholders = ','.join('?' * len(artwork_ids))
            ar_query = f"SELECT artwork_id, aspect_ratio FROM aspect_ratios WHERE artwork_id IN ({placeholders})"
            ar_results = ar_db.execute(ar_query, artwork_ids).fetchall()
            aspect_ratios = {row['artwork_id']: row['aspect_ratio'] for row in ar_results}
    except Exception:
        # 如果宽高比数据库不存在或出错，使用空字典
        pass
    
    # 计算瀑布流布局：为每张卡片分配列号
    column_heights = [0] * columns  # 记录每列的累计高度
    artwork_columns = []  # 记录每张卡片应该放在哪一列
    
    for art in artworks:
        # 获取宽高比，如果没有则使用默认值1.0
        aspect_ratio = aspect_ratios.get(art['id'], 1.0)
        # 计算卡片高度（假设宽度为1单位）
        card_height = 1.0 / aspect_ratio + 0.3  # 0.3是卡片信息区域的估算高度
        
        # 找到当前最短的列
        min_col = column_heights.index(min(column_heights))
        artwork_columns.append(min_col)
        
        # 更新该列的高度
        column_heights[min_col] += card_height
    
    total_artworks = len(artworks)
    
    return render_template('image_wall.html', 
                          artworks=artworks, 
                          total_artworks=total_artworks,
                          columns=columns,
                          aspect_ratios=aspect_ratios,
                          artwork_columns=artwork_columns,
                          current_sort=sort_key, 
                          current_filters=filters)

@app.route('/categories')
def categories_list():
    all_artists = get_distinct_values('artist')
    all_platforms = get_distinct_values('source_platform')
    # Pass empty filters so the layout doesn't break
    return render_template('categories.html', all_artists=all_artists, all_platforms=all_platforms, current_filters={})


@app.route('/statistics')
def statistics():
    return render_template('statistics.html', current_filters={})


@app.route('/artist-ranking')
def artist_ranking_noscript():
    db = get_db()
    
    # 获取每个作者的综合评分，综合考虑平均分和作品数量
    query = """
    SELECT 
        artist, 
        ROUND(AVG(rating - 5), 2) as average_rating,
        COUNT(*) as work_count
    FROM artworks 
    WHERE rating IS NOT NULL
    GROUP BY artist 
    ORDER BY average_rating DESC
    """
    rows = db.execute(query).fetchall()
    
    # 计算综合评分：(平均分-5) * log(作品数量 + 1)
    import math
    artist_ranking = []
    for row in rows:
        weighted_score = float(row['average_rating'] * math.log(row['work_count'] + 1))
        artist_ranking.append({
            'name': row['artist'] or 'Unknown',
            'weighted_score': weighted_score,
            'total_works': row['work_count'],
            'average_rating': float(row['average_rating'])
        })
    
    # 按综合评分排序
    artist_ranking.sort(key=lambda x: x['weighted_score'], reverse=True)
    
    return render_template('artist_ranking_noscript.html', artist_ranking=artist_ranking, current_filters={})


@app.route('/api/statistics/<stat_type>')
def api_statistics(stat_type):
    db = get_db()
    
    if stat_type == 'rating':
        # 获取每个评分的作品数量，不包括未评分作品
        query = """
        SELECT 
            rating as rating_value, 
            COUNT(*) as count 
        FROM artworks 
        WHERE rating IS NOT NULL
        GROUP BY rating_value 
        ORDER BY rating_value DESC
        """
        rows = db.execute(query).fetchall()
        # 转换为图表需要的格式
        data = [{'label': f'{row["rating_value"]}', 'value': row['count']} for row in rows]
        
    elif stat_type == 'artist-works':
        # 获取每个作者的作品数量
        query = """
        SELECT 
            artist, 
            COUNT(*) as count 
        FROM artworks 
        GROUP BY artist 
        ORDER BY count DESC
        """
        rows = db.execute(query).fetchall()
        data = [{'label': row['artist'] or 'Unknown', 'value': row['count']} for row in rows]
        
    elif stat_type == 'artist-stars':
        # 获取每个作者获得的星星总数（评分-5的总和）
        query = """
        SELECT 
            artist, 
            SUM(rating - 5) as total_stars 
        FROM artworks 
        WHERE rating IS NOT NULL
        GROUP BY artist 
        ORDER BY total_stars DESC
        """
        rows = db.execute(query).fetchall()
        data = [{'label': row['artist'] or 'Unknown', 'value': row['total_stars']} for row in rows]
        
    elif stat_type == 'artist-average':
        # 获取每个作者的平均分（评分-5的平均值），不包括未评分作品
        query = """
        SELECT 
            artist, 
            ROUND(AVG(rating - 5), 2) as average_rating
        FROM artworks 
        WHERE rating IS NOT NULL
        GROUP BY artist 
        ORDER BY average_rating DESC
        """
        rows = db.execute(query).fetchall()
        data = [{'label': row['artist'] or 'Unknown', 'value': float(row['average_rating'])} for row in rows]
        
    elif stat_type == 'artist-weighted':
        # 获取每个作者的综合评分，综合考虑平均分和作品数量
        query = """
        SELECT 
            artist, 
            ROUND(AVG(rating - 5), 2) as average_rating,
            COUNT(*) as work_count
        FROM artworks 
        WHERE rating IS NOT NULL
        GROUP BY artist 
        ORDER BY average_rating DESC
        """
        rows = db.execute(query).fetchall()
        # 计算综合评分：(平均分-5) * log(作品数量 + 1)
        import math
        data = [{'label': row['artist'] or 'Unknown', 'value': float(row['average_rating'] * math.log(row['work_count'] + 1))} for row in rows]
        # 按综合评分排序
        data.sort(key=lambda x: x['value'], reverse=True)
        
    else:
        return jsonify({'success': False, 'error': 'Invalid statistic type'}), 400
    
    return jsonify({'success': True, 'data': data})





@app.route('/artwork/<int:artwork_id>')
def artwork_detail(artwork_id):
    db = get_db()
    artwork = db.execute("SELECT * FROM artworks WHERE id = ?", (artwork_id,)).fetchone()
    if artwork is None:
        abort(404)
    
    # 查询同系列的图片
    series_artworks = []
    if artwork['title'] and artwork['artist']:
        # 检查当前标题是否包含序号格式 (1), (2) 等
        if re.search(r'\s*\(\d+\)$', artwork['title']):
            # 提取基础标题（去掉序号部分）
            title_pattern = re.sub(r'\s*\(\d+\)$', '', artwork['title'])
            
            # 查找所有以相同基础标题开头且同作者的作品
            query = """
            SELECT id, file_name, title FROM artworks 
            WHERE title LIKE ? AND artist = ? AND id != ?
            ORDER BY title
            """
            candidates = db.execute(query, (f'{title_pattern}%', artwork['artist'], artwork_id)).fetchall()
            
            # 在Python中过滤，只保留真正的系列作品（带序号的）
            series_pattern = re.compile(f'^{re.escape(title_pattern)}\\s*\\(\\d+\\)$')
            series_artworks = [
                artwork for artwork in candidates 
                if series_pattern.match(artwork['title'])
            ]
    
    return render_template('artwork_detail.html', artwork=artwork, series_artworks=series_artworks, current_filters={})

@app.route('/image_proxy/<int:artwork_id>')
def image_proxy(artwork_id):
    db = get_db()
    artwork = db.execute("SELECT file_path FROM artworks WHERE id = ?", (artwork_id,)).fetchone()
    if artwork and os.path.exists(artwork['file_path']):
        return send_file(artwork['file_path'])
    else:
        abort(404)

# --- NEW: Route to handle classification change ---
@app.route('/classify/<int:artwork_id>', methods=['POST'])
def classify_artwork(artwork_id):
    db = get_db()
    classification = request.form.get('classification')
    
    final_classification = None
    if classification in ['sfw', 'mature', 'nsfw']:
        final_classification = classification
        db.execute(
            "UPDATE artworks SET classification = ? WHERE id = ?",
            (classification, artwork_id)
        )
    elif classification == 'unspecified':
        # final_classification 保持为 None
        db.execute(
            "UPDATE artworks SET classification = NULL WHERE id = ?",
            (artwork_id,)
        )
    
    db.commit()

    # 如果是 AJAX 请求 (来自JS), 返回 JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'new_classification': final_classification})
    
    # 如果是普通表单提交 (来自电子书), 重定向回详情页
    # 添加 #page-top 确保页面从顶部开始显示
    return redirect(url_for('artwork_detail', artwork_id=artwork_id) + "#page-top")

@app.route('/set_category/<int:artwork_id>', methods=['POST'])
def set_category(artwork_id):
    db = get_db()
    category = request.form.get('category')

    # 验证传入的值是否合法
    valid_categories = ['fanart_comic', 'fanart_non_comic', 'real_photo', 'other']
    if category in valid_categories:
        db.execute(
            "UPDATE artworks SET category = ? WHERE id = ?",
            (category, artwork_id)
        )
        db.commit()

        # 如果是 AJAX 请求, 返回 JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'new_category': category})
        
        # 对于无JS的设备，重定向回详情页
        return redirect(url_for('artwork_detail', artwork_id=artwork_id) + "#page-top")
    else:
        # 如果是 AJAX 请求, 返回错误 JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Invalid category value'}), 400
        
        # 对于无JS的设备，重定向回详情页
        return redirect(url_for('artwork_detail', artwork_id=artwork_id) + "#page-top")

# --- API Endpoints for Autocomplete ---
@app.route('/api/artists')
def api_artists():
    return jsonify(get_distinct_values('artist'))

@app.route('/api/platforms')
def api_platforms():
    return jsonify(get_distinct_values('source_platform'))

# --- Page for Adding New Artwork ---
@app.route('/add')
def add_artwork_page():
    return render_template('add_artwork.html', current_filters={})

# --- API Endpoint to Handle Artwork Upload ---
@app.route('/api/add_artwork', methods=['POST'])
def api_add_artwork():
    source_path = None
    
    # --- 1. 获取文件 ---
    temp_filename = request.form.get('temp_filename')
    if temp_filename:
        # 方式A: 文件来自 URL Fetch
        source_path = os.path.join('temp_uploads', temp_filename)
        if not os.path.exists(source_path):
            return jsonify({'success': False, 'error': f"Temporary file '{temp_filename}' not found."}), 400
    
    elif 'artwork_file' in request.files:
        # 方式B: 文件来自用户手动上传
        file = request.files['artwork_file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected.'}), 400
        
        original_filename = secure_filename(file.filename)
        source_path = os.path.join('temp_uploads', original_filename)
        file.save(source_path)
    else:
        return jsonify({'success': False, 'error': 'No file part provided.'}), 400

    # --- 2. 准备元数据 ---
    metadata = {
        'artist': request.form.get('artist'),
        'platform': request.form.get('platform'),
        'title': request.form.get('title'),
        'tags': request.form.get('tags'),
        'description': request.form.get('description'),
        'rating': request.form.get('rating', type=int) if request.form.get('rating') else None,
        'category': request.form.get('category'),
        'classification': request.form.get('classification'),
        'publication_date': request.form.get('publication_date'),
        'source_url': request.form.get('source_url')
    }
    
    # 验证必填字段
    if not metadata['artist'] or not metadata['platform']:
        if os.path.exists(source_path):
            os.remove(source_path)
        return jsonify({'success': False, 'error': 'Artist and Platform are required.'}), 400

    # --- 3. 调用统一入库接口 ---
    success, artwork_id, error = artwork_importer.add_artwork_to_database(
        file_path=source_path,
        metadata=metadata,
        move_file=True,
        db_connection=get_db(),
        check_duplicate=True
    )
    
    if success:
        get_db().commit()
        return jsonify({'success': True, 'message': 'Artwork added successfully!', 'artwork_id': artwork_id})
    else:
        # 入库失败，清理文件
        if os.path.exists(source_path):
            os.remove(source_path)
        
        # 根据错误类型返回不同的状态码
        status_code = 409 if "Duplicate" in error else 500
        return jsonify({'success': False, 'error': error}), status_code

@app.errorhandler(404)
def page_not_found(error):
    """Renders the custom 404 error page."""
    return render_template('404.html', current_filters={}), 404

# --- 新的API端点: 只返回相似图片ID ---
@app.route('/api/get_similar_ids', methods=['POST'])
def api_get_similar_ids():
    if 'search_file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['search_file']
    # 从表单获取阈值，如果未提供则默认为10
    threshold = request.form.get('threshold', 10, type=int)
    
    try:
        query_image = Image.open(file.stream)
        query_hash = imagehash.phash(query_image)
        
        db = get_db()
        cursor = db.execute("SELECT id, phash FROM artworks WHERE phash IS NOT NULL")
        all_hashes = cursor.fetchall()

        results = []
        for row in all_hashes:
            try:
                db_hash = imagehash.hex_to_hash(row['phash'])
                distance = query_hash - db_hash
                # 使用变量阈值进行比较
                if distance < threshold: # 只考虑满足阈值的
                    results.append({'id': row['id'], 'distance': distance})
            except Exception:
                continue
            
        results.sort(key=lambda x: x['distance'])
        result_ids = [str(res['id']) for res in results][:50] # 最多返回50个结果

        return jsonify({'success': True, 'ids': ",".join(result_ids)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# --- 新的API端点: 删除图片 ---
@app.route('/api/delete_artwork/<int:artwork_id>', methods=['POST'])
def api_delete_artwork(artwork_id):
    TRASH_DIR = "./trash"
    if not os.path.exists(TRASH_DIR):
        os.makedirs(TRASH_DIR)
        
    db = get_db()
    artwork = db.execute("SELECT file_path, thumbnail_filename FROM artworks WHERE id = ?", (artwork_id,)).fetchone()

    if not artwork:
        return jsonify({'success': False, 'error': 'Artwork not found'}), 404

    original_path = artwork['file_path']
    thumb_path = os.path.join(utils.THUMBNAIL_DIR, artwork['thumbnail_filename']) if artwork['thumbnail_filename'] else None

    try:
        # 移动原图
        if os.path.exists(original_path):
            shutil.move(original_path, os.path.join(TRASH_DIR, os.path.basename(original_path)))
        
        # 删除缩略图 (不移动)
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)
            
        # 删除数据库记录
        db.execute("DELETE FROM artworks WHERE id = ?", (artwork_id,))
        db.commit()
        
        return jsonify({'success': True, 'message': 'Artwork moved to trash.'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# --- 新的API端点: 根据ID获取相似图片ID ---
@app.route('/api/get_similar_ids_by_id/<int:artwork_id>')
def api_get_similar_ids_by_id(artwork_id):
    db = get_db()
    # 从URL参数获取阈值，如果未提供则默认为10
    threshold = request.args.get('threshold', 10, type=int)
    
    # 1. 获取源图片的phash
    source_artwork = db.execute("SELECT phash FROM artworks WHERE id = ?", (artwork_id,)).fetchone()
    if not source_artwork or not source_artwork['phash']:
        return jsonify({'success': False, 'error': 'Source image has no hash or does not exist.'}), 404
        
    try:
        query_hash = imagehash.hex_to_hash(source_artwork['phash'])
        
        # 2. 从数据库获取所有图片的phash
        all_hashes = db.execute("SELECT id, phash FROM artworks WHERE phash IS NOT NULL").fetchall()

        # 3. 计算哈希差异
        results = []
        for row in all_hashes:
            try:
                db_hash = imagehash.hex_to_hash(row['phash'])
                distance = query_hash - db_hash
                # 使用变量阈值进行比较
                if distance < threshold:
                    results.append({'id': row['id'], 'distance': distance})
            except Exception:
                continue
            
        # 4. 排序并返回ID
        results.sort(key=lambda x: x['distance'])
        result_ids = [str(res['id']) for res in results][:50]

        return jsonify({'success': True, 'ids': ",".join(result_ids)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# --- 新增路由：为不支持JS的设备提供查找相似功能 ---
@app.route('/find_similar/<int:artwork_id>')
def find_similar(artwork_id):
    # 调用现有的API函数获取相似图片ID
    response = api_get_similar_ids_by_id(artwork_id)
    
    # 检查响应是否成功
    if response.status_code == 200:
        result = json.loads(response.get_data(as_text=True))
        if result.get('success'):
            # 构建查询参数
            similar_ids = result.get('ids', '')
            threshold = request.args.get('threshold', 10, type=int)
            search_params = {
                'similar_to': similar_ids,
                'threshold': threshold
            }
            
            # 重定向到主页并传递查询参数
            return redirect(url_for('gallery', **search_params))
    
    # 如果查找失败，重定向回详情页
    return redirect(url_for('artwork_detail', artwork_id=artwork_id))

# --- 重构: 提取元数据的API端点 ---
@app.route('/api/fetch_metadata', methods=['POST'])
def api_fetch_metadata():
    data = request.get_json()
    url = data.get('url')
    proxy = data.get('proxy')  # 获取代理参数
    if not url:
        return jsonify({'success': False, 'error': 'URL is required.'}), 400

    # --- 核心: 将所有复杂工作委托给外部脚本 ---
    # sys.executable 确保我们使用的是与运行Flask应用相同的Python解释器
    command = [sys.executable, 'metadata_fetcher.py', url]
    if proxy:
        command.extend(['--proxy', proxy])  # 如果有代理参数，传递给脚本

    try:
        # 调用脚本，并等待其完成
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,        # 确保输出是字符串
            check=True,       # 如果脚本以非零状态码退出，则抛出异常
            timeout=90        # 给整个流程更长的超时时间
        )

        # 解析脚本返回的、干净的JSON
        response_data = json.loads(result.stdout)

        # 核心修正: 确保返回 temp_path
        return jsonify({'success': True, **response_data, 'temp_path': response_data.get('temp_path')})

    except Exception as e:
        # 如果脚本失败，将其错误信息转发给前端
        err_msg = e.stderr.strip() if hasattr(e, 'stderr') else str(e)
        return jsonify({'success': False, 'error': f"Failed to process URL: {err_msg}"}), 400

# --- 新增: 安全地提供临时文件夹中的图片 ---
@app.route('/temp_image/<filename>')
def temp_image(filename):
    # 安全性: 确保文件名不包含路径遍历字符 '..'
    if '..' in filename or filename.startswith('/'):
        abort(404)
    return send_file(os.path.join('temp_uploads', filename))

# --- 新的API端点: 更新作品字段 ---
@app.route('/api/update_artwork_field/<int:artwork_id>', methods=['POST'])
def api_update_artwork_field(artwork_id):
    db = get_db()
    
    # 支持两种数据格式：JSON和表单数据
    if request.is_json:
        data = request.get_json()
        field_to_update = data.get('field')
        new_value = data.get('value')
    else:
        # 表单数据
        field_to_update = request.form.get('field')
        new_value = request.form.get('value')

    if not field_to_update or new_value is None:
        return jsonify({'success': False, 'error': 'Field and value are required.'}), 400

    # 安全性: 创建一个允许被修改的字段白名单
    allowed_fields = ['title', 'artist', 'source_platform', 'description', 'tags', 'publication_date', 'ai_caption', 'ai_tags']
    if field_to_update not in allowed_fields:
        return jsonify({'success': False, 'error': 'Invalid field specified.'}), 400

    try:
        # 动态构建SQL查询
        query = f"UPDATE artworks SET {field_to_update} = ? WHERE id = ?"
        db.execute(query, (new_value, artwork_id))
        db.commit()
        
        # 根据请求类型返回不同的响应
        if request.is_json:
            return jsonify({'success': True, 'message': f'{field_to_update.capitalize()} updated successfully.'})
        else:
            # 表单提交后重定向回详情页
            return redirect(url_for('artwork_detail', artwork_id=artwork_id))
            
    except sqlite3.Error as e:
        db.rollback()
        if request.is_json:
            return jsonify({'success': False, 'error': f'Database error: {e}'}), 500
        else:
            # 表单提交错误时也重定向，但可以添加flash消息
            return redirect(url_for('artwork_detail', artwork_id=artwork_id))


# --- Slide View Routes ---
@app.route('/slide_view')
def slide_view():
    db = get_db()

    filters = request.args.to_dict()

    # 如果没有指定排序方式，默认使用随机排序
    if 'sort' not in filters:
        filters['sort'] = 'random'

    # 如果是随机模式但没有种子，生成一个种子并重定向
    if filters.get('sort') == 'random' and 'seed' not in filters:
        seed = utils.generate_timestamp_seed()
        filters['seed'] = seed
        return redirect(url_for('slide_view', **filters))

    current_id = filters.get('id')

    # 使用统一的查询构建器
    base_query, params = utils.build_artwork_query(filters, filters.get('sort', 'random'))

    # 获取符合条件的所有ID用于导航
    all_ids_query = f"SELECT id {base_query}"
    all_ids = [row[0] for row in db.execute(all_ids_query, params).fetchall()]

    total_images = len(all_ids)

    # 确定当前图片
    artwork = None
    current_position = 0
    image_aspect_ratio = None

    if total_images > 0:
        if current_id:
            # 查找指定ID的图片
            try:
                current_id = int(current_id)
                artwork = db.execute("SELECT * FROM artworks WHERE id = ?", (current_id,)).fetchone()
                if artwork:
                    current_position = all_ids.index(current_id) + 1
                else:
                    # 如果指定的ID不存在，使用第一个图片
                    artwork_query = f"SELECT * {base_query} LIMIT 1"
                    artwork = db.execute(artwork_query, params).fetchone()
                    if artwork:
                        current_position = 1
            except ValueError:
                # 如果ID不是整数，使用第一个图片
                artwork_query = f"SELECT * {base_query} LIMIT 1"
                artwork = db.execute(artwork_query, params).fetchone()
                if artwork:
                    current_position = 1
        else:
            # 如果没有指定ID，使用第一个图片
            artwork_query = f"SELECT * {base_query} LIMIT 1"
            artwork = db.execute(artwork_query, params).fetchone()
            if artwork:
                current_position = 1

    # 计算图片的宽高比
    if artwork and artwork['file_path'] and os.path.exists(artwork['file_path']):
        try:
            with Image.open(artwork['file_path']) as img:
                width, height = img.size
                # 计算宽高比 (宽度/高度)
                image_aspect_ratio = width / height if height > 0 else 1.0
        except Exception:
            # 如果无法获取图片尺寸，使用默认值
            image_aspect_ratio = 1.0

    # 为模板准备没有ID的过滤器参数
    current_filters_without_id = filters.copy()
    if 'id' in current_filters_without_id:
        del current_filters_without_id['id']

    # 计算上一张和下一张图片的ID
    prev_artwork_id = None
    next_artwork_id = None
    if artwork:
        current_index = all_ids.index(artwork['id'])
        if current_index > 0:
            prev_artwork_id = all_ids[current_index - 1]
        if current_index < len(all_ids) - 1:
            next_artwork_id = all_ids[current_index + 1]

    return render_template('slide_view.html',
                          artwork=artwork,
                          current_filters=filters,
                          current_filters_without_id=current_filters_without_id,
                          current_position=current_position,
                          total_images=total_images,
                          prev_artwork_id=prev_artwork_id,
                          next_artwork_id=next_artwork_id,
                          image_aspect_ratio=image_aspect_ratio)

@app.route('/api/get_next_image', methods=['POST'])
def api_get_next_image():
    data = request.get_json()
    current_id = data.get('current_id')
    filters = data.get('filters', {})
    
    return get_navigation_image(current_id, filters, 'next')

@app.route('/api/get_previous_image', methods=['POST'])
def api_get_previous_image():
    data = request.get_json()
    current_id = data.get('current_id')
    filters = data.get('filters', {})
    
    return get_navigation_image(current_id, filters, 'previous')

def get_navigation_image(current_id, filters, direction):
    try:
        db = get_db()

        # 使用统一的查询构建器
        base_query, params = utils.build_artwork_query(filters, filters.get('sort', 'random'))

        # 获取符合条件的所有ID
        all_ids_query = f"SELECT id {base_query}"
        all_ids = [row[0] for row in db.execute(all_ids_query, params).fetchall()]
        
        if not all_ids:
            return jsonify({'success': False, 'error': 'No images found'})
        
        # 如果没有当前ID或当前ID不在列表中，返回第一个或最后一个图片
        if not current_id:
            return jsonify({
                'success': True, 
                'artwork_id': all_ids[0] if direction == 'next' else all_ids[-1]
            })
        
        try:
            current_id = int(current_id)
            current_index = all_ids.index(current_id)
            
            if direction == 'next':
                next_index = current_index + 1
                if next_index >= len(all_ids):
                    # 如果已经是最后一个，循环到第一个
                    next_id = all_ids[0]
                else:
                    next_id = all_ids[next_index]
            else:
                prev_index = current_index - 1
                if prev_index < 0:
                    # 如果已经是第一个，循环到最后一个
                    next_id = all_ids[-1]
                else:
                    next_id = all_ids[prev_index]
            
            return jsonify({'success': True, 'artwork_id': next_id})
        except (ValueError, IndexError):
            # 如果当前ID不在列表中，返回第一个或最后一个图片
            return jsonify({
                'success': True, 
                'artwork_id': all_ids[0] if direction == 'next' else all_ids[-1]
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})



# --- Comics Routes ---
@app.route('/comics')
def comics():
    """Comics homepage - card layout similar to gallery"""
    db = get_comics_db()

    page = request.args.get('page', 1, type=int)
    sort = request.args.get('sort', 'newest')
    offset = (page - 1) * IMAGES_PER_PAGE

    # Get total comics count
    count_row = db.execute("SELECT COUNT(id) FROM comics").fetchone()
    total_comics = count_row[0] if count_row else 0
    total_pages = math.ceil(total_comics / IMAGES_PER_PAGE) if total_comics > 0 else 1

    # Determine sort order
    sort_map = {
        'newest': 'creation_date DESC',
        'oldest': 'creation_date ASC',
        'title': 'title ASC'
    }
    order_by = sort_map.get(sort, 'creation_date DESC')

    # Get comics for current page with first page path
    comics_list = db.execute(f"""
        SELECT c.*, cp.file_path as first_page_path
        FROM comics c
        LEFT JOIN comic_pages cp ON c.id = cp.comic_id AND cp.page_number = 1
        ORDER BY {order_by}
        LIMIT ? OFFSET ?
    """, (IMAGES_PER_PAGE, offset)).fetchall()

    # 瀑布流布局：计算列数和分配
    columns = 4  # 默认4列，JavaScript会根据屏幕大小调整
    comic_columns = []
    
    # 简单的列分配算法（轮询分配）
    for i, comic in enumerate(comics_list):
        comic_columns.append(i % columns)

    return render_template('comics.html',
                          comics=comics_list,
                          page=page,
                          total_pages=total_pages,
                          columns=columns,
                          comic_columns=comic_columns,
                          current_filters=request.args.to_dict())

@app.route('/comic/<int:comic_id>')
def comic_reader(comic_id):
    """Comic reader - long scroll view for all comic pages"""
    db = get_comics_db()

    # Get comic info
    comic = db.execute("SELECT * FROM comics WHERE id = ?", (comic_id,)).fetchone()
    if not comic:
        abort(404)

    # Get all pages for this comic
    pages = db.execute("""
        SELECT * FROM comic_pages
        WHERE comic_id = ?
        ORDER BY page_number
    """, (comic_id,)).fetchall()

    return render_template('comic_reader.html',
                          comic=comic,
                          pages=pages,
                          current_filters={})

@app.route('/comics_thumbnail/<filename>')
def comics_thumbnail(filename):
    """Serve comics thumbnails"""
    return send_from_directory('static/comics_thumbnails', filename)

@app.route('/comic_page/<path:file_path>')
def comic_page(file_path):
    """Serve comic page images"""
    # Security check - ensure the path is within the comics directory
    full_path = os.path.join('zootopia_comics', file_path)
    if not os.path.exists(full_path):
        abort(404)

    # Ensure the path is within the comics directory
    comics_dir = os.path.abspath('zootopia_comics')
    requested_path = os.path.abspath(full_path)
    if not requested_path.startswith(comics_dir):
        abort(403)

    return send_file(full_path)

# --- 监控和日志相关路由 ---

@app.route('/monitoring')
def monitoring():
    """系统监控页面"""
    monitoring_data = logger.logger.get_monitoring_data()

    # 获取最近的日志（这里简化处理，实际应该从日志文件中读取）
    recent_logs = []  # 暂时留空，稍后完善

    return render_template('monitoring.html',
                          monitoring=monitoring_data,
                          recent_logs=recent_logs)

@app.route('/api/monitoring')
def api_monitoring():
    """监控数据API"""
    return jsonify(logger.logger.get_monitoring_data())

@app.route('/api/logs')
def api_logs():
    """获取最近的日志条目"""
    logs = []
    log_files = {
        'app': 'logs/app.log',
        'errors': 'logs/errors.log',
        'access': 'logs/access.log',
        'performance': 'logs/performance.log'
    }

    for log_type, log_file in log_files.items():
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()[-20:]  # 最近20条日志
                    for line in lines:
                        parts = line.strip().split(' - ', 3)
                        if len(parts) >= 3:
                            timestamp = parts[0]
                            level = parts[1] if parts[1] in ['INFO', 'ERROR', 'WARNING'] else 'INFO'
                            message = parts[-1]
                            logs.append({
                                'timestamp': timestamp,
                                'level': level,
                                'type': log_type,
                                'message': message
                            })
            except Exception:
                continue

    # 按时间戳排序
    logs.sort(key=lambda x: x['timestamp'], reverse=True)

    return jsonify({'logs': logs[:50]})  # 返回最新50条

@app.route('/api/logs/download')
def api_logs_download():
    """下载所有日志文件的ZIP包"""
    import zipfile
    import io

    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for log_file in ['logs/app.log', 'logs/errors.log', 'logs/access.log', 'logs/performance.log']:
            if os.path.exists(log_file):
                zipf.write(log_file, os.path.basename(log_file))

    memory_file.seek(0)
    return send_file(memory_file, as_attachment=True, download_name='gallery_logs.zip', mimetype='application/zip')

# --- 应用初始化 ---
if __name__ == '__main__':
    # 初始化日志系统
    logger.init_app_logging(app)
    logger.logger.app_logger.info("Gallery application starting...")
    app.run(host='0.0.0.0', port=5000, debug=True)
