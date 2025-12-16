# Z-Gallery
A self-hosted, AI-enhanced image archiving system built with Flask. Features metadata curation, visual deduplication, and batch analysis. Originally crafted for a 28k+ Zootopia fanarts.

# 项目来由
作为一个《疯狂动物城》粉丝，在有了大量的同人图收藏以后，我一直希望拥有一个能够打分，平时能够在电脑或手机上刷图的网页画廊，于是我制造了这个Z-gallery，后来还完善了图片导入自动提取信息，以及爬虫和数据清洗流水线。现在这套系统已经容纳了28k+张图片，并作为我日常的工具使用。有一些just for fun的细节打磨，比如主页卡片的超椭圆圆角，曲率连续使得观感赏心悦目。当然有一些细节没有打磨得很好，我将会根据个人需要，持续维护。

## 核心功能

### 智能画廊系统
- **瀑布流布局** - 响应式设计，支持多列自适应
- **多维度筛选** - 按艺术家、平台、分类、评分等筛选
- **智能排序** - 支持时间、评分、随机等多种排序方式

### AI增强功能
- **自动分类** - 使用本地LMstudio或Gemini API进行图片分类
- **智能标注** - AI生成描述和标签
- **内容分级** - 自动识别SFW/Mature/NSFW内容
- **视觉去重** - 基于感知哈希的相似图片检测

### 现代化体验
- **移动端优化** - 支持iOS Web App，触控友好
- **暗色主题** - 护眼的深色界面
- **漫画阅读器** - 专为连续作品设计的阅读模式

### 批量处理工具
- **社交媒体导入** - 支持Twitter等平台的批量下载
- **元数据管理** - 自动提取和管理作品信息
- **批量操作** - 支持批量评分、分类、标注等操作

## 快速开始

### 环境要求
- Python 3.8+
- 现代浏览器（支持ES6+）

### 安装运行

```bash
# 1. 克隆项目
git clone <repository-url>
cd z-gallery

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置API密钥（可选）
cp api_keys.example.py api_keys.py
# 编辑api_keys.py添加Gemini API密钥

# 4. 启动应用
python app.py
```

访问 `http://localhost:5000` 开始使用。

### 导入现有图片

如果你已有图片文件夹，可以使用gallery_manager快速导入：

```bash
# 从文件夹批量导入图片
python gallery_manager.py
```

gallery_manager会：
- 自动扫描IMAGES_ROOT_FOLDER（在config.py中配置）中的图片
- 提取基本元数据信息
- 生成缩略图等

## 主要工具

### 文件夹导入
```bash
# 导入本地图片文件夹
python gallery_manager.py
```
最简单的入库方式，适合导入现有的图片收藏。

### AI标注工具
```bash
python tools/ai_tagging_tool.py
```
使用AI为图片生成标题、标签和分类信息。

### Twitter批量导入
```bash
# 下载
python tools/batch_twitter/download.py https://twitter.com/artist_name

# 导入（支持LLM分类）
python tools/batch_twitter/import.py
```
专业的社交媒体内容采集工具。

### 数据库维护
```bash
# 生成缩略图和哈希
python tools/generate_hashes.py
python tools/check_and_fix_thumbnails.py

# 清理无效数据
python tools/clean_db.py
```

## 适用场景

- 个人艺术作品收藏管理
- 同人作品归档整理
- 设计素材库建设
- 图片资源批量处理

