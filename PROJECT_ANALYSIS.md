# Zootopia Gallery Manager - 项目分析文档

## 项目概述

Zootopia Gallery Manager 是一个基于 Flask 的 Web 应用程序，用于管理和展示 Zootopia（疯狂动物城）主题的艺术作品收藏。该系统提供了完整的画廊浏览、搜索、评分、分类等功能，并集成了外部元数据获取能力。

## 技术架构

### 核心技术栈
- **后端框架**: Flask (Python)
- **数据库**: SQLite
- **前端模板**: Jinja2
- **图像处理**: PIL (Pillow)
- **外部集成**: gallery-dl (用于元数据获取)
- **前端交互**: jQuery + 原生 JavaScript
- **样式**: 自定义 CSS

### 系统架构图
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Browser   │    │    Flask App    │    │   SQLite DB     │
│                 │    │                 │    │                 │
│ - HTML/CSS/JS   │◄──►│ - Routes        │◄──►│ - artworks      │
│ - AJAX Calls    │    │ - Templates     │    │ - metadata      │
│ - Form Submit   │    │ - Business Logic│    │ - thumbnails    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │  File System    │
                       │                 │
                       │ - Images        │
                       │ - Thumbnails    │
                       │ - Temp uploads  │
                       └─────────────────┘
