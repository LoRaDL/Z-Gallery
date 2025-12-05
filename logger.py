"""
日志记录和监控系统
提供应用日志、性能监控、错误跟踪等功能
"""

import logging
import logging.handlers
import time
from functools import wraps
from flask import request, g
import json
from datetime import datetime
import psutil
import os

class GalleryLogger:
    def __init__(self):
        self.setup_loggers()
        self.performance_metrics = {}
        self.request_count = 0
        self.error_count = 0

    def setup_loggers(self):
        """设置不同的日志记录器"""
        # 应用日志
        self.app_logger = logging.getLogger('gallery_app')
        self.app_logger.setLevel(logging.INFO)

        # 错误日志
        self.error_logger = logging.getLogger('gallery_errors')
        self.error_logger.setLevel(logging.ERROR)

        # 访问日志
        self.access_logger = logging.getLogger('gallery_access')
        self.access_logger.setLevel(logging.INFO)

        # 性能日志
        self.perf_logger = logging.getLogger('gallery_performance')
        self.perf_logger.setLevel(logging.INFO)

        # 创建在logs目录下旋转的日志文件
        log_dir = 'logs'
        os.makedirs(log_dir, exist_ok=True)

        # 应用日志处理器
        app_handler = logging.handlers.RotatingFileHandler(
            f'{log_dir}/app.log', maxBytes=10*1024*1024, backupCount=5
        )
        app_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        self.app_logger.addHandler(app_handler)

        # 错误日志处理器
        error_handler = logging.handlers.RotatingFileHandler(
            f'{log_dir}/errors.log', maxBytes=10*1024*1024, backupCount=5
        )
        error_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s\n'
            'Request URL: %(request_url)s\n'
            'User Agent: %(user_agent)s\n'
            'Remote IP: %(remote_addr)s\n'
            'Stack Trace:\n%(custom_exc_text)s\n' + '-'*80
        )
        error_handler.setFormatter(error_formatter)
        self.error_logger.addHandler(error_handler)

        # 访问日志处理器
        access_handler = logging.handlers.RotatingFileHandler(
            f'{log_dir}/access.log', maxBytes=10*1024*1024, backupCount=5
        )
        access_formatter = logging.Formatter(
            '%(asctime)s - %(remote_addr)s - "%(request_line)s" %(status_code)s %(response_time)sms'
        )
        access_handler.setFormatter(access_formatter)
        self.access_logger.addHandler(access_handler)

        # 性能日志处理器
        perf_handler = logging.handlers.RotatingFileHandler(
            f'{log_dir}/performance.log', maxBytes=10*1024*1024, backupCount=5
        )
        perf_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(message)s'
        ))
        self.perf_logger.addHandler(perf_handler)

    def log_request(self, status_code, response_time):
        """记录访问请求"""
        self.request_count += 1
        
        # 跳过从image_wall页面发起的静态资源请求
        if request:
            referer = request.headers.get('Referer', '')
            # 如果是静态资源请求且来自image_wall页面，跳过日志
            if request.endpoint in ['static', 'image_proxy'] and '/image-wall' in referer:
                return
            
        extra = {
            'remote_addr': request.remote_addr if request else 'N/A',
            'request_line': f"{request.method} {request.path} HTTP/1.1" if request else 'N/A',
            'status_code': status_code,
            'response_time': f"{response_time:.2f}"
        }
        self.access_logger.info('Request completed', extra=extra)

    def log_error(self, message, exc_info=None):
        """记录错误"""
        self.error_count += 1
        extra = {
            'request_url': request.url if request else 'N/A',
            'user_agent': request.headers.get('User-Agent', 'N/A') if request else 'N/A',
            'remote_addr': request.remote_addr if request else 'N/A',
            'custom_exc_text': str(exc_info) if exc_info else ''
        }
        self.error_logger.error(message, extra=extra, exc_info=exc_info)

    def log_performance(self, operation, duration, **kwargs):
        """记录性能信息"""
        message = json.dumps({
            'operation': operation,
            'duration_ms': duration,
            'timestamp': datetime.now().isoformat(),
            **kwargs
        })
        self.perf_logger.info(message)

    def get_system_info(self):
        """获取系统信息"""
        try:
            return {
                'cpu_percent': psutil.cpu_percent(interval=1),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_usage': psutil.disk_usage('.').percent,
                'process_count': len(psutil.pids())
            }
        except:
            return {'error': 'Unable to get system info'}

    def get_monitoring_data(self):
        """获取监控数据"""
        return {
            'requests_total': self.request_count,
            'errors_total': self.error_count,
            'error_rate': (self.error_count / self.request_count * 100) if self.request_count > 0 else 0,
            'uptime_seconds': time.time() - getattr(self, 'start_time', time.time()),
            'system_info': self.get_system_info(),
            'timestamp': datetime.now().isoformat()
        }

# 创建全局日志实例
logger = GalleryLogger()
logger.start_time = time.time()

def performance_monitor(operation_name):
    """性能监控装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000  # 转换为毫秒

                # 记录性能信息
                extra_data = {
                    'function': func.__name__,
                    'module': func.__module__
                }
                if duration > 1000:  # 如果超过1000ms，记录为慢查询
                    logger.perf_logger.warning(
                        f"Slow operation: {operation_name} took {duration:.2f}ms, "
                        f"function={func.__name__}"
                    )

                logger.log_performance(operation_name, duration, **extra_data)
                return result
            except Exception as e:
                duration = (time.time() - start_time) * 1000
                logger.log_performance(operation_name, duration, error=str(e))
                raise
        return wrapper
    return decorator

def log_request_details():
    """记录请求详细信息"""
    if request:
        # 跳过从image_wall页面发起的静态资源请求
        referer = request.headers.get('Referer', '')
        if request.endpoint in ['static', 'image_proxy'] and '/image-wall' in referer:
            return
            
        logger.app_logger.info(f"Request: {request.method} {request.url} "
                             f"User-Agent: {request.headers.get('User-Agent', 'N/A')}")
        if request.form:
            logger.app_logger.debug(f"Form data keys: {list(request.form.keys())}")
        if request.files:
            logger.app_logger.debug(f"Uploaded files: {list(request.files.keys())}")

def error_handler_decorator(func):
    """错误处理装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.log_error(f"Unhandled error in {func.__name__}: {str(e)}", exc_info=True)
            raise
    return wrapper

# 用于Flask应用的便捷方法
def init_app_logging(app):
    """初始化Flask应用日志"""
    @app.before_request
    def before_request_logging():
        g.request_start_time = time.time()
        log_request_details()

    @app.after_request
    def after_request_logging(response):
        if hasattr(g, 'request_start_time'):
            response_time = (time.time() - g.request_start_time) * 1000
            logger.log_request(response.status_code, response_time)
        return response

    @app.errorhandler(Exception)
    def global_error_handler(error):
        logger.log_error(f"Flask error: {str(error)}", exc_info=True)
        return {"error": "Internal Server Error"}, 500
