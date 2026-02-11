"""
Database utilities for dual-mode gallery system.

This module provides database connection functions and mode injection utilities
for the private and public mode blueprints.
"""

import sqlite3
from flask import g
import config


def get_db_readonly():
    """
    Get a read-only database connection.
    
    This connection is configured with SQLite's query_only pragma to prevent
    any write operations at the database level. Any attempt to execute
    INSERT, UPDATE, or DELETE statements will raise an OperationalError.
    
    Returns:
        sqlite3.Connection: A read-only database connection
    """
    db = getattr(g, '_database_readonly', None)
    if db is None:
        db = g._database_readonly = sqlite3.connect(config.DB_FILE)
        db.execute("PRAGMA query_only = ON")
        db.row_factory = sqlite3.Row
    return db


def get_comics_db_readonly():
    """
    Get a read-only comics database connection.
    
    Similar to get_db_readonly() but for the comics database.
    
    Returns:
        sqlite3.Connection: A read-only comics database connection
    """
    db = getattr(g, '_comics_database_readonly', None)
    if db is None:
        db = g._comics_database_readonly = sqlite3.connect("zootopia_comics.db")
        db.execute("PRAGMA query_only = ON")
        db.row_factory = sqlite3.Row
    return db


def inject_mode_info(mode):
    """
    Inject mode information into Flask's g object.
    
    This function should be called in a before_request handler to set
    the current mode context for the request.
    
    Args:
        mode (str): The mode to inject ('private' or 'public')
    """
    g.mode = mode
    g.is_private = (mode == 'private')
    g.is_public = (mode == 'public')
