# Z-Gallery

A self-hosted, AI-enhanced image archiving system built with Flask. Features metadata curation, visual deduplication, and batch analysis. Originally crafted for a 23k+ Zootopia fanarts.

## 功能特性

- 🖼️ 图片画廊浏览（支持多种排序方式）
- 🎨 瀑布流布局（响应式设计）
- ⭐ 评分系统（10星评级）
- 🏷️ AI自动标签（使用Gemini API）
- 🔍 图片搜索（按图搜图）
- 📱 iOS Web App优化
- 🎯 超椭圆圆角
- 📚 漫画阅读器

## 安装配置

### 1. 环境要求

- Python 3.8+
- Flask
- Pillow
- imagehash
- google-generativeai（用于AI标签）

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置API密钥

```bash
# 复制API密钥模板
cp api_keys.example.py api_keys.py

# 编辑api_keys.py，填入你的Gemini API密钥
```

### 4. 配置Gallery-dl（可选）

如果需要使用gallery-dl下载图片：

```bash
# 复制gallery-dl配置模板
cp -r gallery-dl.example gallery-dl

# 编辑gallery-dl/gallery-dl.conf，填入你的配置
# 添加必要的cookies文件
```

详见 `gallery-dl.example/README.md`

### 5. 运行应用

```bash
python app.py
```

访问 `http://localhost:5000`

## 工具脚本

所有工具脚本位于 `./tools` 目录：

- `ai_tagging_tool.py` - AI自动标签生成
- `generate_aspect_ratios.py` - 生成图片宽高比数据
- `generate_hashes.py` - 生成图片感知哈希
- `check_and_fix_thumbnails.py` - 检查和修复缩略图
- `clean_db.py` - 清理数据库中的无效记录
- `del_one_star.py` - 删除低评分图片

运行示例：
```bash
python tools/ai_tagging_tool.py
```

