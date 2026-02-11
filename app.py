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
from blueprints.context_processors import register_context_processors
from blueprints.private import private_bp
from blueprints.public import public_bp

# --- App Configuration ---
app = Flask(__name__)
DATABASE = config.DB_FILE
COMICS_DATABASE = "zootopia_comics.db"
IMAGES_PER_PAGE = config.IMAGES_PER_PAGE

# Register context processors for dual-mode support
register_context_processors(app)

# Register blueprints
app.register_blueprint(private_bp)
app.register_blueprint(public_bp)

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
    # Close readonly connection if it exists
    db_readonly = getattr(g, '_database_readonly', None)
    if db_readonly is not None:
        db_readonly.close()

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
    # Close readonly comics connection if it exists
    db_readonly = getattr(g, '_comics_database_readonly', None)
    if db_readonly is not None:
        db_readonly.close()

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
@app.route('/artwork/<int:artwork_id>')
def legacy_artwork_detail(artwork_id):
    """Redirect old artwork detail route to private mode"""
    return redirect(url_for('private.artwork_detail', artwork_id=artwork_id))

@app.route('/rate/<int:artwork_id>', methods=['POST'])
def legacy_rate_artwork(artwork_id):
    """Redirect old rate route to private mode"""
    return redirect(url_for('private.rate_artwork', artwork_id=artwork_id), code=307)


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

# --- Backward Compatibility Redirects ---
# Root route redirects to private gallery for backward compatibility
@app.route('/')
def root():
    """Redirect root path to private gallery for backward compatibility"""
    return redirect(url_for('private.gallery', **request.args))

@app.route('/gallery')
def legacy_gallery():
    """Redirect old gallery route to private mode"""
    return redirect(url_for('private.gallery', **request.args))

@app.route('/image-wall')
def legacy_image_wall():
    """Redirect old image-wall route to private mode"""
    return redirect(url_for('private.image_wall', **request.args))

@app.route('/statistics')
def legacy_statistics():
    """Redirect old statistics route to private mode"""
    return redirect(url_for('private.statistics', **request.args))

@app.route('/slide_view')
def legacy_slide_view():
    """Redirect old slide_view route to private mode"""
    return redirect(url_for('private.slide_view', **request.args))

@app.route('/classify/<int:artwork_id>', methods=['POST'])
def legacy_classify_artwork(artwork_id):
    """Redirect old classify route to private mode"""
    return redirect(url_for('private.classify_artwork', artwork_id=artwork_id), code=307)

@app.route('/set_category/<int:artwork_id>', methods=['POST'])
def legacy_set_category(artwork_id):
    """Redirect old set_category route to private mode"""
    return redirect(url_for('private.set_category', artwork_id=artwork_id), code=307)

@app.route('/comics')
def legacy_comics():
    """Redirect old comics route to private mode"""
    return redirect(url_for('private.comics', **request.args))

@app.route('/comic/<int:comic_id>')
def legacy_comic_reader(comic_id):
    """Redirect old comic reader route to private mode"""
    return redirect(url_for('private.comic_reader', comic_id=comic_id))



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





@app.route('/image_proxy/<int:artwork_id>')
def image_proxy(artwork_id):
    db = get_db()
    artwork = db.execute("SELECT file_path FROM artworks WHERE id = ?", (artwork_id,)).fetchone()
    if artwork and os.path.exists(artwork['file_path']):
        return send_file(artwork['file_path'])
    else:
        abort(404)

# --- NEW: Route to handle classification change ---
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
