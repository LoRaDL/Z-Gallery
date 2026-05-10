# 1. 数据库文件名
DB_FILE = "zootopia_gallery.db"

# 2. 支持的图片文件扩展名
SUPPORTED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', 'bmp')

# 3. 统一的图片收藏根目录
IMAGES_ROOT_FOLDER = "./zootopia_pics"

# 4. gallery-dl 配置文件路径
GALLERY_DL_CONFIG_PATH = "./gallery-dl/gallery-dl.conf"

# 5. 图像处理相关配置
THUMBNAIL_SIZE = (600, 2000)
THUMBNAIL_QUALITY = 85
MAX_SIMILAR_RESULTS = 50
DEFAULT_SEARCH_THRESHOLD = 10

# 6. 页面显示配置
IMAGES_PER_PAGE = 24

# 7. 路径配置
THUMBNAIL_DIR = "static/thumbnails"
TEMP_UPLOADS_DIR = "temp_uploads"
STATIC_DIR = "static"

# 8. 图片显示配置
ENABLE_FULL_RES_CARD_IMAGES = True

# 9. 双模式配置
ENABLE_DUAL_MODE = True
DEFAULT_MODE = 'public'
REQUIRE_CF_ACCESS = False  # 是否在应用层验证 Cloudflare Access

# 10. 公开模式限制
PUBLIC_MODE_RATE_LIMIT = '100/hour'  # 速率限制
PUBLIC_MODE_ENABLE_SEARCH = True  # 是否启用搜索功能

# 11. 公开模式内容过滤
# 灵活的公开模式过滤配置，包含两类规则：
#
# query_filters: 直接注入查询的字段过滤器（与私有模式过滤器语法一致）
#   支持的键: classification_filter ('sfw'|'mature'|'nsfw'|'unspecified')
#             artist, source_platform, category, rating_filter
#
# exclude_rules: 排除规则列表，每条规则包含若干字段条件，
#   所有条件同时满足时该作品不在公开模式展示。
#   每条规则格式:
#     {
#       'description': '规则说明（可选）',
#       'conditions': [
#           {'field': '字段名', 'op': '操作符', 'value': '值'},
#           ...  # 多个条件之间为 AND 关系
#       ]
#     }
#   支持的操作符:
#     'eq'       字段等于值
#     'neq'      字段不等于值
#     'is_null'  字段为 NULL（value 忽略）
#     'not_null' 字段不为 NULL（value 忽略）
#     'like'     字段 LIKE 值（支持 % 通配符）
#
PUBLIC_MODE_FORCED_FILTERS = {
    'query_filters': {},
    'exclude_rules': [
        {
            'description': '作者 greenpurrpleD 且无原始链接时不展示',
            'conditions': [
                {'field': 'artist', 'op': 'eq', 'value': 'greenpurrpleD'},
                {'field': 'source_url', 'op': 'is_null'},
            ]
        },
        {
            'description': '分类为 real_photo 的不在公开模式展示',
            'conditions': [
                {'field': 'category', 'op': 'eq', 'value': 'real_photo'},
            ]
        },
        {
            'description': '分类为 other 的不在公开模式展示',
            'conditions': [
                {'field': 'category', 'op': 'eq', 'value': 'other'},
            ]
        },
        {
            'description': 'mature 内容不在公开模式展示',
            'conditions': [
                {'field': 'classification', 'op': 'eq', 'value': 'mature'},
            ]
        },
        {
            'description': 'nsfw 内容不在公开模式展示',
            'conditions': [
                {'field': 'classification', 'op': 'eq', 'value': 'nsfw'},
            ]
        },
        {
            'description': '未分类内容不在公开模式展示',
            'conditions': [
                {'field': 'classification', 'op': 'is_null'},
            ]
        },
    ]
}