```

## 核心功能模块

### 1. 画廊浏览系统 (Gallery Browsing)

**主要路由**: `/` (gallery)
**功能特性**:
- 网格布局展示艺术作品缩略图
- 支持多种排序方式：评分、发布时间、最新添加、随机
- 分页显示 (每页24张图片)
- 多种筛选器：艺术家、平台、分类、评分、内容分级

**核心逻辑**:
```python
# 排序映射
sort_map = {
    'rating': 'rating DESC, publication_date DESC',
    'newest': 'publication_date DESC',
    'oldest': 'publication_date ASC',
    'latest_added': 'last_modified_date DESC'
}
```

### 2. 艺术作品详情页 (Artwork Details)

**主要路由**: `/artwork/<id>`
**功能特性**:
- 显示完整尺寸图片
- 展示元数据：艺术家、平台、标签、描述、发布时间
- 评分系统 (1-10分)
- 内容分类 (SFW/Mature/NSFW)
- 相似图片推荐 (基于感知哈希)

### 3. 搜索与过滤系统 (Search & Filtering)

**功能特性**:
- 文本搜索：标题、艺术家、标签、描述
- 图搜图：基于感知哈希的图像相似度搜索
- 组合筛选：支持多个筛选条件同时应用
- 随机排序：基于时间戳种子的伪随机算法

**搜索实现**:
```sql
WHERE (title LIKE ? OR artist LIKE ? OR tags LIKE ?)
```

### 4. 元数据获取系统 (Metadata Fetching)

**核心文件**: `metadata_fetcher.py`
**功能特性**:
- 集成 gallery-dl 工具
- 支持 Twitter、DeviantArt、e-hentai 等平台
- 智能元数据提取和解析
- 多图帖子处理
- 自动内容分级检测

**处理流程**:
1. 使用 gallery-dl 下载图片到临时目录
2. 获取 JSON 格式的元数据
3. 解析和转换元数据字段
4. 返回结构化数据

### 5. 文件上传与处理 (File Upload & Processing)

**主要路由**: `/add`, `/api/add_artwork`
**功能特性**:
- 支持多种图片格式 (JPG, PNG, GIF, WebP)
- 自动缩略图生成 (400x400, 85%质量)
- 元数据提取和存储
- 文件验证和错误处理

### 6. 统计与分析 (Statistics & Analytics)

**主要路由**: `/statistics`, `/api/statistics/*`
**功能特性**:
- 艺术家排名 (基于平均评分和作品数量)
- 平台统计
- 时间分布分析
- 评分分布图表

### 7. 幻灯片浏览 (Slide View)

**主要路由**: `/slide_view`, `/api/get_next_image`
**功能特性**:
- 连续浏览体验
- 键盘快捷键支持
- AJAX 动态加载
- URL 状态保持

## 数据库设计

### Artworks 表结构
```sql
CREATE TABLE artworks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    artist TEXT,
    source_platform TEXT,
    category TEXT,
    tags TEXT,
    description TEXT,
    publication_date TEXT,
    rating INTEGER,
    classification TEXT,
    phash TEXT,
    file_path TEXT,
    thumbnail_path TEXT,
    last_modified_date TEXT
);
```

### 关键字段说明
- **phash**: 感知哈希值，用于图像相似度搜索
- **classification**: 内容分级 (sfw/mature/nsfw)
- **source_platform**: 来源平台 (twitter, deviantart, etc.)
- **category**: 自定义分类标签

## 配置与工具模块

### 配置文件 (config.py)
```python
# 数据库和路径配置
DB_FILE = "zootopia_gallery.db"
IMAGES_ROOT_FOLDER = "./zootopia_pics"
THUMBNAIL_SIZE = (400, 400)

# 功能配置
IMAGES_PER_PAGE = 24
MAX_SIMILAR_RESULTS = 50
DEFAULT_SEARCH_THRESHOLD = 10
```

### 工具函数 (utils.py)
- **日期解析**: 优先级策略 (EXIF → 文件名 → 文件系统时间)
- **缩略图生成**: 标准化的图片处理函数
- **查询构建器**: 动态 SQL 查询构造
- **随机排序**: 基于种子的排序算法

## 前端架构

### 模板继承结构
```
layout.html (基础模板)
├── gallery.html (画廊页面)
├── artwork_detail.html (详情页)
├── statistics.html (统计页)
├── slide_view.html (幻灯片)
├── categories.html (分类页)
├── add_artwork.html (上传页)
└── comics.html (漫画页面)
```

### JavaScript 功能
- **main.js**: 通用交互和 AJAX 调用
- **image_search.js**: 图搜图功能
- **detail_page.js**: 详情页交互
- **statistics.js**: 图表渲染和数据可视化
- **slide_view.js**: 幻灯片导航

## API 接口

### RESTful API 端点
- `GET /api/statistics/artist_ranking` - 艺术家排名
- `GET /api/statistics/platform_stats` - 平台统计
- `GET /api/get_next_image` - 下一张图片 (幻灯片)
- `POST /api/add_artwork` - 添加艺术作品

### AJAX 交互
- 评分提交
- 分类更新
- 动态内容加载
- 表单验证

## 性能优化

### 数据库优化
- 使用索引优化查询性能
- 分页查询避免大结果集
- 连接池管理

### 图像处理优化
- 延迟缩略图生成
- 缓存机制
- 批量处理

### 前端优化
- 懒加载图片
- AJAX 分页
- 最小化资源请求

## 安全考虑

### 输入验证
- 文件类型检查
- 路径遍历防护
- SQL 注入防护 (使用参数化查询)

### 内容安全
- 自动 NSFW 检测
- 用户内容分类
- 访问控制

## 部署与维护

### 系统要求
- Python 3.7+
- SQLite 3
- gallery-dl
- PIL/Pillow

### 目录结构
```
zootopia_gallery/
├── app.py                 # 主应用
├── config.py             # 配置
├── utils.py              # 工具函数
├── metadata_fetcher.py   # 元数据获取
├── templates/            # HTML 模板
├── static/               # 静态资源
│   ├── css/
│   ├── js/
│   └── thumbnails/
├── zootopia_pics/        # 原图存储
├── temp_uploads/         # 临时上传
└── zootopia_gallery.db   # 数据库
```

## 扩展性设计

### 模块化架构
- 独立的业务逻辑模块
- 可插拔的元数据提供者
- 灵活的筛选器系统

### API 设计
- RESTful 接口设计
- JSON 数据格式
- 错误处理标准化

## 总结

Zootopia Gallery Manager 是一个功能完整、架构清晰的 Web 应用程序，成功整合了多个技术领域：

- **Web 开发**: Flask 框架，模板渲染，AJAX 交互
- **数据管理**: SQLite 数据库，查询优化，数据完整性
- **图像处理**: 缩略图生成，格式转换，相似度搜索
- **外部集成**: gallery-dl 工具，元数据解析，多平台支持
- **用户体验**: 响应式设计，流畅的浏览体验，多种交互方式

该项目展示了现代 Web 应用开发的多个最佳实践，是一个优秀的学习和参考案例。
