"""
Twitter元数据解析器
供 metadata_fetcher.py 和 batch_twitter/import.py 共用
"""

import re


def parse_twitter_metadata(data, image_position=None, total_images=None, is_multi_image_post=None):
    """
    解析Twitter/gallery-dl的JSON元数据
    
    参数:
        data: dict - gallery-dl的JSON数据
        image_position: int - 当前图片位置（可选，用于标号）
        total_images: int - 总图片数（可选，用于标号）
        is_multi_image_post: bool - 是否是多图帖子（可选，用于单图下载场景）
    
    返回:
        dict - 标准化的元数据
    """
    
    # 提取作者信息
    author_info = data.get('author', {}) or data.get('user', {})
    artist = None
    if isinstance(author_info, dict):
        artist = author_info.get('name') or author_info.get('nick')
    if not artist:
        artist = data.get('username')
    
    # 提取平台
    platform_str = data.get('category') or data.get('extractor', '')
    platform = platform_str.split(':')[0] if platform_str else 'twitter'
    
    # 提取描述
    description = data.get('content') or data.get('description') or ''
    
    # 提取标题
    title = data.get('title')
    if not title and description:
        # 从描述提取标题（去除hashtag）
        clean_desc = re.sub(r'#\w+\s*', '', description).strip()
        if clean_desc:  # 确保不是空字符串
            title = clean_desc.split('\n')[0][:200]
    
    # 如果还是没有标题，使用默认值
    if not title:
        title = f"Untitled ({data.get('tweet_id', 'unknown')})"
    
    # 自动添加标号逻辑（与metadata_fetcher.py保持一致）
    if title:
        # 情况1：明确是多图帖子（批量下载或单图下载多图帖子）
        if is_multi_image_post is True and image_position:
            if not re.search(r'\s*\(\d+\)\s*$', title):
                title = f"{title} ({image_position})"
        # 情况2：通过count判断是多图帖子
        elif total_images and total_images > 1 and image_position:
            if not re.search(r'\s*\(\d+\)\s*$', title):
                title = f"{title} ({image_position})"
        # 情况3：单图下载，但检测到帖子实际有多图，添加(1)
        # 这种情况：用户只下载了第一张，但total_images显示帖子有多张
        elif is_multi_image_post is False and total_images and total_images > 1 and image_position == 1:
            if not re.search(r'\s*\(\d+\)\s*$', title):
                title = f"{title} (1)"
    
    # 提取标签
    tags_list = data.get('hashtags', []) or data.get('tags', [])
    tags = ", ".join(tags_list) if isinstance(tags_list, list) else ''
    
    # 分类
    classification = 'nsfw' if data.get('sensitive') else 'sfw'
    
    # 日期
    publication_date = data.get('date')
    
    # URL
    source_url = data.get('url')
    
    return {
        'artist': artist,
        'platform': platform,
        'title': title,
        'tags': tags,
        'description': description.strip(),
        'classification': classification,
        'publication_date': publication_date,
        'source_url': source_url
    }
