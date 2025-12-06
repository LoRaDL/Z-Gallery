# Twitter 批量下载和导入工具

## 快速开始

### 1. 下载图片
```bash
python download.py <twitter_url>
```

**默认行为**：自动续传现有批次（如果存在）

示例：
```bash
# 第一次下载
python download.py https://twitter.com/artist_name
# → 创建新批次: artist_name_20241206_143022

# 再次运行（自动续传）
python download.py https://twitter.com/artist_name
# → 找到现有批次，继续下载到: artist_name_20241206_143022
# → 只下载新内容，跳过已下载的

# 强制创建新批次
python download.py https://twitter.com/artist_name --new
# → 创建新批次: artist_name_20241206_173045
```

### 2. 人工清洗
打开 `downloads/<目录名>/` 文件夹，删除不需要的图片。

### 3. 导入到数据库

**交互式导入（推荐）**：
```bash
python import.py
```
会列出所有批次，让你选择要导入哪个，并可选择是否检查相似图片。

**导入所有批次**：
```bash
python import.py --all
```

**导入指定批次**：
```bash
python import.py <目录名>
```

**跳过相似度检查**：
```bash
python import.py <目录名> --no-check
```

**自定义相似度阈值**：
```bash
python import.py <目录名> --threshold 15
```

示例：
```bash
# 交互式选择（会询问是否检查相似）
python import.py

# 导入所有（默认检查相似）
python import.py --all

# 导入指定批次（默认检查相似）
python import.py artist_name_20241206_143022

# 导入但不检查相似（快速模式）
python import.py artist_name_20241206_143022 --no-check

# 使用更宽松的阈值
python import.py artist_name_20241206_143022 --threshold 5

# 交互模式（询问用户）
python import.py artist_name_20241206_143022 --interactive
```

**相似度检查说明**：
- 默认阈值：1（几乎完全相同）
- 默认行为：自动跳过相似图片
- 使用 `--interactive` 参数可以在发现相似时询问：
  - `s` - 跳过当前图片
  - `k` - 保留并导入（可能重复）
  - `v` - 查看详细信息
  - `q` - 退出导入

## 高级用法

### 断点续传

```bash
# 自动续传（默认）
python download.py https://twitter.com/artist_name

# 续传指定批次
python download.py https://twitter.com/artist_name --resume artist_name_20241206_143022

# 创建新批次
python download.py https://twitter.com/artist_name --new

# 避免 rate limit（增加延迟）
python download.py https://twitter.com/artist_name --sleep 2.0
```

**关于 Rate Limit**：
- 默认延迟：1秒/请求（配置文件中设置）
- 如果遇到 rate limit，使用 `--sleep 2.0` 或更高
- 续传时也会请求 API 检查已下载的项目，建议加延迟

### 其他功能

```bash
# 列出所有下载批次
python download.py --list

# 预览导入（不实际导入）
python import.py <目录名> --preview

# 查看帮助
python import.py --help
```

## 工作流程

### 定期更新
```bash
# 每周运行一次，自动获取新内容
python download.py https://twitter.com/artist_name
# → 自动续传，只下载新图片

# 人工清洗

# 导入新内容
python import.py artist_name_20241206_143022
# → 自动跳过数据库中已存在的
```

## 目录结构

```
downloads/
├── artist_name_20241206_143022/
│   ├── .archive.txt          # gallery-dl断点记录
│   ├── 0001-abc123.jpg
│   ├── 0001-abc123.json
│   └── ...
└── search_zootopia_20241205_091234/
    └── ...
```

## 注意事项

- 下载的图片会自动添加标号，如 "Tweet content (1)", "Tweet content (2)"
- 导入时会自动检查重复（基于 platform + artist + title）
- 删除图片后对应的 JSON 文件也可以删除
- archive 文件用于断点续传，不要删除
