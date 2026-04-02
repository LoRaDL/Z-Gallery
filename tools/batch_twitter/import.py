#!/usr/bin/env python3
"""
Twitter批量导入工具
用法: python import.py <directory_name> [--preview] [--dry-run] [--no-llm]
"""

import sys
import os
import json
import re
import sqlite3
import base64
import time
import requests
import io
from PIL import Image
import imagehash

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config
import artwork_importer
import twitter_metadata_parser

# LLM配置
# 确保LMstudio正在运行并加载了支持视觉的模型（如llava、qwen2-vl等）
LM_STUDIO_BASE_URL = "http://localhost:1234/v1"
LM_STUDIO_MODEL = "local-model"  # LMstudio中的模型名称，通常为"local-model"

# 默认开关
ENABLE_LLM_CLASSIFICATION = True  # 默认启用LLM分类
DRY_RUN_MODE = False  # 干运行模式：不写入数据库


# LLM分类提示词
SYSTEM_PROMPT = """You are an expert in analyzing and tagging artworks.
You will receive a single fanart image (may from the movie *Zootopia*).
Your task is to analyze the image and output structured information.

Category: [choose ONE]
- fanart: Artwork, illustrations, drawings (including both single images and comics)
- real_photo: Real photographs, cosplay photos, physical merchandise photos, movie frames
- other: Screenshots, memes, text-heavy images, UI elements, non-art content

Classification: [choose ONE]
- sfw: Safe for work. Fully clothed characters, everyday scenes, casual swimwear/beach scenes, hugs, kisses, romantic moments without suggestive elements. When in doubt between sfw and mature, choose sfw.
- mature: Clearly suggestive content. Revealing underwear, lingerie, partial nudity showing private areas, overtly sexual poses, intimate scenes with sexual tension. Must have clear suggestive intent.
- nsfw: Explicit content. Full nudity with genitalia visible, sexual acts depicted, explicit sexual situations

Example output:
Category: fanart
Classification: sfw"""


def resize_image_for_llm(image_path, max_size=896):
    """将图片下采样到指定最长边尺寸"""
    try:
        with Image.open(image_path) as img:
            # 获取原始尺寸
            width, height = img.size
            
            # 如果图片已经足够小，直接返回
            if max(width, height) <= max_size:
                return img.copy()
            
            # 计算缩放比例
            if width > height:
                new_width = max_size
                new_height = int(height * max_size / width)
            else:
                new_height = max_size
                new_width = int(width * max_size / height)
            
            # 缩放图片
            resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            return resized_img
            
    except Exception as e:
        print(f"  错误: 无法处理图片 {image_path}: {e}")
        return None


def encode_image_to_base64(image_path, max_size=896):
    """将图片下采样并编码为base64"""
    try:
        # 下采样图片
        resized_img = resize_image_for_llm(image_path, max_size)
        if resized_img is None:
            return None
        
        # 转换为JPEG格式并编码
        buffer = io.BytesIO()
        
        # 如果是RGBA模式，转换为RGB
        if resized_img.mode == 'RGBA':
            # 创建白色背景
            background = Image.new('RGB', resized_img.size, (255, 255, 255))
            background.paste(resized_img, mask=resized_img.split()[-1])  # 使用alpha通道作为mask
            resized_img = background
        elif resized_img.mode != 'RGB':
            resized_img = resized_img.convert('RGB')
        
        resized_img.save(buffer, format='JPEG', quality=85)
        buffer.seek(0)
        
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
        
    except Exception as e:
        print(f"  错误: 无法编码图片 {image_path}: {e}")
        return None


