"""
Decorators for dual-mode gallery system.

This module provides decorators for enforcing access control and
mode-specific behavior in routes.
"""

from functools import wraps
from flask import request, abort, g, current_app
import logging

logger = logging.getLogger(__name__)


def readonly_only(f):
    """
    Decorator to enforce read-only access (GET and HEAD methods only).
    
    This decorator should be applied to routes that should only accept
    read operations. Any POST, PUT, DELETE, or other write methods
    will be rejected with a 403 Forbidden response.
    
    Usage:
        @app.route('/some-route')
        @readonly_only
        def some_route():
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method not in ['GET', 'HEAD']:
            logger.warning(
                f"Write operation attempted in read-only mode: "
                f"{request.method} {request.path}"
            )
            abort(403, description="Write operations are not allowed in this mode")
        return f(*args, **kwargs)
    return decorated_function


def require_cloudflare_access(f):
    """
    Decorator to require Cloudflare Access authentication.
    
    This decorator checks for the Cf-Access-Jwt-Assertion header
    which is set by Cloudflare Access when a user is authenticated.
    If the header is missing and REQUIRE_CF_ACCESS is enabled in config,
    the request is rejected with a 403 Forbidden response.
    
    Usage:
        @app.route('/private-route')
        @require_cloudflare_access
        def private_route():
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_app.config.get('REQUIRE_CF_ACCESS', False):
            cf_access_jwt = request.headers.get('Cf-Access-Jwt-Assertion')
            if not cf_access_jwt:
                from logger import logger as app_logger
                app_logger.app_logger.warning(
                    f"Authentication failure - Cloudflare Access JWT missing for: {request.path} "
                    f"from IP {request.remote_addr}"
                )
                app_logger.log_error(
                    f"Authentication failure - Missing Cloudflare Access authentication",
                    exc_info=False
                )
                abort(403, description="Authentication required")
            # TODO: Optionally verify JWT token here
        return f(*args, **kwargs)
    return decorated_function


def inject_mode(mode):
    """
    Decorator factory to inject mode information into Flask's g object.
    
    This decorator should be used in before_request handlers to set
    the current mode context.
    
    Args:
        mode (str): The mode to inject ('private' or 'public')
        
    Usage:
        @blueprint.before_request
        @inject_mode('private')
        def before_request():
            pass
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            g.mode = mode
            g.is_private = (mode == 'private')
            g.is_public = (mode == 'public')
            return f(*args, **kwargs)
        return decorated_function
    return decorator
