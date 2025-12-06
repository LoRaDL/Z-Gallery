#!/usr/bin/env python3
"""
Twitter批量下载工具
用法: python download.py <twitter_url> [--resume <directory_name>]
"""

import subprocess
import sys
import os
import re
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config


def extract_name_from_url(url):
    """从URL提取有意义的名称"""
    
    # 用户主页: https://twitter.com/artist_name
    if '/status/' not in url and '/search' not in url and '/hashtag/' not in url:
        match = re.search(r'twitter\.com/([^/\?]+)', url)
        if match:
            return match.group(1)
    
    # 搜索: https://twitter.com/search?q=zootopia
    if '/search' in url:
        match = re.search(r'q=([^&]+)', url)
        if match:
            query = match.group(1).replace('%20', '_')
            return f"search_{query[:20]}"
    
    # 话题: https://twitter.com/hashtag/zootopia
    if '/hashtag/' in url:
        match = re.search(r'/hashtag/([^/\?]+)', url)
        if match:
            return f"hashtag_{match.group(1)}"
    
    return "twitter_batch"


def list_batches():
    """列出所有已下载的批次"""
    downloads_dir = os.path.join(os.path.dirname(__file__), 'downloads')
    
    if not os.path.exists(downloads_dir):
        print("没有找到下载批次")
        return
    
    batches = []
    for dirname in os.listdir(downloads_dir):
        dir_path = os.path.join(downloads_dir, dirname)
        if os.path.isdir(dir_path):
            # 统计图片数量
            image_count = len([f for f in os.listdir(dir_path) 
                             if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))])
            
            # 检查是否有archive文件（判断是否完成）
            archive_file = os.path.join(dir_path, '.archive.txt')
            status = "已完成" if os.path.exists(archive_file) else "未完成"
            
            batches.append({
                'name': dirname,
                'count': image_count,
                'status': status
            })
    
    if not batches:
        print("没有找到下载批次")
        return
    
    print("\n已下载的批次：")
    print("=" * 70)
    for i, batch in enumerate(batches, 1):
        print(f"{i}. {batch['name']}")
        print(f"   图片数量: {batch['count']}, 状态: {batch['status']}")
    print("=" * 70)


def find_existing_batch(url, downloads_dir):
    """查找URL对应的现有批次"""
    name = extract_name_from_url(url)
    
    # 查找所有匹配的目录
    matching_dirs = []
    if os.path.exists(downloads_dir):
        for dirname in os.listdir(downloads_dir):
            if dirname.startswith(name + '_'):
                dir_path = os.path.join(downloads_dir, dirname)
                if os.path.isdir(dir_path):
                    matching_dirs.append(dirname)
    
    # 返回最新的目录（按名称排序，时间戳在后面）
    if matching_dirs:
        return sorted(matching_dirs)[-1]
    return None


def download(url, resume_dir=None, force_new=False):
    """下载Twitter图片"""
    
    script_dir = os.path.dirname(__file__)
    downloads_dir = os.path.join(script_dir, 'downloads')
    os.makedirs(downloads_dir, exist_ok=True)
    
    # 确定输出目录
    if resume_dir:
        # 用户明确指定了目录
        output_dir = os.path.join(downloads_dir, resume_dir)
        if not os.path.exists(output_dir):
            print(f"错误: 目录不存在: {resume_dir}")
            sys.exit(1)
        print(f"\n继续下载到: {resume_dir}")
    elif force_new:
        # 用户指定创建新批次
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = extract_name_from_url(url)
        dir_name = f"{name}_{timestamp}"
        output_dir = os.path.join(downloads_dir, dir_name)
        os.makedirs(output_dir, exist_ok=True)
        print(f"\n创建新批次: {dir_name}")
    else:
        # 默认：自动查找现有批次
        existing_batch = find_existing_batch(url, downloads_dir)
        if existing_batch:
            output_dir = os.path.join(downloads_dir, existing_batch)
            print(f"\n找到现有批次，继续下载到: {existing_batch}")
        else:
            # 没有现有批次，创建新的
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            name = extract_name_from_url(url)
            dir_name = f"{name}_{timestamp}"
            output_dir = os.path.join(downloads_dir, dir_name)
            os.makedirs(output_dir, exist_ok=True)
            print(f"\n创建新批次: {dir_name}")
    
    # 构建gallery-dl命令
    archive_file = os.path.join(output_dir, '.archive.txt')
    
    command = [
        'gallery-dl',
        '--write-metadata',
        '--directory', output_dir,
        '--download-archive', archive_file,
        '--filter', "extension in ('jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp')",
        '--config', config.GALLERY_DL_CONFIG_PATH,
        url
    ]
    
    print(f"开始下载...")
    print(f"命令: {' '.join(command)}\n")
    
    try:
        result = subprocess.run(command, check=True)
        
        # 统计下载的图片数量
        image_count = len([f for f in os.listdir(output_dir) 
                          if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))])
        
        print(f"\n{'=' * 70}")
        print(f"✓ 下载完成！")
        print(f"  文件保存在: {os.path.basename(output_dir)}")
        print(f"  共下载 {image_count} 张图片")
        print(f"\n请手动清洗图片（删除不需要的），然后运行：")
        print(f"  python tools/batch_twitter/import.py {os.path.basename(output_dir)}")
        print(f"{'=' * 70}\n")
        
    except subprocess.CalledProcessError as e:
        print(f"\n✗ 下载失败")
        print(f"如需续传，运行：")
        print(f"  python tools/batch_twitter/download.py {url} --resume {os.path.basename(output_dir)}")
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n\n下载已中断")
        print(f"如需续传，运行：")
        print(f"  python tools/batch_twitter/download.py {url} --resume {os.path.basename(output_dir)}")
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("用法: python download.py <twitter_url> [选项]")
        print("\n示例:")
        print("  python download.py https://twitter.com/artist_name")
        print("  python download.py \"https://twitter.com/search?q=zootopia\"")
        print("\n选项:")
        print("  --new                        创建新批次（默认会自动续传现有批次）")
        print("  --resume <directory_name>    续传指定批次")
        print("  --list                       列出所有批次")
        sys.exit(1)
    
    if sys.argv[1] == '--list':
        list_batches()
        return
    
    url = sys.argv[1]
    resume_dir = None
    force_new = False
    
    # 解析参数
    if len(sys.argv) > 2:
        if sys.argv[2] == '--resume':
            if len(sys.argv) < 4:
                print("错误: --resume 需要指定目录名")
                sys.exit(1)
            resume_dir = sys.argv[3]
        elif sys.argv[2] == '--new':
            force_new = True
    
    download(url, resume_dir, force_new)


if __name__ == "__main__":
    main()
