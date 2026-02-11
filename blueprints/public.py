"""
Public mode blueprint for the dual-mode gallery system.

This blueprint handles all routes for the public (read-only) mode, which includes:
- Gallery browsing
- Artwork detail viewing
- Slide view
- Image wall
- Statistics viewing
- Comics viewing

All routes in this blueprint are read-only and use readonly database connections.
No write operations are allowed.
"""

from flask import Blueprint, g, request, abort
from blueprints.rate_limiter import rate_limit

# Create the public blueprint with /public URL prefix
public_bp = Blueprint('public', __name__, url_prefix='/public')


# --- Blueprint Request Hooks ---

@public_bp.before_request
def inject_mode():
    """Inject mode information into Flask's g object before each request"""
    g.mode = 'public'
    g.is_private = False
    g.is_public = True


@public_bp.before_request
def enforce_readonly():
    """Ensure only GET and HEAD requests are allowed in public mode"""
    if request.method not in ['GET', 'HEAD']:
        from logger import logger
        logger.app_logger.warning(
            f"Write operation attempted in public mode: {request.method} {request.path} "
            f"from IP {request.remote_addr}"
        )
        abort(403, description="Write operations are not allowed in public mode")


import sqlite3
import math
import os
from flask import render_template
from PIL import Image
import config
import utils
from blueprints.db_utils import get_db_readonly

# Configuration
IMAGES_PER_PAGE = config.IMAGES_PER_PAGE


# --- Database Helper Functions ---

def get_aspect_ratios_db():
    """Get aspect ratios database connection (read-only)"""
    db = getattr(g, '_aspect_ratios_db_public', None)
    if db is None:
        db = g._aspect_ratios_db_public = sqlite3.connect('aspect_ratios.db')
        db.execute("PRAGMA query_only = ON")
        db.row_factory = sqlite3.Row
    return db


# --- Core Gallery Routes ---

@public_bp.route('/')
@public_bp.route('/gallery')
@rate_limit(limit=100, window=3600)  # 100 requests per hour
def gallery():
    """Public mode gallery page - read-only"""
    from blueprints.security import validate_query_params
    
    db = get_db_readonly()
    
    filters = request.args.to_dict()
    
    # Validate query parameters
    validate_query_params(filters)
    
    sort_key = filters.get('sort', 'random')

    # Use unified query builder
    base_query, params = utils.build_artwork_query(filters, sort_key)

    # Handle seed generation redirect for random sort
    if 'random' in sort_key and 'seed' not in filters:
        from flask import redirect, url_for
        seed = utils.generate_timestamp_seed()
        filters['seed'] = seed
        return redirect(url_for('public.gallery', **filters))

    # Pagination
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * IMAGES_PER_PAGE

    # Execute query
    count_row = db.execute("SELECT COUNT(id) " + base_query, params).fetchone()
    total_artworks = count_row[0] if count_row else 0
    total_pages = math.ceil(total_artworks / IMAGES_PER_PAGE) if total_artworks > 0 else 1

    main_query = "SELECT * " + base_query
    if IMAGES_PER_PAGE:
        main_query += f" LIMIT {IMAGES_PER_PAGE} OFFSET {offset}"

    artworks = db.execute(main_query, params).fetchall()

    # Get aspect ratios for waterfall layout
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
        pass
    
    # Calculate waterfall layout
    columns = 4
    column_heights = [0] * columns
    artwork_columns = []
    
    for art in artworks:
        aspect_ratio = aspect_ratios.get(art['id'], 1.0)
        card_height = 1.0 / aspect_ratio + 0.3
        
        min_col = column_heights.index(min(column_heights))
        artwork_columns.append(min_col)
        
        column_heights[min_col] += card_height

    return render_template('gallery.html', artworks=artworks, page=page, total_pages=total_pages,
                           total_artworks=total_artworks, current_sort=sort_key, current_filters=filters,
                           columns=columns, aspect_ratios=aspect_ratios, artwork_columns=artwork_columns)


