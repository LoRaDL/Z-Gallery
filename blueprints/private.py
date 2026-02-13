"""
Private mode blueprint for the dual-mode gallery system.

This blueprint handles all routes for the private (admin) mode, which includes:
- Full CRUD operations on artworks
- Rating and classification functionality
- Comics management
- All administrative features

Access to these routes should be protected by Cloudflare Access authentication.
"""

import sqlite3
import math
import os
import re
import shutil
import json
import sys
import subprocess
from flask import Blueprint, render_template, request, g, redirect, url_for, abort, send_file, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image
import imagehash
import config
import utils
import artwork_importer

# Create the private blueprint with /private URL prefix
private_bp = Blueprint('private', __name__, url_prefix='/private')

# Configuration
DATABASE = config.DB_FILE
COMICS_DATABASE = "zootopia_comics.db"
IMAGES_PER_PAGE = config.IMAGES_PER_PAGE


# --- Blueprint Request Hooks ---

@private_bp.before_request
def inject_mode():
    """Inject mode information into Flask's g object before each request"""
    g.mode = 'private'
    g.is_private = True
    g.is_public = False


# --- Database Helper Functions ---

def get_db():
    """Get standard read-write database connection"""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


def get_comics_db():
    """Get comics database connection"""
    db = getattr(g, '_comics_database', None)
    if db is None:
        db = g._comics_database = sqlite3.connect(COMICS_DATABASE)
        db.row_factory = sqlite3.Row
    return db


def get_aspect_ratios_db():
    """Get aspect ratios database connection"""
    db = getattr(g, '_aspect_ratios_db', None)
    if db is None:
        db = g._aspect_ratios_db = sqlite3.connect('aspect_ratios.db')
        db.row_factory = sqlite3.Row
    return db


def get_distinct_values(column_name):
    """Get distinct values from a column in the artworks table"""
    db = get_db()
    query = f"SELECT DISTINCT {column_name} FROM artworks WHERE {column_name} IS NOT NULL ORDER BY {column_name}"
    return [row[column_name] for row in db.execute(query).fetchall()]


def is_duplicate(platform, artist, title):
    """Check if a specific platform + artist + title combination already exists"""
    db = get_db()
    row = db.execute(
        "SELECT id FROM artworks WHERE source_platform = ? AND artist = ? AND title = ?",
        (platform, artist, title)
    ).fetchone()
    return row is not None


# --- Core Gallery Routes ---

@private_bp.route('/')
@private_bp.route('/gallery')
def gallery():
    """Private mode gallery page with full functionality"""
    from blueprints.security import validate_query_params
    
    db = get_db()
    
    filters = request.args.to_dict()
    
    # Validate query parameters
    validate_query_params(filters)
    
    sort_key = filters.get('sort', 'random')

    # Use unified query builder
    base_query, params = utils.build_artwork_query(filters, sort_key)

    # Handle seed generation redirect for random sort
    if 'random' in sort_key and 'seed' not in filters:
        seed = utils.generate_timestamp_seed()
        filters['seed'] = seed
        return redirect(url_for('private.gallery', **filters))

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


@private_bp.route('/artwork/<int:artwork_id>')
def artwork_detail(artwork_id):
    """Private mode artwork detail page with edit capabilities"""
    db = get_db()
    artwork = db.execute("SELECT * FROM artworks WHERE id = ?", (artwork_id,)).fetchone()
    if artwork is None:
        abort(404)
    
    # Query series artworks
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


@private_bp.route('/slide_view')
def slide_view():
    """Private mode slide view with rating functionality"""
    db = get_db()

    filters = request.args.to_dict()

    if 'sort' not in filters:
        filters['sort'] = 'random'

    if filters.get('sort') == 'random' and 'seed' not in filters:
        seed = utils.generate_timestamp_seed()
        filters['seed'] = seed
        return redirect(url_for('private.slide_view', **filters))

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


@private_bp.route('/image-wall')
def image_wall():
    """Private mode image wall view"""
    db = get_db()
    
    filters = request.args.to_dict()
    sort_key = filters.get('sort', 'random')
    columns = request.args.get('columns', 4, type=int)
    
    base_query, params = utils.build_artwork_query(filters, sort_key)
    
    if 'random' in sort_key and 'seed' not in filters:
        seed = utils.generate_timestamp_seed()
        filters['seed'] = seed
        filters['columns'] = columns
        return redirect(url_for('private.image_wall', **filters))
    
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


