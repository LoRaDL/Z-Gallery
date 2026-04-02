import sys
import json
import re
import os
import subprocess
import config
import argparse
import twitter_metadata_parser


def is_twitter_url(url):
    """检查是否是Twitter/X的URL"""
    return bool(re.search(r'(twitter\.com|x\.com)', url, re.IGNORECASE))


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
        # 检查URL是否支持
        if not is_twitter_url(url):
            raise ValueError("Unsupported URL. Only Twitter/X links are supported.")
        
        # --- 1. 精确下载 ---
        target_photo_num = 1
        filter_option = []
        match = re.search(r'/photo/(\d+)', url)
        if match:
            target_photo_num = int(match.group(1))
            # URL 已经指定了 /photo/N，gallery-dl 会自动只下载那张
            # 不需要额外的 --filter，否则两者叠加反而导致 exit code 4
        else:
            # 没有 /photo/N，默认下载第一张（单图或多图帖子的第一张）
            filter_option = ['--filter', 'num == 1']
        
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
        
        # --- 3. 解析元数据，找到与下载文件匹配的媒体块 ---
        data_list = json.loads(meta_result.stdout, strict=False)
        all_dicts = [d for item in data_list if isinstance(item, list) for d in item if isinstance(d, dict)]

        filename_key = os.path.splitext(downloaded_filename)[0]

        content_block = {}
        media_block = {}

        for meta in all_dicts:
            # 找内容块（推文正文）
            if not content_block and ('content' in meta or 'hashtags' in meta):
                content_block = meta
            # 找与下载文件匹配的媒体块
            if meta.get('filename') == filename_key:
                media_block = meta

        # 智能合并：以内容块为基础，用媒体块覆盖（媒体块的 num/count/tweet_id 更准确）
        final_meta = content_block.copy()
        final_meta.update(media_block)

        if not final_meta:
            raise ValueError("No suitable metadata found.")

        # --- 4. 确定图片位置和多图信息 ---
        # 优先用 media_block 里 gallery-dl 给出的 num/count（最可靠）
        # URL 中的 /photo/N 作为兜底（当 media_block 匹配失败时）
        total_images_in_post = media_block.get('count') or len(
            [m for m in all_dicts if m.get('filename')]
        )
        current_image_position = media_block.get('num') or url_based_position
        is_multi_image_post = total_images_in_post > 1

        # --- 5. 使用统一的解析器 ---
        metadata = fix_surrogates(final_meta)

        extracted_data = twitter_metadata_parser.parse_twitter_metadata(
            data=metadata,
            image_position=current_image_position,
            total_images=total_images_in_post,
            is_multi_image_post=is_multi_image_post
        )

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
            error_message += f"\ngallery-dl stderr:\n{e.stderr}"
        print(error_message, file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Fetch metadata from URL using gallery-dl')
    parser.add_argument('url', help='URL to fetch metadata from')
    parser.add_argument('--proxy', help='Proxy server to use (e.g., http://127.0.0.1:10809)')

    args = parser.parse_args()

    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(1)

    fetch_and_parse(args.url, proxy=args.proxy, debug=True)