@public_bp.route('/artwork/<int:artwork_id>')
@rate_limit(limit=100, window=3600)  # 100 requests per hour
def artwork_detail(artwork_id):
    """Public mode artwork detail page - read-only"""
    db = get_db_readonly()
    artwork = db.execute("SELECT * FROM artworks WHERE id = ?", (artwork_id,)).fetchone()
    if artwork is None:
        abort(404)
    
    # Query series artworks
    import re
    series_artworks = []
    if artwork['title'] and artwork['artist']:
        if re.search(r'\s*\(\d+\)', artwork['title']):
            title_pattern = re.sub(r'\s*\(\d+\)', '', artwork['title'])
            
            query = """
            SELECT id, file_name, title FROM artworks 
            WHERE title LIKE ? AND artist = ? AND id != ?
            ORDER BY title
            """
            candidates = db.execute(query, (f'{title_pattern}%', artwork['artist'], artwork_id)).fetchall()
            
            series_pattern = re.compile(f'^{re.escape(title_pattern)}\\s*\\(\\d+\\)')
            series_artworks = [
                artwork for artwork in candidates 
                if series_pattern.match(artwork['title'])
            ]
    
    return render_template('artwork_detail.html', artwork=artwork, series_artworks=series_artworks, current_filters={})


@public_bp.route('/slide_view')
@rate_limit(limit=100, window=3600)  # 100 requests per hour
def slide_view():
    """Public mode slide view - read-only"""
    db = get_db_readonly()

    filters = request.args.to_dict()

    if 'sort' not in filters:
        filters['sort'] = 'random'

    if filters.get('sort') == 'random' and 'seed' not in filters:
        from flask import redirect, url_for
        seed = utils.generate_timestamp_seed()
        filters['seed'] = seed
        return redirect(url_for('public.slide_view', **filters))

    current_id = filters.get('id')

    base_query, params = utils.build_artwork_query(filters, filters.get('sort', 'random'))

    all_ids_query = f"SELECT id {base_query}"
    all_ids = [row[0] for row in db.execute(all_ids_query, params).fetchall()]

    total_images = len(all_ids)

    artwork = None
    current_position = 0
    image_aspect_ratio = None

    if total_images > 0:
        if current_id:
            try:
                current_id = int(current_id)
                artwork = db.execute("SELECT * FROM artworks WHERE id = ?", (current_id,)).fetchone()
                if artwork:
                    current_position = all_ids.index(current_id) + 1
                else:
                    artwork_query = f"SELECT * {base_query} LIMIT 1"
                    artwork = db.execute(artwork_query, params).fetchone()
                    if artwork:
                        current_position = 1
            except ValueError:
                artwork_query = f"SELECT * {base_query} LIMIT 1"
                artwork = db.execute(artwork_query, params).fetchone()
                if artwork:
                    current_position = 1
        else:
            artwork_query = f"SELECT * {base_query} LIMIT 1"
            artwork = db.execute(artwork_query, params).fetchone()
            if artwork:
                current_position = 1

    if artwork and artwork['file_path'] and os.path.exists(artwork['file_path']):
        try:
            with Image.open(artwork['file_path']) as img:
                width, height = img.size
                image_aspect_ratio = width / height if height > 0 else 1.0
        except Exception:
            image_aspect_ratio = 1.0

    current_filters_without_id = filters.copy()
    if 'id' in current_filters_without_id:
        del current_filters_without_id['id']

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


@public_bp.route('/image-wall')
@rate_limit(limit=100, window=3600)  # 100 requests per hour
def image_wall():
    """Public mode image wall view - read-only"""
    db = get_db_readonly()
    
    filters = request.args.to_dict()
    sort_key = filters.get('sort', 'random')
    columns = request.args.get('columns', 4, type=int)
    
    base_query, params = utils.build_artwork_query(filters, sort_key)
    
    if 'random' in sort_key and 'seed' not in filters:
        from flask import redirect, url_for
        seed = utils.generate_timestamp_seed()
        filters['seed'] = seed
        filters['columns'] = columns
        return redirect(url_for('public.image_wall', **filters))
    
    main_query = "SELECT * " + base_query
    artworks = db.execute(main_query, params).fetchall()
    
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
        pass
    
    column_heights = [0] * columns
    artwork_columns = []
    
    for art in artworks:
        aspect_ratio = aspect_ratios.get(art['id'], 1.0)
        card_height = 1.0 / aspect_ratio + 0.3
        
        min_col = column_heights.index(min(column_heights))
        artwork_columns.append(min_col)
        
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


@public_bp.route('/statistics')
@rate_limit(limit=100, window=3600)  # 100 requests per hour
def statistics():
    """Public mode statistics page - read-only"""
    return render_template('statistics.html', current_filters={})



# --- Comics Routes ---

