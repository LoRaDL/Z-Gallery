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
ENABLE_FULL_RES_CARD_IMAGES = False