@private_bp.route('/statistics')
def statistics():
    """Private mode statistics page"""
    return render_template('statistics.html', current_filters={})


# This route will be implemented in the next subtask (2.3)
# Placeholder for write operation routes



# --- Write Operation Routes ---

@private_bp.route('/rate/<int:artwork_id>', methods=['POST'])
def rate_artwork(artwork_id):
    """Rate an artwork (private mode only)"""
    from blueprints.security import validate_artwork_id, validate_rating
    
    # Validate inputs
    validate_artwork_id(artwork_id)
    
    db = get_db()
    rating = request.form.get('rating', type=int)
    
    validate_rating(rating)
    
    db.execute('UPDATE artworks SET rating = ? WHERE id = ?', (rating, artwork_id))
    db.commit()
    
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if is_ajax:
        return jsonify({'success': True, 'message': 'Rating updated successfully.', 'new_rating': rating})
    else:
        if request.referrer and 'slide_view' in request.referrer:
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(request.referrer)
            referrer_params = parse_qs(parsed_url.query)
            referrer_params_single = {k: v[0] if isinstance(v, list) and len(v) > 0 else v for k, v in referrer_params.items()}
            current_id = referrer_params_single.get('id', None)
            
            next_artwork_response = get_navigation_image(current_id, referrer_params_single, 'next')
            next_artwork_data = next_artwork_response.get_json() if hasattr(next_artwork_response, 'get_json') else None
            
            if isinstance(next_artwork_data, dict) and next_artwork_data.get('success'):
                new_params = referrer_params_single.copy()
                new_params['id'] = next_artwork_data.get('artwork_id')
                new_params.pop('rating', None)
                query_string = '&'.join([f"{key}={value}" for key, value in new_params.items() if value is not None])
                return redirect(url_for('private.slide_view') + '?' + query_string + '#image-top')
            else:
                return redirect(request.referrer + '#image-top')
        elif request.referrer:
            from urllib.parse import urlparse, parse_qs, urlencode
            parsed_url = urlparse(request.referrer)
            referrer_params = parse_qs(parsed_url.query)
            referrer_params_single = {k: v[0] if isinstance(v, list) and len(v) > 0 else v for k, v in referrer_params.items()}
            query_string = urlencode(referrer_params_single, doseq=True)
            final_url = f"{parsed_url.path}?{query_string}#artwork-{artwork_id}" if query_string else f"{parsed_url.path}#artwork-{artwork_id}"
            return redirect(final_url)
        else:
            return redirect(url_for('private.gallery') + '#artwork-' + str(artwork_id))


@private_bp.route('/classify/<int:artwork_id>', methods=['POST'])
def classify_artwork(artwork_id):
    """Change artwork classification (private mode only)"""
    from blueprints.security import validate_artwork_id, validate_classification
    
    # Validate inputs
    validate_artwork_id(artwork_id)
    
    db = get_db()
    classification = request.form.get('classification')
    
    validate_classification(classification)
    
    final_classification = None
    if classification in ['sfw', 'mature', 'nsfw']:
        final_classification = classification
        db.execute(
            "UPDATE artworks SET classification = ? WHERE id = ?",
            (classification, artwork_id)
        )
    elif classification == 'unspecified':
        db.execute(
            "UPDATE artworks SET classification = NULL WHERE id = ?",
            (artwork_id,)
        )
    
    db.commit()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'new_classification': final_classification})
    
    return redirect(url_for('private.artwork_detail', artwork_id=artwork_id) + "#page-top")


@private_bp.route('/set_category/<int:artwork_id>', methods=['POST'])
def set_category(artwork_id):
    """Set artwork category (private mode only)"""
    from blueprints.security import validate_artwork_id, validate_category
    
    # Validate inputs
    validate_artwork_id(artwork_id)
    
    db = get_db()
    category = request.form.get('category')

    validate_category(category)
    
    db.execute(
        "UPDATE artworks SET category = ? WHERE id = ?",
        (category, artwork_id)
    )
    db.commit()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'new_category': category})
    
    return redirect(url_for('private.artwork_detail', artwork_id=artwork_id) + "#page-top")


