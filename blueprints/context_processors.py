"""
Context processors for dual-mode gallery system.

This module provides template context processors that inject mode information
and URL generation helpers into all templates.
"""

from flask import g, url_for


def inject_mode_context():
    """
    Inject mode information into template context.
    
    This context processor makes the current mode available to all templates
    through the 'mode', 'is_private', and 'is_public' variables.
    
    Returns:
        dict: Dictionary containing mode information
    """
    return {
        'mode': getattr(g, 'mode', 'public'),
        'is_private': getattr(g, 'is_private', False),
        'is_public': getattr(g, 'is_public', True)
    }


def inject_url_helpers():
    """
    Inject URL generation helper functions into template context.
    
    This context processor provides the mode_url_for() function which
    generates URLs that maintain the current mode context.
    
    Returns:
        dict: Dictionary containing URL helper functions
    """
    def mode_url_for(endpoint, **values):
        """
        Generate a URL for the given endpoint in the current mode.
        
        This function automatically prefixes the endpoint with the current
        mode's blueprint name (private. or public.) to ensure navigation
        stays within the same mode.
        
        Args:
            endpoint (str): The endpoint name (without blueprint prefix)
            **values: Additional URL parameters
            
        Returns:
            str: The generated URL
        """
        current_mode = getattr(g, 'mode', 'public')
        
        # If endpoint already has a blueprint prefix, use it as-is
        if '.' in endpoint:
            return url_for(endpoint, **values)
        
        # List of endpoints that should NOT be prefixed (they're in main app, not blueprints)
        non_blueprint_endpoints = [
            'monitoring', 'api_monitoring', 'api_logs', 'api_logs_download',
            'api_artists', 'api_platforms', 'add_artwork_page', 'api_add_artwork',
            'api_get_similar_ids', 'api_delete_artwork', 'api_get_similar_ids_by_id',
            'find_similar', 'api_fetch_metadata', 'temp_image', 'api_update_artwork_field',
            'api_get_next_image', 'api_get_previous_image',
            'comics_thumbnail', 'comic_page', 'image_proxy',
            'static'
        ]
        
        # If endpoint is in the non-blueprint list, don't add prefix
        if endpoint in non_blueprint_endpoints:
            return url_for(endpoint, **values)
        
        # Otherwise, add the current mode's blueprint prefix
        if current_mode == 'private':
            endpoint = f'private.{endpoint}'
        else:
            endpoint = f'public.{endpoint}'
        
        return url_for(endpoint, **values)
    
    return {'mode_url_for': mode_url_for}


def register_context_processors(app):
    """
    Register all context processors with the Flask app.
    
    Args:
        app: The Flask application instance
    """
    app.context_processor(inject_mode_context)
    app.context_processor(inject_url_helpers)