@public_bp.route('/comics')
@rate_limit(limit=100, window=3600)  # 100 requests per hour
def comics():
    """Public mode comics homepage - read-only"""
    from blueprints.db_utils import get_comics_db_readonly
    db = get_comics_db_readonly()

    page = request.args.get('page', 1, type=int)
    sort = request.args.get('sort', 'newest')
    offset = (page - 1) * IMAGES_PER_PAGE

    count_row = db.execute("SELECT COUNT(id) FROM comics").fetchone()
    total_comics = count_row[0] if count_row else 0
    total_pages = math.ceil(total_comics / IMAGES_PER_PAGE) if total_comics > 0 else 1

    sort_map = {
        'newest': 'creation_date DESC',
        'oldest': 'creation_date ASC',
        'title': 'title ASC'
    }
    order_by = sort_map.get(sort, 'creation_date DESC')

    comics_list = db.execute(f"""
        SELECT c.*, cp.file_path as first_page_path
        FROM comics c
        LEFT JOIN comic_pages cp ON c.id = cp.comic_id AND cp.page_number = 1
        ORDER BY {order_by}
        LIMIT ? OFFSET ?
    """, (IMAGES_PER_PAGE, offset)).fetchall()

    columns = 4
    comic_columns = []
    
    for i, comic in enumerate(comics_list):
        comic_columns.append(i % columns)

    return render_template('comics.html',
                          comics=comics_list,
                          page=page,
                          total_pages=total_pages,
                          columns=columns,
                          comic_columns=comic_columns,
                          current_filters=request.args.to_dict())


@public_bp.route('/comic/<int:comic_id>')
@rate_limit(limit=100, window=3600)  # 100 requests per hour
def comic_reader(comic_id):
    """Public mode comic reader - read-only"""
    from blueprints.db_utils import get_comics_db_readonly
    db = get_comics_db_readonly()

    comic = db.execute("SELECT * FROM comics WHERE id = ?", (comic_id,)).fetchone()
    if not comic:
        abort(404)

    pages = db.execute("""
        SELECT * FROM comic_pages
        WHERE comic_id = ?
        ORDER BY page_number
    """, (comic_id,)).fetchall()

    return render_template('comic_reader.html',
                          comic=comic,
                          pages=pages,
                          current_filters={})


# --- Additional Helper Routes ---

@public_bp.route('/categories')
def categories_list():
    """Public mode categories list page - read-only"""
    db = get_db_readonly()
    
    # Get distinct values for artists and platforms
    all_artists = db.execute(
        "SELECT DISTINCT artist FROM artworks WHERE artist IS NOT NULL ORDER BY artist"
    ).fetchall()
    all_artists = [row['artist'] for row in all_artists]
    
    all_platforms = db.execute(
        "SELECT DISTINCT source_platform FROM artworks WHERE source_platform IS NOT NULL ORDER BY source_platform"
    ).fetchall()
    all_platforms = [row['source_platform'] for row in all_platforms]
    
    return render_template('categories.html', all_artists=all_artists, all_platforms=all_platforms, current_filters={})


@public_bp.route('/artist-ranking')
def artist_ranking_noscript():
    """Public mode artist ranking page - read-only"""
    db = get_db_readonly()
    
    # Get comprehensive artist ratings
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
    
    # Calculate weighted score
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
    
    # Sort by weighted score
    artist_ranking.sort(key=lambda x: x['weighted_score'], reverse=True)
    
    return render_template('artist_ranking_noscript.html', artist_ranking=artist_ranking, current_filters={})


# --- Error Handlers ---

@public_bp.errorhandler(404)
def public_not_found(error):
    """Handle 404 errors in public mode"""
    from logger import logger
    logger.app_logger.warning(f"404 error in public mode: {request.url}")
    return render_template('errors/404.html', mode='public'), 404


@public_bp.errorhandler(403)
def public_forbidden(error):
    """Handle 403 errors in public mode"""
    from logger import logger
    logger.app_logger.warning(f"403 error in public mode: {request.url}")
    # Don't reveal system information in error message
    return render_template('errors/403.html', mode='public'), 403


@public_bp.errorhandler(500)
def public_internal_error(error):
    """Handle 500 errors in public mode"""
    from logger import logger
    logger.log_error(f"500 error in public mode: {str(error)}", exc_info=True)
    # Don't reveal system information in error message
    return render_template('errors/500.html', mode='public'), 500


@public_bp.errorhandler(429)
def public_rate_limit_error(error):
    """Handle 429 rate limit errors in public mode"""
    from logger import logger
    logger.app_logger.warning(f"429 rate limit error in public mode: {request.url}")
    return render_template('errors/429.html', mode='public'), 429


@public_bp.errorhandler(400)
def public_bad_request(error):
    """Handle 400 bad request errors in public mode"""
    from logger import logger
    logger.app_logger.warning(f"400 bad request in public mode: {request.url}")
    return render_template('errors/400.html', mode='public'), 400