@private_bp.route('/api/delete_artwork/<int:artwork_id>', methods=['POST'])
def api_delete_artwork(artwork_id):
    """Delete an artwork (private mode only)"""
    from blueprints.security import validate_artwork_id
    
    # Validate input
    validate_artwork_id(artwork_id)
    
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
        if os.path.exists(original_path):
            shutil.move(original_path, os.path.join(TRASH_DIR, os.path.basename(original_path)))
        
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)
            
        db.execute("DELETE FROM artworks WHERE id = ?", (artwork_id,))
        db.commit()
        
        return jsonify({'success': True, 'message': 'Artwork moved to trash.'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@private_bp.route('/api/update_artwork_field/<int:artwork_id>', methods=['POST'])
def api_update_artwork_field(artwork_id):
    """Update a specific artwork field (private mode only)"""
    from blueprints.security import validate_artwork_id, validate_field_name, validate_input
    
    # Validate artwork ID
    validate_artwork_id(artwork_id)
    
    db = get_db()
    
    if request.is_json:
        data = request.get_json()
        field_to_update = data.get('field')
        new_value = data.get('value')
    else:
        field_to_update = request.form.get('field')
        new_value = request.form.get('value')

    if not field_to_update or new_value is None:
        return jsonify({'success': False, 'error': 'Field and value are required.'}), 400

    # Validate field name
    validate_field_name(field_to_update)
    
    # Validate the new value for SQL injection
    validate_input(new_value, field_name=field_to_update, check_sql=True, check_path=False)

    try:
        query = f"UPDATE artworks SET {field_to_update} = ? WHERE id = ?"
        db.execute(query, (new_value, artwork_id))
        db.commit()
        
        if request.is_json:
            return jsonify({'success': True, 'message': f'{field_to_update.capitalize()} updated successfully.'})
        else:
            return redirect(url_for('private.artwork_detail', artwork_id=artwork_id))
            
    except sqlite3.Error as e:
        db.rollback()
        if request.is_json:
            return jsonify({'success': False, 'error': f'Database error: {e}'}), 500
        else:
            return redirect(url_for('private.artwork_detail', artwork_id=artwork_id))


# --- Navigation API Routes ---

@private_bp.route('/api/get_next_image', methods=['POST'])
def api_get_next_image():
    """Get next image in slide view"""
    data = request.get_json()
    current_id = data.get('current_id')
    filters = data.get('filters', {})
    
    return get_navigation_image(current_id, filters, 'next')


@private_bp.route('/api/get_previous_image', methods=['POST'])
def api_get_previous_image():
    """Get previous image in slide view"""
    data = request.get_json()
    current_id = data.get('current_id')
    filters = data.get('filters', {})
    
    return get_navigation_image(current_id, filters, 'previous')


def get_navigation_image(current_id, filters, direction):
    """Helper function to get next/previous image"""
    try:
        db = get_db()

        base_query, params = utils.build_artwork_query(filters, filters.get('sort', 'random'))

        all_ids_query = f"SELECT id {base_query}"
        all_ids = [row[0] for row in db.execute(all_ids_query, params).fetchall()]
        
        if not all_ids:
            return jsonify({'success': False, 'error': 'No images found'})
        
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
                    next_id = all_ids[0]
                else:
                    next_id = all_ids[next_index]
            else:
                prev_index = current_index - 1
                if prev_index < 0:
                    next_id = all_ids[-1]
                else:
                    next_id = all_ids[prev_index]
            
            return jsonify({'success': True, 'artwork_id': next_id})
        except (ValueError, IndexError):
            return jsonify({
                'success': True, 
                'artwork_id': all_ids[0] if direction == 'next' else all_ids[-1]
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# --- Comics Routes ---

@private_bp.route('/comics')
def comics():
    """Private mode comics homepage"""
    db = get_comics_db()

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


@private_bp.route('/comic/<int:comic_id>')
def comic_reader(comic_id):
    """Private mode comic reader"""
    db = get_comics_db()

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

@private_bp.route('/categories')
def categories_list():
    """Categories list page"""
    all_artists = get_distinct_values('artist')
    all_platforms = get_distinct_values('source_platform')
    return render_template('categories.html', all_artists=all_artists, all_platforms=all_platforms, current_filters={})


@private_bp.route('/artist-ranking')
def artist_ranking_noscript():
    """Artist ranking page"""
    db = get_db()
    
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
    
    artist_ranking.sort(key=lambda x: x['weighted_score'], reverse=True)
    
    return render_template('artist_ranking_noscript.html', artist_ranking=artist_ranking, current_filters={})


@private_bp.route('/api/statistics/<stat_type>')
def api_statistics(stat_type):
    """Statistics API endpoint"""
    db = get_db()
    
    if stat_type == 'rating':
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
        data = [{'label': f'{row["rating_value"]}', 'value': row['count']} for row in rows]
        
    elif stat_type == 'artist-works':
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
        import math
        data = [{'label': row['artist'] or 'Unknown', 'value': float(row['average_rating'] * math.log(row['work_count'] + 1))} for row in rows]
        data.sort(key=lambda x: x['value'], reverse=True)
        
    else:
        return jsonify({'success': False, 'error': 'Invalid statistic type'}), 400
    
    return jsonify({'success': True, 'data': data})


@private_bp.route('/api/artists')
def api_artists():
    """API endpoint for artist autocomplete"""
    return jsonify(get_distinct_values('artist'))


@private_bp.route('/api/platforms')
def api_platforms():
    """API endpoint for platform autocomplete"""
    return jsonify(get_distinct_values('source_platform'))


@private_bp.route('/add')
def add_artwork_page():
    """Page for adding new artwork"""
    return render_template('add_artwork.html', current_filters={})


@private_bp.route('/api/add_artwork', methods=['POST'])
def api_add_artwork():
    """API endpoint to handle artwork upload"""
    source_path = None
    
    temp_filename = request.form.get('temp_filename')
    if temp_filename:
        source_path = os.path.join('temp_uploads', temp_filename)
        if not os.path.exists(source_path):
            return jsonify({'success': False, 'error': f"Temporary file '{temp_filename}' not found."}), 400
    
    elif 'artwork_file' in request.files:
        file = request.files['artwork_file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected.'}), 400
        
        original_filename = secure_filename(file.filename)
        source_path = os.path.join('temp_uploads', original_filename)
        file.save(source_path)
    else:
        return jsonify({'success': False, 'error': 'No file part provided.'}), 400

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
    
    if not metadata['artist'] or not metadata['platform']:
        if os.path.exists(source_path):
            os.remove(source_path)
        return jsonify({'success': False, 'error': 'Artist and Platform are required.'}), 400

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
        if os.path.exists(source_path):
            os.remove(source_path)
        
        status_code = 409 if "Duplicate" in error else 500
        return jsonify({'success': False, 'error': error}), status_code


@private_bp.route('/api/get_similar_ids', methods=['POST'])
def api_get_similar_ids():
    """API endpoint to find similar images by upload"""
    if 'search_file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['search_file']
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
                if distance < threshold:
                    results.append({'id': row['id'], 'distance': distance})
            except Exception:
                continue
            
        results.sort(key=lambda x: x['distance'])
        result_ids = [str(res['id']) for res in results][:50]

        return jsonify({'success': True, 'ids': ",".join(result_ids)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@private_bp.route('/api/get_similar_ids_by_id/<int:artwork_id>')
def api_get_similar_ids_by_id(artwork_id):
    """API endpoint to find similar images by artwork ID"""
    db = get_db()
    threshold = request.args.get('threshold', 10, type=int)
    
    source_artwork = db.execute("SELECT phash FROM artworks WHERE id = ?", (artwork_id,)).fetchone()
    if not source_artwork or not source_artwork['phash']:
        return jsonify({'success': False, 'error': 'Source image has no hash or does not exist.'}), 404
        
    try:
        query_hash = imagehash.hex_to_hash(source_artwork['phash'])
        
        all_hashes = db.execute("SELECT id, phash FROM artworks WHERE phash IS NOT NULL").fetchall()

        results = []
        for row in all_hashes:
            try:
                db_hash = imagehash.hex_to_hash(row['phash'])
                distance = query_hash - db_hash
                if distance < threshold:
                    results.append({'id': row['id'], 'distance': distance})
            except Exception:
                continue
            
        results.sort(key=lambda x: x['distance'])
        result_ids = [str(res['id']) for res in results][:50]

        return jsonify({'success': True, 'ids': ",".join(result_ids)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@private_bp.route('/find_similar/<int:artwork_id>')
def find_similar(artwork_id):
    """Find similar images (no-JS fallback)"""
    response = api_get_similar_ids_by_id(artwork_id)
    
    if response.status_code == 200:
        result = json.loads(response.get_data(as_text=True))
        if result.get('success'):
            similar_ids = result.get('ids', '')
            threshold = request.args.get('threshold', 10, type=int)
            search_params = {
                'similar_to': similar_ids,
                'threshold': threshold
            }
            
            return redirect(url_for('private.gallery', **search_params))
    
    return redirect(url_for('private.artwork_detail', artwork_id=artwork_id))


@private_bp.route('/api/fetch_metadata', methods=['POST'])
def api_fetch_metadata():
    """API endpoint to fetch metadata from URL"""
    data = request.get_json()
    url = data.get('url')
    proxy = data.get('proxy')
    if not url:
        return jsonify({'success': False, 'error': 'URL is required.'}), 400

    command = [sys.executable, 'metadata_fetcher.py', url]
    if proxy:
        command.extend(['--proxy', proxy])

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=90
        )

        response_data = json.loads(result.stdout)

        return jsonify({'success': True, **response_data, 'temp_path': response_data.get('temp_path')})

    except Exception as e:
        err_msg = e.stderr.strip() if hasattr(e, 'stderr') else str(e)
        return jsonify({'success': False, 'error': f"Failed to process URL: {err_msg}"}), 400


@private_bp.route('/temp_image/<filename>')
def temp_image(filename):
    """Serve temporary uploaded images"""
    from blueprints.security import sanitize_filename
    
    # Sanitize filename to prevent path traversal
    filename = sanitize_filename(filename)
    
    return send_file(os.path.join('temp_uploads', filename))


@private_bp.route('/comics_thumbnail/<filename>')
def comics_thumbnail(filename):
    """Serve comics thumbnails"""
    return send_from_directory('static/comics_thumbnails', filename)


@private_bp.route('/comic_page/<path:file_path>')
def comic_page(file_path):
    """Serve comic page images"""
    from blueprints.security import validate_input
    
    # Validate file path for path traversal
    validate_input(file_path, field_name='file_path', check_sql=False, check_path=True)
    
    full_path = os.path.join('zootopia_comics', file_path)
    if not os.path.exists(full_path):
        abort(404)

    comics_dir = os.path.abspath('zootopia_comics')
    requested_path = os.path.abspath(full_path)
    if not requested_path.startswith(comics_dir):
        abort(403)

    return send_file(full_path)


# --- Error Handlers ---

@private_bp.errorhandler(404)
def private_not_found(error):
    """Handle 404 errors in private mode"""
    from logger import logger
    logger.app_logger.warning(f"404 error in private mode: {request.url}")
    return render_template('errors/404.html', mode='private', current_filters={}), 404


@private_bp.errorhandler(403)
def private_forbidden(error):
    """Handle 403 errors in private mode"""
    from logger import logger
    logger.app_logger.warning(f"403 error in private mode: {request.url}")
    # Don't reveal system information in error message
    return render_template('errors/403.html', mode='private', current_filters={}), 403


@private_bp.errorhandler(500)
def private_internal_error(error):
    """Handle 500 errors in private mode"""
    from logger import logger
    logger.log_error(f"500 error in private mode: {str(error)}", exc_info=True)
    # Don't reveal system information in error message
    return render_template('errors/500.html', mode='private', current_filters={}), 500


@private_bp.errorhandler(429)
def private_rate_limit_error(error):
    """Handle 429 rate limit errors in private mode"""
    from logger import logger
    logger.app_logger.warning(f"429 rate limit error in private mode: {request.url}")
    return render_template('errors/429.html', mode='private', current_filters={}), 429


@private_bp.errorhandler(400)
def private_bad_request(error):
    """Handle 400 bad request errors in private mode"""
    from logger import logger
    logger.app_logger.warning(f"400 bad request in private mode: {request.url}")
    return render_template('errors/400.html', mode='private', current_filters={}), 400
