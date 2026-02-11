# Blueprints Package - Dual-Mode Gallery System

This package contains the infrastructure for the dual-mode gallery system, which supports both private (admin) and public (read-only) access modes.

## Package Structure

```
blueprints/
├── __init__.py              # Package initialization
├── db_utils.py              # Database connection utilities
├── context_processors.py    # Template context processors
├── decorators.py            # Route decorators for access control
└── README.md               # This file
```

## Components

### 1. Database Utilities (`db_utils.py`)

Provides database connection functions for both read-write and read-only access:

- **`get_db_readonly()`**: Returns a read-only SQLite connection with `PRAGMA query_only = ON`
- **`get_comics_db_readonly()`**: Returns a read-only connection for the comics database
- **`inject_mode_info(mode)`**: Injects mode information into Flask's `g` object

#### Usage Example:

```python
from blueprints.db_utils import get_db_readonly

@app.route('/public/gallery')
def public_gallery():
    db = get_db_readonly()  # This connection cannot write to the database
    artworks = db.execute("SELECT * FROM artworks").fetchall()
    return render_template('gallery.html', artworks=artworks)
```

### 2. Context Processors (`context_processors.py`)

Provides template context and URL generation helpers:

- **`inject_mode_context()`**: Makes `mode`, `is_private`, and `is_public` available in all templates
- **`inject_url_helpers()`**: Provides `mode_url_for()` function for mode-aware URL generation
- **`register_context_processors(app)`**: Registers all context processors with the Flask app

#### Usage in Templates:

```jinja2
{# Check current mode #}
{% if is_private %}
    <button>Edit Artwork</button>
{% endif %}

{# Generate mode-aware URLs #}
<a href="{{ mode_url_for('gallery') }}">Gallery</a>
```

### 3. Decorators (`decorators.py`)

Provides decorators for enforcing access control:

- **`@readonly_only`**: Ensures only GET and HEAD requests are allowed
- **`@require_cloudflare_access`**: Checks for Cloudflare Access authentication
- **`@inject_mode(mode)`**: Decorator factory for injecting mode information

#### Usage Example:

```python
from blueprints.decorators import readonly_only

@app.route('/public/gallery')
@readonly_only
def public_gallery():
    # This route will reject POST, PUT, DELETE requests
    return render_template('gallery.html')
```

## Configuration

The following configuration options have been added to `config.py`:

```python
# Dual-mode configuration
ENABLE_DUAL_MODE = True
DEFAULT_MODE = 'public'
REQUIRE_CF_ACCESS = False  # Whether to verify Cloudflare Access at app level

# Public mode restrictions
PUBLIC_MODE_RATE_LIMIT = '100/hour'
PUBLIC_MODE_ENABLE_SEARCH = True
```

## Integration with Main App

The context processors are automatically registered in `app.py`:

```python
from blueprints.context_processors import register_context_processors

app = Flask(__name__)
register_context_processors(app)
```

Teardown handlers have been added to properly close readonly database connections:

```python
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()
    # Close readonly connection if it exists
    db_readonly = getattr(g, '_database_readonly', None)
    if db_readonly is not None:
        db_readonly.close()
```

## Testing

Two test files verify the functionality:

1. **`test_db_readonly.py`**: Tests readonly database connections
   - Verifies connections can be established
   - Confirms read operations work
   - Ensures write operations are blocked
   - Checks PRAGMA query_only is set

2. **`test_context_processors.py`**: Tests context processors and mode injection
   - Verifies mode injection works correctly
   - Confirms template context is available
   - Tests mode_url_for() generates correct URLs

Run tests with:
```bash
python test_db_readonly.py
python test_context_processors.py
```

## Next Steps

With this infrastructure in place, the next tasks are:

1. Create the private blueprint (`blueprints/private.py`)
2. Create the public blueprint (`blueprints/public.py`)
3. Migrate existing routes to the appropriate blueprints
4. Update templates to use mode-aware features

## Requirements Satisfied

This implementation satisfies the following requirements from the design document:

- **Requirement 6.1**: Read-only database connections for public mode
- **Requirement 6.2**: Write operations blocked at database level
- **Requirement 6.3**: PRAGMA query_only configuration
- **Requirement 5.3**: Mode injection via Flask blueprints
- **Requirement 3.5**: Mode context available in templates
- **Requirement 9.3**: Mode-aware URL generation helper