def classify_with_lmstudio(image_path, enable_streaming=True):
    """使用LMstudio进行图片分类，支持流式输出"""
    try:
        # 编码图片（下采样到896px）
        image_data = encode_image_to_base64(image_path, max_size=896)
        if not image_data:
            return None, None
        
        # 构建请求
        payload = {
            "model": LM_STUDIO_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": SYSTEM_PROMPT
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 300,
            "temperature": 0.1,
            "stream": enable_streaming
        }
        
        # 发送请求
        response = requests.post(
            f"{LM_STUDIO_BASE_URL}/chat/completions",
            json=payload,
            timeout=60,
            stream=enable_streaming
        )
        
        if response.status_code == 200:
            if enable_streaming:
                # 流式处理
                content = ""
                for line in response.iter_lines():
                    if line:
                        line = line.decode('utf-8')
                        if line.startswith('data: '):
                            data = line[6:]  # 移除 'data: ' 前缀
                            if data.strip() == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data)
                                if 'choices' in chunk and len(chunk['choices']) > 0:
                                    delta = chunk['choices'][0].get('delta', {})
                                    if 'content' in delta:
                                        chunk_content = delta['content']
                                        content += chunk_content
                                        print(chunk_content, end='', flush=True)
                            except json.JSONDecodeError:
                                continue
                print()  # 换行
            else:
                # 非流式处理
                result = response.json()
                content = result['choices'][0]['message']['content']
            
            # 解析响应
            analysis = None
            category = None
            classification = None
            
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('Analysis:'):
                    analysis = line.replace('Analysis:', '').strip()
                elif line.startswith('Category:'):
                    category = line.replace('Category:', '').strip()
                elif line.startswith('Classification:'):
                    classification = line.replace('Classification:', '').strip()
            
            # 映射category：fanart -> fanart_non_comic
            if category == 'fanart':
                category = 'fanart_non_comic'
            
            return category, classification
        else:
            print(f"HTTP {response.status_code}")
            return None, None
            
    except Exception as e:
        print(f"失败: {e}")
        return None, None


