#!/usr/bin/env python3
"""
LLM图片审核工具
用于审核数据库中的图片，将不通过的图片ID写入文件
用法: python llm_image_review.py [选项]
"""

import sys
import os
import sqlite3
import base64
import json
import requests
import io
import signal
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from datetime import datetime
from tqdm import tqdm

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# 全局标志：用于优雅退出
shutdown_flag = threading.Event()

# LLM配置
LM_STUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
LM_STUDIO_MODEL = "local-model"

# 审核提示词
REVIEW_SYSTEM_PROMPT = """You are an expert content moderator reviewing images.
Analyze the image and determine if it meets content guidelines.

Your task:
Check if the image contains any inappropriate content or is misclassified.

Output format:
Decision: [PASS/FAIL]

Guidelines:
- PASS: Image is appropriate and correctly classified
- FAIL: Image contains inappropriate content, misclassified, or violates guidelines
"""


def encode_image_to_base64(image_path, max_size=896):
    """将图片下采样并编码为base64"""
    try:
        with Image.open(image_path) as img:
            # 获取原始尺寸
            width, height = img.size
            
            # 如果图片已经足够小，直接使用
            if max(width, height) <= max_size:
                resized_img = img.copy()
            else:
                # 计算缩放比例
                if width > height:
                    new_width = max_size
                    new_height = int(height * max_size / width)
                else:
                    new_height = max_size
                    new_width = int(width * max_size / height)
                
                # 缩放图片
                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # 转换为JPEG格式并编码
            buffer = io.BytesIO()
            
            # 如果是RGBA模式，转换为RGB
            if resized_img.mode == 'RGBA':
                background = Image.new('RGB', resized_img.size, (255, 255, 255))
                background.paste(resized_img, mask=resized_img.split()[-1])
                resized_img = background
            elif resized_img.mode != 'RGB':
                resized_img = resized_img.convert('RGB')
            
            resized_img.save(buffer, format='JPEG', quality=85)
            buffer.seek(0)
            
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
            
    except Exception as e:
        return None


