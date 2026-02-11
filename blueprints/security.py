"""
Security utilities for input validation and sanitization.

This module provides functions to detect and prevent common security threats:
- SQL injection attempts
- Path traversal attacks
- XSS attempts
"""

import re
from flask import abort, request
from logger import logger


# SQL injection patterns to detect
SQL_INJECTION_PATTERNS = [
    r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE|UNION|DECLARE)\b)",
    r"(--|;|\/\*|\*\/)",
    r"(\bOR\b.*=.*)",
    r"(\bAND\b.*=.*)",
    r"('|\"|`)(.*?)(\1)",
    r"(\bxp_|\bsp_)",
]

# Path traversal patterns to detect
PATH_TRAVERSAL_PATTERNS = [
    r"\.\.",
    r"(\/|\\)(etc|windows|system32|boot|proc)",
    r"(\.\.\/|\.\.\\)",
    r"(%2e%2e|%252e%252e)",
    r"(\.\.%2f|\.\.%5c)",
]


def validate_input(value, field_name="input", check_sql=True, check_path=True):
    """
    Validate user input for security threats.
    
    Args:
        value: The input value to validate
        field_name: Name of the field for logging purposes
        check_sql: Whether to check for SQL injection patterns
        check_path: Whether to check for path traversal patterns
    
    Returns:
        bool: True if input is safe, False otherwise
    
    Raises:
        400 Bad Request if malicious patterns are detected
    """
    if value is None:
        return True
    
    # Convert to string for pattern matching
    str_value = str(value).lower()
    
    # Check for SQL injection patterns
    if check_sql:
        for pattern in SQL_INJECTION_PATTERNS:
            if re.search(pattern, str_value, re.IGNORECASE):
                logger.app_logger.warning(
                    f"SQL injection attempt detected in {field_name}: {value} "
                    f"from IP {request.remote_addr if request else 'unknown'}"
                )
                logger.log_error(
                    f"Input validation failure - SQL injection pattern in {field_name}",
                    exc_info=False
                )
                abort(400, description="Invalid input detected")
    
    # Check for path traversal patterns
    if check_path:
        for pattern in PATH_TRAVERSAL_PATTERNS:
            if re.search(pattern, str_value, re.IGNORECASE):
                logger.app_logger.warning(
                    f"Path traversal attempt detected in {field_name}: {value} "
                    f"from IP {request.remote_addr if request else 'unknown'}"
                )
                logger.log_error(
                    f"Input validation failure - Path traversal pattern in {field_name}",
                    exc_info=False
                )
                abort(400, description="Invalid input detected")
    
    return True


def validate_artwork_id(artwork_id):
    """
    Validate artwork ID is a positive integer.
    
    Args:
        artwork_id: The artwork ID to validate
    
    Returns:
        bool: True if valid
    
    Raises:
        400 Bad Request if invalid
    """
    try:
        id_int = int(artwork_id)
        if id_int <= 0:
            logger.app_logger.warning(
                f"Invalid artwork ID: {artwork_id} from IP {request.remote_addr if request else 'unknown'}"
            )
            logger.log_error(f"Input validation failure - Invalid artwork ID: {artwork_id}", exc_info=False)
            abort(400, description="Invalid artwork ID")
        return True
    except (ValueError, TypeError):
        logger.app_logger.warning(
            f"Invalid artwork ID format: {artwork_id} from IP {request.remote_addr if request else 'unknown'}"
        )
        logger.log_error(f"Input validation failure - Invalid artwork ID format: {artwork_id}", exc_info=False)
        abort(400, description="Invalid artwork ID")


