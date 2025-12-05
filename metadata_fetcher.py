import sys
import json
import re
import os
import subprocess
import config
import argparse

def fix_surrogates(obj):
    """递归修复字符串中破碎的代理对"""
    if isinstance(obj, str):
        return obj.encode('utf-16', 'surrogatepass').decode('utf-16')
    elif isinstance(obj, dict):
        return {k: fix_surrogates(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [fix_surrogates(i) for i in obj]
    return obj

def find_downloaded_filename(stdout_str):
    """从gallery-dl的下载输出中健壮地解析出实际的文件名。"""
    for line in stdout_str.strip().split('\n'):
        if 'temp_uploads' in line.replace('\\', '/'):
            return os.path.basename(line.strip())
    return None

def fetch_and_parse(url, proxy=None, debug=False):
    """
    核心函数：精确下载图片，智能合并元数据，并正确提取所有关键字。
    """
    try:
        # --- 1. 精确下载 ---
        target_photo_num = 1
        filter_option = []
        match = re.search(r'/photo/(\d+)', url)
        if match:
            target_photo_num = int(match.group(1))
            filter_option = ['--filter', f"num == {target_photo_num}"]
        
        # 检测是否为多图帖子
        is_multi_image_post = False
        total_images_in_post = 1
        
        # 优先使用URL中的photo参数确定图片位置
        url_based_position = target_photo_num if match else 1

        # 构建基础命令
        base_download_options = ['gallery-dl', '--directory', './temp_uploads', '--config', config.GALLERY_DL_CONFIG_PATH]
        base_metadata_options = ['gallery-dl', '-q', '--dump-json', '--no-download', '--config', config.GALLERY_DL_CONFIG_PATH]

        # 如果提供了代理，添加到命令中
        if proxy:
            proxy_option = ['--proxy', proxy]
            download_command = base_download_options + proxy_option + filter_option + [url]
            metadata_command = base_metadata_options + proxy_option + [url]
        else:
            download_command = base_download_options + filter_option + [url]
            metadata_command = base_metadata_options + [url]

        dl_result = subprocess.run(download_command, capture_output=True, text=True, check=True, timeout=60)

        downloaded_filename = find_downloaded_filename(dl_result.stdout)
        if not downloaded_filename:
            raise ValueError("Could not determine downloaded filename.")

        # --- 2. 获取所有元数据 ---
        meta_result = subprocess.run(metadata_command, capture_output=True, text=True, check=True, timeout=30)
        
        # --- 3. 检测多图帖子信息 ---
        data_list = json.loads(meta_result.stdout, strict=False)
        all_dicts = [d for item in data_list if isinstance(item, list) for d in item if isinstance(d, dict)]
        
        # 计算帖子中的总图片数量
        media_entries = [meta for meta in all_dicts if meta.get('filename')]
        total_images_in_post = len(media_entries)
        is_multi_image_post = total_images_in_post > 1
        
        # 确定当前图片在帖子中的位置
        # 优先使用URL中的photo参数，如果URL中没有则使用元数据检测
        if url_based_position > 1:
            # URL明确指定了图片位置，直接使用
            current_image_position = url_based_position
            # 如果URL指定了位置，通常意味着这是多图帖子
            is_multi_image_post = True
        else:
            # URL没有指定位置，使用元数据检测
            current_image_position = 1
            if is_multi_image_post:
                # 找到当前下载的图片在媒体列表中的位置
                for i, meta in enumerate(media_entries):
                    if meta.get('filename') == os.path.splitext(downloaded_filename)[0]:
                        current_image_position = i + 1
                        break
        
        # --- 4. 智能合并元数据 (最终修正版) ---
        content_block = {}
        media_block = {}

        # 找到内容块 (通常是推文本身)
        for meta in all_dicts:
            if 'content' in meta or 'hashtags' in meta:
                content_block = meta
                break # 假设只有一个主要的内容块

        # 找到与下载文件匹配的媒体块
        filename_key = os.path.splitext(downloaded_filename)[0]
        for meta in all_dicts:
            if meta.get('filename') == filename_key:
                media_block = meta
                break
        
        # 智能合并: 以内容块为基础，用媒体块的信息来补充
        final_meta = content_block.copy() # 创建一个副本
        final_meta.update(media_block)    # 用媒体块更新它

        if not final_meta:
            raise ValueError("No suitable metadata found.")

        # --- 4. 提取关键字 (最终修正版) ---
        metadata = fix_surrogates(final_meta)
        
        extracted_data = {
            'artist': None, 'platform': None, 'title': None,
            'tags': '', 'description': '', 'classification': 'sfw',
            'publication_date': None # <-- 新增：为日期准备一个位置
        }

        # 作者, 平台, 标签 (逻辑无变化)
        author_info = metadata.get('author', {}) or metadata.get('user', {})
        if isinstance(author_info, dict): extracted_data['artist'] = author_info.get('name')
        if not extracted_data.get('artist'): extracted_data['artist'] = metadata.get('username')
        
        platform_str = metadata.get('category') or metadata.get('extractor', '')
        extracted_data['platform'] = platform_str.split(':')[0]

        tags_list = metadata.get('hashtags', []) or metadata.get('tags', [])
        if isinstance(tags_list, list): extracted_data['tags'] = ", ".join(tags_list)

        # 描述 (现在只提取纯粹的描述)
        description = metadata.get('content') or metadata.get('description') or ''
        extracted_data['description'] = description.strip()

        # 标题 (基于原始描述提取)
        title = metadata.get('title')
        if not title and description:
            clean_desc = re.sub(r'#\w+\s*', '', description).strip()
            extracted_data['title'] = clean_desc.split('\n')[0]
        else:
            extracted_data['title'] = title
        
        # 自动添加标号逻辑
        if extracted_data['title']:
            # 如果帖子有多张图片，自动添加标号
            if is_multi_image_post:
                # 检查标题是否已经有标号（支持括号格式）
                if not re.search(r'\s*\(\d+\)\s*$', extracted_data['title']):
                    extracted_data['title'] = f"{extracted_data['title']} ({current_image_position})"
            # 如果帖子只有一张图片，但检测到是多图帖子的一部分，添加标号1
            elif total_images_in_post > 1 and current_image_position == 1:
                if not re.search(r'\s*\(\d+\)\s*$', extracted_data['title']):
                    extracted_data['title'] = f"{extracted_data['title']} (1)"
            
        # --- 5. 应用自定义逻辑 (核心修正) ---
        # 读取日期字符串并放入独立字段
        date_str = metadata.get('date')
        if date_str:
            extracted_data['publication_date'] = date_str
        
        if metadata.get('sensitive') is True:
            extracted_data['classification'] = 'nsfw'

        # --- 6. 最终输出 ---
        final_output = { 
            "data": extracted_data, 
            "temp_path": downloaded_filename,
            "image_info": {
                "is_multi_image_post": is_multi_image_post,
                "total_images_in_post": total_images_in_post,
                "current_image_position": current_image_position
            }
        }
        print(json.dumps(final_output))

    except Exception as e:
        error_message = f"Error in metadata_fetcher.py: {e}"
        if isinstance(e, subprocess.CalledProcessError):
            error_message += f"\ngallery-dl stderr:\n{e.stderr.decode('utf-8', errors='ignore')}"
        print(error_message, file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Fetch metadata from URL using gallery-dl')
    parser.add_argument('url', help='URL to fetch metadata from')
    parser.add_argument('--proxy', help='Proxy server to use (e.g., http://172.20.10.1:10809)')

    args = parser.parse_args()

    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(1)

    fetch_and_parse(args.url, proxy=args.proxy, debug=True)
