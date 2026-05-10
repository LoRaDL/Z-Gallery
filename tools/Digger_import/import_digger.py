#!/usr/bin/env python3
"""
Z-ArtDigger 批量导入工具（Digger 格式）
用法: python import_digger.py [batch_dir] [选项]

与 batch_twitter/import.py 的唯一区别：
  图片从 JSON 中的 media_url 下载，而不是从本地 related/ 目录读取。
"""

import sys
import os
import json
import re
import sqlite3
import base64
import time
import tempfile
import requests
import io
from PIL import Image
import imagehash

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
import config
import artwork_importer
import twitter_metadata_parser

# ─── LLM 配置（与 import.py 保持一致） ────────────────────────────────────────
LM_STUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
LM_STUDIO_MODEL = "local-model"

ENABLE_LLM_CLASSIFICATION = True
DRY_RUN_MODE = False

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

VALID_CATEGORIES = {'fanart', 'real_photo', 'other'}
VALID_CLASSIFICATIONS = {'sfw', 'mature', 'nsfw'}

LLM_MAX_RETRIES = 3
LLM_RETRY_DELAY = 2

# 下载超时（秒）
DOWNLOAD_TIMEOUT = 30
# 下载重试次数
DOWNLOAD_MAX_RETRIES = 3
DOWNLOAD_RETRY_DELAY = 3

# HTTP 请求头（模拟浏览器，避免被拒）
DOWNLOAD_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://x.com/',
}


# ─── 图片下载 ──────────────────────────────────────────────────────────────────