def parse_gallery_dl_metadata(json_path):
    """解析gallery-dl生成的JSON元数据"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 提取多图信息
    image_position = data.get('num', 1)
    total_images = data.get('count', 1)
    is_multi_image_post = total_images > 1
    post_id = data.get('tweet_id') or data.get('post_id')
    
    # 使用共享的解析器
    extracted = twitter_metadata_parser.parse_twitter_metadata(
        data,
        image_position=image_position,
        total_images=total_images,
        is_multi_image_post=is_multi_image_post
    )
    
    # 添加调试信息
    extracted['_post_id'] = post_id
    extracted['_image_position'] = image_position
    extracted['_total_images'] = total_images
    
    return extracted


def preview_import(directory, enable_llm=True):
    """预览将要导入的内容"""
    script_dir = os.path.dirname(__file__)
    downloads_dir = os.path.join(script_dir, 'downloads')
    target_dir = os.path.join(downloads_dir, directory)
    
    if not os.path.exists(target_dir):
        print(f"错误: 目录不存在: {directory}")
        sys.exit(1)
    
    # 扫描related子目录中的图片文件
    related_dir = os.path.join(target_dir, 'related')
    if not os.path.exists(related_dir):
        print(f"错误: related子目录不存在: {related_dir}")
        sys.exit(1)
    
    image_files = [f for f in os.listdir(related_dir) 
                   if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))]
    
    if not image_files:
        print(f"错误: related目录中没有找到图片文件")
        sys.exit(1)
    
    print(f"\n预览导入: {directory}")
    if enable_llm:
        print("LLM分类: 启用")
    else:
        print("LLM分类: 禁用")
    print("=" * 70)
    
    will_import = 0
    will_skip = 0
    
    conn = sqlite3.connect(config.DB_FILE)
    cursor = conn.cursor()
    
    for filename in sorted(image_files):
        # gallery-dl的JSON文件名格式是 filename.jpg.json
        json_path = os.path.join(target_dir, filename + '.json')
        
        if not os.path.exists(json_path):
            print(f"⚠ {filename} - 跳过（无元数据）")
            will_skip += 1
            continue
        
        try:
            metadata = parse_gallery_dl_metadata(json_path)
            
            if not metadata['artist']:
                print(f"⚠ {filename} - 跳过（无作者信息）")
                will_skip += 1
                continue
            
            # 检查重复
            if metadata.get('title'):
                cursor.execute(
                    "SELECT id FROM artworks WHERE source_platform = ? AND artist = ? AND title = ?",
                    (metadata['platform'], metadata['artist'], metadata['title'])
                )
                if cursor.fetchone():
                    print(f"⚠ {filename} - 跳过（已存在）")
                    will_skip += 1
                    continue
            
            # 显示多图信息
            multi_info = ""
            if metadata.get('_total_images', 1) > 1:
                multi_info = f" [{metadata['_image_position']}/{metadata['_total_images']}]"
            
            # LLM分类预览
            llm_info = ""
            if enable_llm:
                image_path = os.path.join(related_dir, filename)
                print(f"  🤖 正在分析: {filename}...")
                print(f"     ", end="", flush=True)
                category, classification = classify_with_lmstudio(image_path, enable_streaming=True)
                if category and classification:
                    llm_info = f" [{category}] [{classification}]"
                    print(f"\n     结果: {llm_info}")
                else:
                    print(f"\n     结果: 分类失败")
            
            print(f"✓ {filename}{multi_info}{llm_info}")
            print(f"  → {metadata['artist']}: {metadata['title'][:60]}")
            will_import += 1
            
        except Exception as e:
            print(f"✗ {filename} - 错误: {e}")
            will_skip += 1
    
    conn.close()
    
    print("=" * 70)
    print(f"总计: {will_import} 张将导入, {will_skip} 张将跳过")
    print("=" * 70)


def load_all_phashes(conn):
    """一次性加载所有phash到内存"""
    cursor = conn.execute("SELECT id, phash, file_name, artist, title FROM artworks WHERE phash IS NOT NULL")
    all_hashes = []
    
    for row in cursor.fetchall():
        try:
            all_hashes.append({
                'id': row[0],
                'hash': imagehash.hex_to_hash(row[1]),
                'file_name': row[2],
                'artist': row[3],
                'title': row[4]
            })
        except Exception:
            continue
    
    return all_hashes


def find_similar_images(image_path, all_hashes, threshold=1):
    """查找相似图片（使用预加载的hash列表）"""
    try:
        # 计算当前图片的phash
        with Image.open(image_path) as img:
            query_hash = imagehash.phash(img)
        
        similar = []
        for item in all_hashes:
            try:
                distance = query_hash - item['hash']
                if distance < threshold:
                    similar.append({
                        'id': item['id'],
                        'distance': distance,
                        'file_name': item['file_name'],
                        'artist': item['artist'],
                        'title': item['title']
                    })
            except Exception:
                continue
        
        return sorted(similar, key=lambda x: x['distance'])
    
    except Exception as e:
        print(f"  ⚠ 无法计算相似度: {e}")
        return []


def ask_user_decision(filename, similar_images):
    """询问用户如何处理相似图片"""
    print(f"\n  ⚠ 发现 {len(similar_images)} 张相似图片:")
    for i, sim in enumerate(similar_images[:5], 1):  # 最多显示5张
        print(f"     {i}. ID:{sim['id']:06d} 距离:{sim['distance']} - {sim['artist']}: {sim['title'][:40]}")
    
    if len(similar_images) > 5:
        print(f"     ... 还有 {len(similar_images) - 5} 张")
    
    print(f"\n  当前图片: {filename}")
    print(f"  选项:")
    print(f"    s - 跳过当前图片")
    print(f"    k - 保留并导入（可能重复）")
    print(f"    v - 查看详细信息")
    print(f"    q - 退出导入")
    
    while True:
        try:
            choice = input(f"  请选择 [s/k/v/q]: ").lower().strip()
            if choice in ['s', 'k', 'v', 'q']:
                return choice
            print("  无效的选择，请重新输入")
        except (EOFError, KeyboardInterrupt):
            return 'q'


def import_batch(directory, check_duplicates=True, threshold=1, interactive=False, enable_llm=True, dry_run=False):
    """批量导入指定目录中的图片"""
    script_dir = os.path.dirname(__file__)
    downloads_dir = os.path.join(script_dir, 'downloads')
    target_dir = os.path.join(downloads_dir, directory)
    
    if not os.path.exists(target_dir):
        print(f"错误: 目录不存在: {directory}")
        sys.exit(1)
    
    # 扫描related子目录中的图片文件
    related_dir = os.path.join(target_dir, 'related')
    if not os.path.exists(related_dir):
        print(f"错误: related子目录不存在: {related_dir}")
        sys.exit(1)
    
    try:
        all_files = os.listdir(related_dir)
    except Exception as e:
        print(f"错误: 无法读取related目录: {e}")
        sys.exit(1)
    
    image_files = [f for f in all_files 
                   if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))]
    
    if not image_files:
        print(f"错误: related目录中没有找到图片文件")
        print(f"related目录内容: {len(all_files)} 个文件")
        sys.exit(1)
    
    print(f"\n开始导入: {directory}")
    print(f"找到 {len(image_files)} 张图片")
    if check_duplicates:
        print(f"相似度检查: 开启 (阈值: {threshold})")
    if enable_llm:
        print(f"LLM分类: 启用")
    else:
        print(f"LLM分类: 禁用")
    if dry_run:
        print("⚠️  干运行模式: 不会写入数据库")
    print("=" * 70)
    
    success_count = 0
    skip_count = 0
    error_count = 0
    
    conn = sqlite3.connect(config.DB_FILE)
    
    # 预加载所有phash（优化性能）
    all_hashes = []
    if check_duplicates:
        print("加载数据库中的图片哈希...")
        all_hashes = load_all_phashes(conn)
        print(f"已加载 {len(all_hashes)} 张图片的哈希值")
        
        # 预计算待导入图片的phash（可选优化）
        if len(image_files) > 10:
            print(f"预计算 {len(image_files)} 张待导入图片的哈希...")
        
        print("=" * 70)
    
    for idx, filename in enumerate(sorted(image_files), 1):
        image_path = os.path.join(related_dir, filename)
        # gallery-dl的JSON文件名格式是 filename.jpg.json，不是 filename.json
        # 元数据文件仍然在主目录中
        json_path = os.path.join(target_dir, filename + '.json')
        
        print(f"\n[{idx}/{len(image_files)}] 处理: {filename}")
        
        if not os.path.exists(json_path):
            print(f"  ⚠ 跳过: 没有找到元数据文件 (需要 {os.path.basename(json_path)})")
            skip_count += 1
            continue
        
        try:
            # 解析元数据
            metadata = parse_gallery_dl_metadata(json_path)
            
            if not metadata['artist']:
                print(f"  ⚠ 跳过: 无法提取作者信息")
                skip_count += 1
                continue
            
            # 显示多图信息
            if metadata.get('_total_images', 1) > 1:
                print(f"  📷 多图帖子: {metadata['_image_position']}/{metadata['_total_images']}")
            
            # 相似度检查
            if check_duplicates:
                similar_images = find_similar_images(image_path, all_hashes, threshold)
                if similar_images:
                    if interactive:
                        # 交互模式：询问用户
                        decision = ask_user_decision(filename, similar_images)
                        
                        if decision == 's':
                            print(f"  ⊘ 跳过")
                            skip_count += 1
                            continue
                        elif decision == 'q':
                            print(f"\n用户中止导入")
                            break
                        elif decision == 'v':
                            # 显示详细信息
                            print(f"\n  详细信息:")
                            for sim in similar_images[:5]:
                                print(f"    ID:{sim['id']:06d} 距离:{sim['distance']}")
                                print(f"    文件: {sim['file_name']}")
                                print(f"    作者: {sim['artist']}")
                                print(f"    标题: {sim['title']}")
                                print()
                            
                            # 再次询问
                            decision = ask_user_decision(filename, similar_images)
                            if decision == 's':
                                print(f"  ⊘ 跳过")
                                skip_count += 1
                                continue
                            elif decision == 'q':
                                print(f"\n用户中止导入")
                                break
                        # decision == 'k': 继续导入
                    else:
                        # 非交互模式：自动跳过
                        print(f"  ⊘ 跳过 (发现 {len(similar_images)} 张相似图片，距离: {similar_images[0]['distance']})")
                        skip_count += 1
                        continue
            
            # LLM分类
            llm_category = None
            llm_classification = None
            if enable_llm:
                print(f"  🤖 LLM分析中...")
                print(f"     ", end="", flush=True)
                llm_category, llm_classification = classify_with_lmstudio(image_path, enable_streaming=True)
                if llm_category and llm_classification:
                    print(f"\n     结果: [{llm_category}] [{llm_classification}]")
                    # 更新metadata中的分类信息
                    metadata['category'] = llm_category
                    metadata['classification'] = llm_classification
                else:
                    print(f"\n     结果: 分类失败，使用默认值")
                    metadata['category'] = 'fanart_non_comic'
                    metadata['classification'] = 'sfw'
            
            # 干运行模式
            if dry_run:
                print(f"  ✓ 干运行: 将导入 (模拟)")
                title_display = metadata.get('title') or '(无标题)'
                print(f"     {metadata['artist']}: {title_display[:60]}")
                if enable_llm and llm_category and llm_classification:
                    print(f"     分类: {llm_category} / {llm_classification}")
                success_count += 1
                continue
            
            # 调用统一入库接口
            success, artwork_id, error = artwork_importer.add_artwork_to_database(
                file_path=image_path,
                metadata=metadata,
                move_file=True,
                db_connection=conn,
                check_duplicate=True
            )
            
            if success:
                print(f"  ✓ 成功导入 (ID: {artwork_id:06d})")
                # 安全地显示标题
                title_display = metadata.get('title') or '(无标题)'
                print(f"     {metadata['artist']}: {title_display[:60]}")
                if enable_llm and llm_category and llm_classification:
                    print(f"     分类: {llm_category} / {llm_classification}")
                conn.commit()
                success_count += 1
            else:
                if "Duplicate" in error:
                    print(f"  ⚠ 跳过: {error}")
                    skip_count += 1
                else:
                    print(f"  ✗ 失败: {error}")
                    error_count += 1
                
        except Exception as e:
            print(f"  ✗ 错误: {e}")
            error_count += 1
    
    conn.close()
    
    print("\n" + "=" * 70)
    print(f"导入完成！")
    print(f"  ✓ 成功: {success_count}")
    print(f"  ⚠ 跳过: {skip_count}")
    print(f"  ✗ 错误: {error_count}")
    print("=" * 70 + "\n")


def list_available_batches():
    """列出所有可用的批次"""
    script_dir = os.path.dirname(__file__)
    downloads_dir = os.path.join(script_dir, 'downloads')
    
    if not os.path.exists(downloads_dir):
        return []
    
    batches = []
    for dirname in os.listdir(downloads_dir):
        dir_path = os.path.join(downloads_dir, dirname)
        if os.path.isdir(dir_path):
            # 检查related子目录中的图片数量
            related_dir = os.path.join(dir_path, 'related')
            if os.path.exists(related_dir) and os.path.isdir(related_dir):
                image_count = len([f for f in os.listdir(related_dir) 
                                 if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))])
                if image_count > 0:
                    batches.append({
                        'name': dirname,
                        'count': image_count,
                        'path': dir_path
                    })
    
    return sorted(batches, key=lambda x: x['name'], reverse=False)


def interactive_import():
    """交互式导入"""
    batches = list_available_batches()
    
    if not batches:
        print("没有找到可导入的批次")
        return
    
    print("\n可用的批次：")
    print("=" * 70)
    for i, batch in enumerate(batches, 1):
        print(f"{i}. {batch['name']} ({batch['count']} 张图片)")
    print("=" * 70)
    
    try:
        choice = input("\n请选择要导入的批次 [1-{}] (多选用逗号分隔如'1,3,5', 'all'导入全部, 'q'退出): ".format(len(batches)))
        
        if choice.lower() == 'q':
            print("已取消")
            return
        
        # 解析选择
        selected_batches = []
        
        if choice.lower() == 'all':
            selected_batches = batches
        else:
            # 解析多选输入
            try:
                # 分割并解析数字
                choices = [c.strip() for c in choice.split(',')]
                for c in choices:
                    if '-' in c:
                        # 支持范围选择，如 "1-5"
                        start, end = map(int, c.split('-'))
                        for i in range(start, end + 1):
                            if 1 <= i <= len(batches):
                                selected_batches.append(batches[i - 1])
                    else:
                        # 单个选择
                        index = int(c) - 1
                        if 0 <= index < len(batches):
                            selected_batches.append(batches[index])
                        else:
                            print(f"警告: 忽略无效选择 {c}")
                
                # 去重（保持顺序）
                seen = set()
                unique_batches = []
                for batch in selected_batches:
                    if batch['name'] not in seen:
                        seen.add(batch['name'])
                        unique_batches.append(batch)
                selected_batches = unique_batches
                
            except ValueError:
                print("无效的输入格式")
                return
        
        if not selected_batches:
            print("没有选择任何有效的批次")
            return
        
        # 显示选择的批次
        print(f"\n已选择 {len(selected_batches)} 个批次:")
        for i, batch in enumerate(selected_batches, 1):
            print(f"  {i}. {batch['name']} ({batch['count']} 张图片)")
        
        # 询问配置选项
        print("\n配置导入选项:")
        
        # LLM分类
        llm_input = input("启用LLM分类? [Y/n]: ")
        enable_llm = llm_input.lower() != 'n'
        
        # 干运行模式
        dry_run_input = input("干运行模式(不写入数据库)? [y/N]: ")
        dry_run = dry_run_input.lower() == 'y'
        
        # 预览选项（仅对单个批次有效）
        if len(selected_batches) == 1:
            preview = input(f"是否预览 '{selected_batches[0]['name']}'? [y/N]: ")
            if preview.lower() == 'y':
                preview_import(selected_batches[0]['name'], enable_llm)
                
                # 预览后询问是否继续导入
                if not dry_run:
                    confirm = input("\n是否继续导入? [y/N]: ")
                    if confirm.lower() != 'y':
                        print("已取消")
                        return
        
        # 重复检查
        check_dup = input("检查相似图片? [Y/n]: ")
        check_duplicates = check_dup.lower() != 'n'
        
        threshold = 1
        interactive_mode = False
        
        if check_duplicates:
            threshold_input = input("相似度阈值 [1]: ")
            if threshold_input.strip():
                try:
                    threshold = int(threshold_input)
                except ValueError:
                    threshold = 1
            
            interactive_input = input("发现相似时询问? [y/N]: ")
            interactive_mode = interactive_input.lower() == 'y'
        
        # 开始导入选择的批次
        print(f"\n开始导入 {len(selected_batches)} 个批次...")
        for i, batch in enumerate(selected_batches, 1):
            print(f"\n{'=' * 70}")
            print(f"[{i}/{len(selected_batches)}] 导入批次: {batch['name']}")
            print(f"{'=' * 70}")
            import_batch(batch['name'], check_duplicates, threshold, interactive_mode, enable_llm, dry_run)
    
    except ValueError:
        print("无效的输入")
    except KeyboardInterrupt:
        print("\n\n已取消")


def import_all_batches(check_duplicates=True, threshold=1, interactive=False, enable_llm=True, dry_run=False):
    """导入所有批次"""
    batches = list_available_batches()
    
    if not batches:
        print("没有找到可导入的批次")
        return
    
    print(f"\n找到 {len(batches)} 个批次")
    print("=" * 70)
    
    for i, batch in enumerate(batches, 1):
        print(f"\n[{i}/{len(batches)}] 导入批次: {batch['name']}")
        print("=" * 70)
        import_batch(batch['name'], check_duplicates, threshold, interactive, enable_llm, dry_run)


def main():
    global ENABLE_LLM_CLASSIFICATION, DRY_RUN_MODE
    
    # 解析参数
    check_duplicates = True
    threshold = 1  # 默认阈值改为1
    interactive = False  # 默认非交互模式（自动跳过）
    enable_llm = ENABLE_LLM_CLASSIFICATION
    dry_run = DRY_RUN_MODE
    
    # 检查是否有 --no-check 参数
    if '--no-check' in sys.argv:
        check_duplicates = False
        sys.argv.remove('--no-check')
    
    # 检查是否有 --interactive 参数
    if '--interactive' in sys.argv:
        interactive = True
        sys.argv.remove('--interactive')
    
    # 检查是否有 --no-llm 参数
    if '--no-llm' in sys.argv:
        enable_llm = False
        sys.argv.remove('--no-llm')
    
    # 检查是否有 --dry-run 参数
    if '--dry-run' in sys.argv:
        dry_run = True
        sys.argv.remove('--dry-run')
    
    # 检查是否有 --threshold 参数
    if '--threshold' in sys.argv:
        idx = sys.argv.index('--threshold')
        if idx + 1 < len(sys.argv):
            try:
                threshold = int(sys.argv[idx + 1])
                sys.argv.pop(idx)  # 移除 --threshold
                sys.argv.pop(idx)  # 移除阈值值
            except ValueError:
                pass
    
    if len(sys.argv) == 1:
        # 无参数：交互式模式
        interactive_import()
        return
    
    if sys.argv[1] == '--all':
        # 导入所有批次
        import_all_batches(check_duplicates, threshold, interactive, enable_llm, dry_run)
        return
    
    if sys.argv[1] == '--help' or sys.argv[1] == '-h':
        print("用法: python import.py [选项] [directory_name]")
        print("\n无参数运行：交互式选择批次（支持多选）")
        print("\n选项:")
        print("  --all                        导入所有批次")
        print("  --no-check                   跳过相似度检查")
        print("  --no-llm                     禁用LLM分类 (默认启用)")
        print("  --dry-run                    干运行模式：不写入数据库")
        print("  --threshold <n>              设置相似度阈值 (默认: 1)")
        print("  --interactive                发现相似时询问用户 (默认自动跳过)")
        print("  --help, -h                   显示帮助信息")
        print("\n指定批次:")
        print("  python import.py <directory_name>")
        print("  python import.py <directory_name> --preview")
        print("  python import.py <directory_name> --no-check")
        print("  python import.py <directory_name> --no-llm")
        print("  python import.py <directory_name> --dry-run")
        print("  python import.py <directory_name> --threshold 5")
        print("  python import.py <directory_name> --interactive")
        print("\n交互式多选示例:")
        print("  输入 '1'           # 选择第1个批次")
        print("  输入 '1,3,5'       # 选择第1、3、5个批次")
        print("  输入 '1-5'         # 选择第1到5个批次")
        print("  输入 '1,3-5,7'     # 选择第1、3到5、7个批次")
        print("  输入 'all'         # 选择所有批次")
        print("\n示例:")
        print("  python import.py                              # 交互式选择（支持多选）")
        print("  python import.py --all                        # 导入所有，启用LLM分类")
        print("  python import.py --all --no-llm               # 导入所有，禁用LLM分类")
        print("  python import.py --all --dry-run              # 导入所有，干运行模式")
        print("  python import.py --all --interactive          # 导入所有，询问用户")
        print("  python import.py --all --no-check             # 导入所有，不检查重复")
        print("  python import.py artist_name_20241206_143022  # 导入指定批次")
        print("\nLLM配置:")
        print(f"  LMstudio地址: {LM_STUDIO_BASE_URL}")
        print(f"  模型名称: {LM_STUDIO_MODEL}")
        return
    
    # 指定批次名
    directory = sys.argv[1]
    preview_mode = len(sys.argv) > 2 and sys.argv[2] == '--preview'
    
    if preview_mode:
        preview_import(directory, enable_llm)
    else:
        import_batch(directory, check_duplicates, threshold, interactive, enable_llm, dry_run)


if __name__ == "__main__":
    main()
