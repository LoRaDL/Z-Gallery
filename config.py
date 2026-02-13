# 1. 数据库文件名
DB_FILE = "zootopia_gallery.db"

# 2. 支持的图片文件扩展名
SUPPORTED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', 'bmp')

# 3. 统一的图片收藏根目录
IMAGES_ROOT_FOLDER = "./zootopia_pics"

# 4. gallery-dl 配置文件路径
GALLERY_DL_CONFIG_PATH = "./gallery-dl/gallery-dl.conf"

# 5. 图像处理相关配置
THUMBNAIL_SIZE = (400, 400)
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
# 强制应用的过滤器（不在 URL 中显示）
PUBLIC_MODE_FORCED_FILTERS = {
    'classification_filter': 'sfw'  # 仅显示 SFW 内容
}