def download_image(media_url, dest_path, max_retries=DOWNLOAD_MAX_RETRIES):
    """从 media_url 下载图片到 dest_path，失败时重试。
    成功返回 True，失败返回 False。
    """
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(media_url, headers=DOWNLOAD_HEADERS,
                                timeout=DOWNLOAD_TIMEOUT, stream=True)
            resp.raise_for_status()
            with open(dest_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
            return True
        except Exception as e:
            if attempt < max_retries:
                print(f"  ⚠ 下载第{attempt}次失败: {e}，{DOWNLOAD_RETRY_DELAY}秒后重试...")
                time.sleep(DOWNLOAD_RETRY_DELAY)
            else:
                print(f"  ✗ 下载失败（共{max_retries}次）: {e}")
    return False


# ─── 元数据解析 ────────────────────────────────────────────────────────────────

def parse_digger_metadata(json_path):
    """解析 Digger 格式的 JSON 元数据（gallery-dl 生成）。"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    image_position = data.get('num', 1)
    total_images = data.get('count', 1)
    is_multi_image_post = total_images > 1
    post_id = data.get('tweet_id') or data.get('post_id')

    extracted = twitter_metadata_parser.parse_twitter_metadata(
        data,
        image_position=image_position,
        total_images=total_images,
        is_multi_image_post=is_multi_image_post,
    )

    extracted['_post_id'] = post_id
    extracted['_image_position'] = image_position
    extracted['_total_images'] = total_images

    return extracted


# ─── LLM 分类（与 import.py 完全一致） ────────────────────────────────────────

def resize_image_for_llm(image_path, max_size=896):
    try:
        with Image.open(image_path) as img:
            w, h = img.size
            if max(w, h) <= max_size:
                return img.copy()
            if w > h:
                nw, nh = max_size, int(h * max_size / w)
            else:
                nh, nw = max_size, int(w * max_size / h)
            return img.resize((nw, nh), Image.Resampling.LANCZOS)
    except Exception as e:
        print(f"  错误: 无法处理图片 {image_path}: {e}")
        return None


def encode_image_to_base64(image_path, max_size=896):
    try:
        resized = resize_image_for_llm(image_path, max_size)
        if resized is None:
            return None
        buf = io.BytesIO()
        if resized.mode == 'RGBA':
            bg = Image.new('RGB', resized.size, (255, 255, 255))
            bg.paste(resized, mask=resized.split()[-1])
            resized = bg
        elif resized.mode != 'RGB':
            resized = resized.convert('RGB')
        resized.save(buf, format='JPEG', quality=85)
        buf.seek(0)
        return base64.b64encode(buf.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"  错误: 无法编码图片 {image_path}: {e}")
        return None


def classify_with_lmstudio(image_path, enable_streaming=True, max_retries=LLM_MAX_RETRIES):
    """使用 LMstudio 对图片进行分类，失败时重试。"""
    image_data = encode_image_to_base64(image_path, max_size=896)
    if not image_data:
        return None, None

    for attempt in range(1, max_retries + 1):
        try:
            payload = {
                "model": LM_STUDIO_MODEL,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": SYSTEM_PROMPT},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/jpeg;base64,{image_data}"
                        }},
                    ],
                }],
                "max_tokens": 300,
                "temperature": 0.1,
                "stream": enable_streaming,
            }

            response = requests.post(
                f"{LM_STUDIO_BASE_URL}/chat/completions",
                json=payload, timeout=60, stream=enable_streaming,
            )

            if response.status_code != 200:
                raise ConnectionError(f"LLM返回HTTP {response.status_code}")

            if enable_streaming:
                content = ""
                for line in response.iter_lines():
                    if line:
                        line = line.decode('utf-8')
                        if line.startswith('data: '):
                            data = line[6:]
                            if data.strip() == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data)
                                if chunk.get('choices'):
                                    delta = chunk['choices'][0].get('delta', {})
                                    if 'content' in delta:
                                        content += delta['content']
                                        print(delta['content'], end='', flush=True)
                            except json.JSONDecodeError:
                                continue
                print()
            else:
                content = response.json()['choices'][0]['message']['content']

            category = classification = None
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('Category:'):
                    category = line.replace('Category:', '').strip().lower()
                elif line.startswith('Classification:'):
                    classification = line.replace('Classification:', '').strip().lower()

            if category not in VALID_CATEGORIES:
                raise ValueError(f"LLM返回了无法识别的category: '{category}'")
            if classification not in VALID_CLASSIFICATIONS:
                raise ValueError(f"LLM返回了无法识别的classification: '{classification}'")

            if category == 'fanart':
                category = 'fanart_non_comic'

            return category, classification

        except Exception as e:
            if attempt < max_retries:
                print(f"  ⚠ 第{attempt}次尝试失败: {e}，{LLM_RETRY_DELAY}秒后重试...")
                time.sleep(LLM_RETRY_DELAY)
                if enable_streaming:
                    print("     ", end="", flush=True)
            else:
                print(f"  ✗ 第{attempt}次尝试失败: {e}")

    return None, None


# ─── phash 工具（与 import.py 一致） ──────────────────────────────────────────

def load_all_phashes(conn):
    cursor = conn.execute(
        "SELECT id, phash, file_name, artist, title FROM artworks WHERE phash IS NOT NULL"
    )
    all_hashes = []
    for row in cursor.fetchall():
        try:
            all_hashes.append({
                'id': row[0],
                'hash': imagehash.hex_to_hash(row[1]),
                'file_name': row[2],
                'artist': row[3],
                'title': row[4],
            })
        except Exception:
            continue
    return all_hashes


def find_similar_images(image_path, all_hashes, threshold=1):
    try:
        with Image.open(image_path) as img:
            query_hash = imagehash.phash(img)
        similar = []
        for item in all_hashes:
            try:
                dist = query_hash - item['hash']
                if dist < threshold:
                    similar.append({**item, 'distance': dist})
            except Exception:
                continue
        return sorted(similar, key=lambda x: x['distance'])
    except Exception as e:
        print(f"  ⚠ 无法计算相似度: {e}")
        return []


# ─── 辅助 ──────────────────────────────────────────────────────────────────────

def _remove_json(json_path, dry_run=False):
    """移除已处理的 JSON 文件（dry-run 时跳过）。"""
    if dry_run:
        return
    try:
        os.remove(json_path)
    except Exception as e:
        print(f"  ⚠ 无法删除 JSON: {e}")


# ─── 核心导入逻辑 ──────────────────────────────────────────────────────────────

def import_batch(batch_dir, check_duplicates=True, threshold=1,
                 enable_llm=True, dry_run=False):
    """批量导入指定目录下的所有 JSON 文件对应的图片。

    目录结构：
        batch_dir/
            *.jpg.json   ← 元数据（媒体 URL 在 json['url'] 字段）
            *.jpg        ← 可选的本地图片（不存在时从网络下载）
    """
    if not os.path.isdir(batch_dir):
        print(f"错误: 目录不存在: {batch_dir}")
        sys.exit(1)

    json_files = sorted([
        f for f in os.listdir(batch_dir)
        if f.endswith('.json') and not f.startswith('_')
    ])

    if not json_files:
        print(f"错误: 目录中未找到 JSON 文件: {batch_dir}")
        sys.exit(1)

    print(f"\n开始导入: {os.path.basename(batch_dir)}")
    print(f"找到 {len(json_files)} 个 JSON 文件")
    print(f"相似度检查: {'开启 (阈值: ' + str(threshold) + ')' if check_duplicates else '关闭'}")
    print(f"LLM分类: {'启用' if enable_llm else '禁用'}")
    if dry_run:
        print("⚠️  干运行模式: 不会写入数据库")
    print("=" * 70)

    success_count = skip_count = error_count = removed_count = 0

    conn = sqlite3.connect(config.DB_FILE)

    all_hashes = []
    if check_duplicates:
        print("加载数据库图片哈希...")
        all_hashes = load_all_phashes(conn)
        print(f"已加载 {len(all_hashes)} 条哈希")
        print("=" * 70)

    # 使用一个临时目录存放从网络下载的图片
    tmp_dir = tempfile.mkdtemp(prefix='digger_import_')

    try:
        for idx, json_fname in enumerate(json_files, 1):
            json_path = os.path.join(batch_dir, json_fname)

            # json 文件名格式：<media_filename>.<ext>.json
            # 去掉末尾的 .json 得到图片文件名
            image_fname = json_fname[:-5]  # 去掉 .json
            print(f"\n[{idx}/{len(json_files)}] 处理: {image_fname}")

            try:
                # ── 解析元数据 ────────────────────────────────────────────────
                metadata = parse_digger_metadata(json_path)

                if not metadata.get('artist'):
                    print("  ⚠ 跳过: 无法提取作者信息")
                    skip_count += 1
                    continue

                media_url = metadata.get('media_url')
                if not media_url:
                    print("  ⚠ 跳过: JSON 中无 media_url")
                    skip_count += 1
                    continue

                # 显示多图信息
                if metadata.get('_total_images', 1) > 1:
                    print(f"  📷 多图帖子: {metadata['_image_position']}/{metadata['_total_images']}")

                # ── 确定图片路径（优先使用本地文件，否则下载） ───────────────
                local_path = os.path.join(batch_dir, image_fname)
                if os.path.exists(local_path):
                    image_path = local_path
                    downloaded = False
                    print(f"  📁 使用本地文件")
                else:
                    # 下载到临时文件
                    tmp_path = os.path.join(tmp_dir, image_fname)
                    print(f"  ⬇ 下载: {media_url}")
                    if not download_image(media_url, tmp_path):
                        print("  ✗ 跳过: 图片下载失败")
                        error_count += 1
                        continue
                    image_path = tmp_path
                    downloaded = True

                # ── 相似度检查 ────────────────────────────────────────────────
                if check_duplicates:
                    similar = find_similar_images(image_path, all_hashes, threshold)
                    if similar:
                        print(f"  ⊘ 跳过 (发现 {len(similar)} 张相似图片，"
                              f"距离: {similar[0]['distance']})")
                        # 清理已下载的临时文件
                        if downloaded and os.path.exists(image_path):
                            os.remove(image_path)
                        _remove_json(json_path, dry_run)
                        removed_count += 1
                        skip_count += 1
                        continue

                # ── LLM 分类 ──────────────────────────────────────────────────
                if enable_llm:
                    print(f"  🤖 LLM分析中...")
                    print(f"     ", end="", flush=True)
                    llm_category, llm_classification = classify_with_lmstudio(
                        image_path, enable_streaming=True
                    )
                    if llm_category and llm_classification:
                        print(f"     结果: [{llm_category}] [{llm_classification}]")
                        metadata['category'] = llm_category
                        metadata['classification'] = llm_classification
                    else:
                        print(f"\n  ✗ LLM分类在{LLM_MAX_RETRIES}次重试后仍然失败，中止导入。")
                        print(f"    请检查LMstudio是否正在运行: {LM_STUDIO_BASE_URL}")
                        conn.close()
                        sys.exit(1)

                # ── 干运行 ────────────────────────────────────────────────────
                if dry_run:
                    title_display = metadata.get('title') or '(无标题)'
                    print(f"  ✓ 干运行: 将导入 → {metadata['artist']}: {title_display[:60]}")
                    if enable_llm:
                        print(f"     分类: {metadata.get('category')} / {metadata.get('classification')}")
                    # 清理临时文件
                    if downloaded and os.path.exists(image_path):
                        os.remove(image_path)
                    success_count += 1
                    continue

                # ── 入库 ──────────────────────────────────────────────────────
                success, artwork_id, error = artwork_importer.add_artwork_to_database(
                    file_path=image_path,
                    metadata=metadata,
                    move_file=True,       # 移动到最终存储位置
                    db_connection=conn,
                    check_duplicate=True,
                )

                if success:
                    print(f"  ✓ 成功导入 (ID: {artwork_id:06d})")
                    title_display = metadata.get('title') or '(无标题)'
                    print(f"     {metadata['artist']}: {title_display[:60]}")
                    if enable_llm:
                        print(f"     分类: {metadata.get('category')} / {metadata.get('classification')}")
                    conn.commit()
                    _remove_json(json_path, dry_run)
                    removed_count += 1
                    success_count += 1
                else:
                    if error and "Duplicate" in error:
                        print(f"  ⚠ 跳过: {error}")
                        _remove_json(json_path, dry_run)
                        removed_count += 1
                        skip_count += 1
                    else:
                        print(f"  ✗ 失败: {error}")
                        error_count += 1
                    # 入库失败时，临时文件不再需要
                    if downloaded and os.path.exists(image_path):
                        os.remove(image_path)

            except Exception as e:
                print(f"  ✗ 错误: {e}")
                error_count += 1

    finally:
        conn.close()
        # 清理临时目录（若仍有残留文件）
        import shutil
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass

    print("\n" + "=" * 70)
    print("导入完成！")
    print(f"  ✓ 成功: {success_count}")
    print(f"  ⚠ 跳过: {skip_count}")
    print(f"  ✗ 错误: {error_count}")
    print(f"  🗑 已移除JSON: {removed_count}")
    print("=" * 70 + "\n")


# ─── 入口 ──────────────────────────────────────────────────────────────────────

def main():
    global ENABLE_LLM_CLASSIFICATION, DRY_RUN_MODE

    check_duplicates = True
    threshold = 1
    enable_llm = ENABLE_LLM_CLASSIFICATION
    dry_run = DRY_RUN_MODE

    args = sys.argv[1:]

    if '--no-check' in args:
        check_duplicates = False
        args.remove('--no-check')

    if '--no-llm' in args:
        enable_llm = False
        args.remove('--no-llm')

    if '--dry-run' in args:
        dry_run = True
        args.remove('--dry-run')

    if '--threshold' in args:
        idx = args.index('--threshold')
        if idx + 1 < len(args):
            try:
                threshold = int(args[idx + 1])
                args.pop(idx)
                args.pop(idx)
            except ValueError:
                pass

    if not args or args[0] in ('--help', '-h'):
        print("用法: python import_digger.py <batch_dir> [选项]")
        print()
        print("参数:")
        print("  batch_dir          包含 *.json 元数据文件的目录")
        print("                     图片若不存在则自动从 media_url 下载")
        print()
        print("选项:")
        print("  --no-check         跳过相似度检查")
        print("  --no-llm           禁用LLM分类 (默认启用)")
        print("  --dry-run          干运行: 不写入数据库、不移动文件")
        print("  --threshold <n>    相似度阈值 (默认: 1)")
        print("  --help, -h         显示帮助")
        print()
        print("示例:")
        print("  python import_digger.py batch1")
        print("  python import_digger.py batch1 --no-llm")
        print("  python import_digger.py batch1 --dry-run")
        print("  python import_digger.py batch1 --no-check --threshold 3")
        print()
        print(f"LMstudio地址: {LM_STUDIO_BASE_URL}")
        return

    # 支持相对路径（相对于本脚本所在目录）
    batch_dir = args[0]
    if not os.path.isabs(batch_dir):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidate = os.path.join(script_dir, batch_dir)
        if os.path.isdir(candidate):
            batch_dir = candidate

    import_batch(batch_dir, check_duplicates, threshold, enable_llm, dry_run)


if __name__ == "__main__":
    main()
