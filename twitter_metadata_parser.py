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
    
    # 自动添加标号逻辑
    if title:
        is_multi = (is_multi_image_post is True) or (total_images and total_images > 1)
        if is_multi and image_position:
            if not re.search(r'\s*\(\d+\)\s*$', title):
                title = f"{title} ({image_position})"
    
    # 提取标签
    tags_list = data.get('hashtags', []) or data.get('tags', [])
    tags = ", ".join(tags_list) if isinstance(tags_list, list) else ''
    
    # 分类
    classification = 'nsfw' if data.get('sensitive') else 'sfw'
    
    # 日期
    publication_date = data.get('date')
    
    # 构造推文原始链接
    # gallery-dl JSON 中没有直接的 tweet URL，需要从 tweet_id + author.name 构造
    # 多图帖子加 /photo/{num} 精确定位到具体那张图
    source_url = data.get('url')
    if not source_url:
        tweet_id = data.get('tweet_id') or data.get('post_id')
        username = None
        if isinstance(author_info, dict):
            username = author_info.get('name')
        if not username:
            username = data.get('username')
        if tweet_id and username:
            is_multi = (is_multi_image_post is True) or (total_images and total_images > 1)
            if is_multi and image_position:
                source_url = f"https://x.com/{username}/status/{tweet_id}/photo/{image_position}"
            else:
                source_url = f"https://x.com/{username}/status/{tweet_id}"

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
