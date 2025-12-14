# Z-Gallery
A self-hosted, AI-enhanced image archiving system built with Flask. Features metadata curation, visual deduplication, and batch analysis. Originally crafted for a 23k+ Zootopia fanarts.

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

## 主要工具

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

### 数据库维护
```bash
# 生成缩略图和哈希
python tools/generate_hashes.py
python tools/check_and_fix_thumbnails.py

# 清理无效数据
python tools/clean_db.py
```

## 技术特色

- **Flask后端** - 轻量级Python Web框架
- **SQLite数据库** - 零配置的嵌入式数据库
- **响应式前端** - 原生JavaScript，无框架依赖
- **AI集成** - 支持本地和云端AI模型
- **模块化设计** - 工具脚本独立，易于扩展

## 适用场景

- 个人艺术作品收藏管理
- 同人作品归档整理
- 设计素材库建设
- 图片资源批量处理
- AI辅助内容审核