def review_with_lmstudio(image_path, max_retries=None):
    """使用LMstudio进行图片审核（非流式），支持无限重试"""
    retry_count = 0
    
    while True:
        # 检查是否需要退出
        if shutdown_flag.is_set():
            return None
        
        try:
            # 编码图片
            image_data = encode_image_to_base64(image_path, max_size=896)
            if not image_data:
                retry_count += 1
                continue
            
            # 构建请求
            payload = {
                "model": LM_STUDIO_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": REVIEW_SYSTEM_PROMPT
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
                "max_tokens": 100,
                "temperature": 0.1,
                "stream": False
            }
            
            # 发送请求
            response = requests.post(
                f"{LM_STUDIO_BASE_URL}/chat/completions",
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                
                # 解析响应
                decision = None
                
                for line in content.split('\n'):
                    line = line.strip()
                    if line.startswith('Decision:'):
                        decision_text = line.replace('Decision:', '').strip().upper()
                        if 'PASS' in decision_text:
                            decision = 'PASS'
                        elif 'FAIL' in decision_text:
                            decision = 'FAIL'
                
                # 如果成功解析到决策，返回结果
                if decision:
                    return decision
                else:
                    # 解析失败，重试
                    retry_count += 1
                    continue
            else:
                # HTTP错误，重试
                retry_count += 1
                continue
                
        except Exception as e:
            # 任何异常都重试
            retry_count += 1
            continue


def get_artworks_by_filter(conn, classification=None, category=None, limit=None):
    """根据条件筛选图片"""
    query = "SELECT id, file_name, artist, title, classification, category FROM artworks WHERE 1=1"
    params = []
    
    if classification:
        query += " AND classification = ?"
        params.append(classification)
    
    if category:
        query += " AND category = ?"
        params.append(category)
    
    query += " ORDER BY id"
    
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    
    cursor = conn.execute(query, params)
    return cursor.fetchall()


def review_artworks(classification=None, category=None, limit=None, start=1, output_file=None, workers=1):
    """审核图片"""
    # 连接数据库
    conn = sqlite3.connect(config.DB_FILE)
    
    # 获取待审核的图片
    artworks = get_artworks_by_filter(conn, classification, category, limit)
    conn.close()
    
    if not artworks:
        print("没有找到符合条件的图片")
        return
    
    total = len(artworks)
    
    # 验证起始位置
    if start < 1 or start > total:
        print(f"错误: 起始位置 {start} 超出范围 (1-{total})")
        return
    
    print(f"\n找到 {total} 张图片待审核")
    
    # 筛选条件
    filter_info = []
    if classification:
        filter_info.append(f"classification={classification}")
    if category:
        filter_info.append(f"category={category}")
    if limit:
        filter_info.append(f"limit={limit}")
    if start > 1:
        filter_info.append(f"start={start}")
    filter_info.append(f"workers={workers}")
    
    if filter_info:
        print(f"筛选条件: {', '.join(filter_info)}")
    
    print("=" * 70)
    
    # 准备输出文件
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"review_failed_{timestamp}.txt"
    
    output_path = os.path.join(os.path.dirname(__file__), output_file)
    
    # 统计
    passed = 0
    failed = 0
    errors = 0
    stats_lock = threading.Lock()
    file_lock = threading.Lock()
    
    # 从指定位置开始审核
    artworks_to_review = artworks[start-1:]
    
    def process_artwork(artwork, pbar):
        """处理单个图片的审核"""
        nonlocal passed, failed, errors
        
        # 检查是否需要退出
        if shutdown_flag.is_set():
            return None
        
        artwork_id, file_name, artist, title, orig_classification, orig_category = artwork
        
        # 更新进度条描述
        pbar.set_description(f"审核 ID:{artwork_id:06d}")
        
        # 构建缩略图路径（缩略图文件名格式为 ID.jpg）
        thumbnail_filename = f"{artwork_id:06d}.jpg"
        thumbnail_path = os.path.join(config.THUMBNAIL_DIR, thumbnail_filename)
        
        if not os.path.exists(thumbnail_path):
            with stats_lock:
                errors += 1
                pbar.set_postfix({"通过": passed, "不通过": failed, "错误": errors})
            return None
        
        # 调用LLM审核（会自动重试直到成功或用户中断）
        decision = review_with_lmstudio(thumbnail_path)
        
        # 如果返回None，说明用户中断了
        if decision is None:
            return None
        
        result = None
        with stats_lock:
            if decision == 'PASS':
                passed += 1
            elif decision == 'FAIL':
                failed += 1
                result = artwork_id
            
            # 更新进度条统计
            pbar.set_postfix({"通过": passed, "不通过": failed, "错误": errors})
        
        return result
    
    # 设置信号处理
    def signal_handler(signum, frame):
        shutdown_flag.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # 开始审核（追加模式，不清空已有内容）
    try:
        with open(output_path, 'a', encoding='utf-8') as f:
            # 使用tqdm进度条
            with tqdm(total=total,
                     initial=start-1,
                     desc="审核进度",
                     unit="张") as pbar:
                
                # 使用线程池
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    # 提交所有任务
                    futures = {
                        executor.submit(process_artwork, artwork, pbar): artwork 
                        for artwork in artworks_to_review
                    }
                    
                    # 处理完成的任务
                    for future in as_completed(futures):
                        if shutdown_flag.is_set():
                            # 取消所有未完成的任务
                            for f in futures:
                                f.cancel()
                            break
                        
                        try:
                            result = future.result()
                            if result is not None:
                                # 写入文件（只写ID）
                                with file_lock:
                                    f.write(f"{result:06d}\n")
                                    f.flush()  # 实时写入
                        except Exception as e:
                            with stats_lock:
                                errors += 1
                        
                        pbar.update(1)
    
    except KeyboardInterrupt:
        print("\n\n用户中断，正在退出...")
        shutdown_flag.set()
    
    # 输出统计
    print("\n" + "=" * 70)
    if shutdown_flag.is_set():
        print(f"审核已中断！")
    else:
        print(f"审核完成！")
    print(f"  ✓ 通过: {passed}")
    print(f"  ✗ 不通过: {failed}")
    print(f"  ⚠ 错误: {errors}")
    print(f"\n不通过的图片ID已写入: {output_path}")
    print("=" * 70 + "\n")


def main():
    """主函数"""
    # 默认参数
    classification = None
    category = None
    limit = None
    start = 1
    output_file = None
    workers = 4
    
    # 解析命令行参数
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        
        if arg == '--classification' and i + 1 < len(args):
            classification = args[i + 1]
            i += 2
        elif arg == '--category' and i + 1 < len(args):
            category = args[i + 1]
            i += 2
        elif arg == '--limit' and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
            except ValueError:
                print(f"错误: --limit 参数必须是整数")
                sys.exit(1)
            i += 2
        elif arg == '--start' and i + 1 < len(args):
            try:
                start = int(args[i + 1])
            except ValueError:
                print(f"错误: --start 参数必须是整数")
                sys.exit(1)
            i += 2
        elif arg == '--workers' and i + 1 < len(args):
            try:
                workers = int(args[i + 1])
                if workers < 1:
                    print(f"错误: --workers 参数必须大于0")
                    sys.exit(1)
            except ValueError:
                print(f"错误: --workers 参数必须是整数")
                sys.exit(1)
            i += 2
        elif arg == '--output' and i + 1 < len(args):
            output_file = args[i + 1]
            i += 2
        elif arg in ['--help', '-h']:
            print("用法: python llm_image_review.py [选项]")
            print("\n选项:")
            print("  --classification <value>  筛选指定分类 (sfw/mature/nsfw)")
            print("  --category <value>        筛选指定类别 (fanart_non_comic/fanart_comic/real_photo/other)")
            print("  --limit <n>               限制审核数量")
            print("  --start <n>               从第n个筛选结果开始 (默认: 1)")
            print("  --workers <n>             并发线程数 (默认: 4)")
            print("  --output <file>           指定输出文件名 (默认: review_failed_<timestamp>.txt)")
            print("  --help, -h                显示帮助信息")
            print("\n示例:")
            print("  python llm_image_review.py --classification sfw")
            print("  python llm_image_review.py --classification sfw --limit 100")
            print("  python llm_image_review.py --classification sfw --start 50")
            print("  python llm_image_review.py --classification sfw --workers 8")
            print("  python llm_image_review.py --category fanart_non_comic --classification sfw")
            print("  python llm_image_review.py --output my_review.txt")
            print("\n提示:")
            print("  - 按 Ctrl+C 可以优雅退出，已处理的结果会保存")
            print("  - 多线程可以加快处理速度，但注意LLM服务器的负载")
            print("\nLLM配置:")
            print(f"  LMstudio地址: {LM_STUDIO_BASE_URL}")
            print(f"  模型名称: {LM_STUDIO_MODEL}")
            return
        else:
            print(f"错误: 未知参数 '{arg}'")
            print("使用 --help 查看帮助信息")
            sys.exit(1)
    
    # 开始审核
    review_artworks(classification, category, limit, start, output_file, workers)


if __name__ == "__main__":
    main()