def validate_rating(rating):
    """
    Validate rating is between 1 and 10.
    
    Args:
        rating: The rating value to validate
    
    Returns:
        bool: True if valid
    
    Raises:
        400 Bad Request if invalid
    """
    try:
        rating_int = int(rating)
        if not (1 <= rating_int <= 10):
            logger.app_logger.warning(
                f"Invalid rating value: {rating} from IP {request.remote_addr if request else 'unknown'}"
            )
            logger.log_error(f"Input validation failure - Invalid rating: {rating}", exc_info=False)
            abort(400, description="Rating must be between 1 and 10")
        return True
    except (ValueError, TypeError):
        logger.app_logger.warning(
            f"Invalid rating format: {rating} from IP {request.remote_addr if request else 'unknown'}"
        )
        logger.log_error(f"Input validation failure - Invalid rating format: {rating}", exc_info=False)
        abort(400, description="Invalid rating format")


def validate_classification(classification):
    """
    Validate classification is one of the allowed values.
    
    Args:
        classification: The classification value to validate
    
    Returns:
        bool: True if valid
    
    Raises:
        400 Bad Request if invalid
    """
    allowed_values = ['sfw', 'mature', 'nsfw', 'unspecified', None]
    if classification not in allowed_values:
        logger.app_logger.warning(
            f"Invalid classification: {classification} from IP {request.remote_addr if request else 'unknown'}"
        )
        logger.log_error(f"Input validation failure - Invalid classification: {classification}", exc_info=False)
        abort(400, description="Invalid classification value")
    return True


def validate_category(category):
    """
    Validate category is one of the allowed values.
    
    Args:
        category: The category value to validate
    
    Returns:
        bool: True if valid
    
    Raises:
        400 Bad Request if invalid
    """
    allowed_values = ['fanart_comic', 'fanart_non_comic', 'real_photo', 'other']
    if category not in allowed_values:
        logger.app_logger.warning(
            f"Invalid category: {category} from IP {request.remote_addr if request else 'unknown'}"
        )
        logger.log_error(f"Input validation failure - Invalid category: {category}", exc_info=False)
        abort(400, description="Invalid category value")
    return True


def validate_field_name(field_name):
    """
    Validate field name for database updates.
    
    Args:
        field_name: The field name to validate
    
    Returns:
        bool: True if valid
    
    Raises:
        400 Bad Request if invalid
    """
    allowed_fields = [
        'title', 'artist', 'source_platform', 'description', 
        'tags', 'publication_date', 'ai_caption', 'ai_tags'
    ]
    if field_name not in allowed_fields:
        logger.app_logger.warning(
            f"Invalid field name: {field_name} from IP {request.remote_addr if request else 'unknown'}"
        )
        logger.log_error(f"Input validation failure - Invalid field name: {field_name}", exc_info=False)
        abort(400, description="Invalid field name")
    return True


def sanitize_filename(filename):
    """
    Sanitize filename to prevent path traversal.
    
    Args:
        filename: The filename to sanitize
    
    Returns:
        str: Sanitized filename
    """
    if not filename:
        return ""
    
    # Remove any path components
    filename = filename.replace('\\', '/').split('/')[-1]
    
    # Remove dangerous characters
    filename = re.sub(r'[^\w\s\-\.]', '', filename)
    
    # Check for path traversal attempts
    if '..' in filename or filename.startswith('.'):
        logger.app_logger.warning(
            f"Suspicious filename: {filename} from IP {request.remote_addr if request else 'unknown'}"
        )
        logger.log_error(f"Input validation failure - Suspicious filename: {filename}", exc_info=False)
        abort(400, description="Invalid filename")
    
    return filename


def validate_query_params(params):
    """
    Validate query parameters for gallery filtering.
    
    Args:
        params: Dictionary of query parameters
    
    Returns:
        bool: True if all params are valid
    """
    for key, value in params.items():
        # Skip empty values
        if not value:
            continue
        
        # Validate specific parameter types
        if key in ['page', 'columns', 'threshold']:
            try:
                int(value)
            except ValueError:
                logger.app_logger.warning(
                    f"Invalid integer parameter {key}: {value} from IP {request.remote_addr if request else 'unknown'}"
                )
                logger.log_error(f"Input validation failure - Invalid {key} parameter: {value}", exc_info=False)
                abort(400, description=f"Invalid {key} parameter")
        
        # Check for SQL injection in all string parameters
        validate_input(value, field_name=key, check_sql=True, check_path=False)
    
    return True
