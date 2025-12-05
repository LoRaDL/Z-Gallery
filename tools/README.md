# 工具脚本说明

## generate_aspect_ratios.py

生成图片宽高比数据库，用于图墙页面的占位符优化。

### 功能

- 遍历所有图片，计算宽高比
- 将宽高比数据存储到独立的 `aspect_ratios.db` 数据库
- 不修改主数据库结构

### 使用方法

```bash
# 首次运行，生成所有图片的宽高比数据
python tools/generate_aspect_ratios.py

# 强制更新所有记录（包括已存在的）
python tools/generate_aspect_ratios.py --force

# 仅显示统计信息
python tools/generate_aspect_ratios.py --stats
```

### 工作原理

1. 创建独立的 `aspect_ratios.db` 数据库
2. 从主数据库读取所有图片路径
3. 使用 PIL 读取图片尺寸
4. 计算宽高比（width / height）
5. 存储到宽高比数据库

### 数据库结构

```sql
CREATE TABLE aspect_ratios (
    artwork_id INTEGER PRIMARY KEY,
    aspect_ratio REAL NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### 性能优化

- 图墙页面加载时，使用宽高比创建占位符
- 防止图片加载时页面布局抖动
- 减少浏览器重排（reflow）次数
- 如果图片没有宽高比数据，使用默认值 1:1

### 注意事项

- 脚本只在手动运行时更新数据
- 新添加的图片不会自动记录宽高比
- 需要定期运行脚本更新数据
- 如果图片文件不存在，会跳过并记录错误
