"""
临时补录脚本：从 downloads/ 下的 JSON 文件中提取推文链接，
并回填到数据库的 source_url 字段。

匹配规则：abc.jpg.json 对应数据库中 file_name LIKE '%abc.jpg'
"""

import os
import sys
import json
import sqlite3
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import config

DOWNLOADS_DIR = os.path.join(os.path.dirname(__file__), 'downloads')


def build_source_url(data: dict) -> str | None:
    tweet_id = data.get('tweet_id') or data.get('post_id')
    author = data.get('author') or data.get('user') or {}
    username = author.get('name') if isinstance(author, dict) else None
    if not username:
        username = data.get('username')
    if tweet_id and username:
        num = data.get('num', 1)
        count = data.get('count', 1)
        if count > 1:
            return f"https://x.com/{username}/status/{tweet_id}/photo/{num}"
        return f"https://x.com/{username}/status/{tweet_id}"
    return data.get('url')


def collect_json_files(root_dir: str) -> list[tuple[str, str]]:
    """递归收集所有 .json 文件，边扫描边打印进度"""
    results = []
    total_dirs = sum(1 for _, dirs, _ in os.walk(root_dir) for _ in [dirs])
    dir_count = 0

    for dirpath, dirs, filenames in os.walk(root_dir):
        dirs.sort()
        dir_count += 1
        rel = os.path.relpath(dirpath, root_dir)
        json_files = [f for f in filenames if f.endswith('.json')]
        print(f"  [{dir_count}] {rel}/ — {len(json_files)} 个JSON", flush=True)

        for fname in json_files:
            image_name = fname[:-5]  # abc.jpg.json -> abc.jpg
            json_path = os.path.join(dirpath, fname)
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                url = build_source_url(data)
                if url:
                    results.append((image_name, url))
            except Exception as e:
                print(f"    ⚠ 读取失败 {fname}: {e}", flush=True)

    return results


def backfill(dry_run: bool = False, only_empty: bool = True):
    print(f"扫描目录: {DOWNLOADS_DIR}\n")
    entries = collect_json_files(DOWNLOADS_DIR)
    print(f"\n共找到 {len(entries)} 个有效 JSON\n")
    print("开始匹配数据库...\n")

    conn = sqlite3.connect(config.DB_FILE)
    cursor = conn.cursor()

    updated = 0
    skipped = 0
    not_found = 0

    for i, (image_name, url) in enumerate(entries, 1):
        if only_empty:
            cursor.execute(
                "SELECT id, file_name, source_url FROM artworks "
                "WHERE file_name LIKE ? AND (source_url IS NULL OR source_url = '')",
                (f'%{image_name}',)
            )
        else:
            cursor.execute(
                "SELECT id, file_name, source_url FROM artworks WHERE file_name LIKE ?",
                (f'%{image_name}',)
            )

        rows = cursor.fetchall()

        if not rows:
            not_found += 1
            continue

        for row_id, file_name, existing_url in rows:
            if only_empty and existing_url:
                skipped += 1
                continue
            if dry_run:
                print(f"  [dry] [{i}/{len(entries)}] ID={row_id:06d} {file_name}")
                print(f"         -> {url}", flush=True)
            else:
                cursor.execute(
                    "UPDATE artworks SET source_url = ? WHERE id = ?",
                    (url, row_id)
                )
                print(f"  ✓ [{i}/{len(entries)}] ID={row_id:06d} {file_name}", flush=True)
            updated += 1

        # 每 100 条提交一次，避免长事务
        if not dry_run and i % 100 == 0:
            conn.commit()
            print(f"  --- 已提交 {updated} 条 ---", flush=True)

    if not dry_run:
        conn.commit()
    conn.close()

    print(f"\n{'[干运行] ' if dry_run else ''}完成")
    print(f"  更新: {updated}")
    print(f"  跳过(已有URL): {skipped}")
    print(f"  未匹配: {not_found}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='回填 source_url 到数据库')
    parser.add_argument('--dry-run', action='store_true', help='只打印，不写入数据库')
    parser.add_argument('--overwrite', action='store_true', help='覆盖已有的 source_url')
    args = parser.parse_args()

    backfill(dry_run=args.dry_run, only_empty=not args.overwrite)
