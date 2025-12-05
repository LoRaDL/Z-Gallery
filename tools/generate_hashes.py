import sqlite3
import os
import sys
import argparse
from pathlib import Path

# 添加项目根目录到Python路径
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)  # 切换工作目录到项目根目录

from PIL import Image
import imagehash
import config


def normalize_path(p):
    # 尝试直接使用原路径；如果不存在，则替换 '/' 为系统分隔符后重试
    if os.path.exists(p):
        return p
    alt = p.replace('/', os.sep).replace('\\', os.sep)
    if os.path.exists(alt):
        return alt
    # 仍然不存在，返回原路径（后续将跳过）
    return p


def backfill_hashes(commit_each=True, limit=None):
    """为数据库中所有缺少phash的图片生成并填充感知哈希值。

    参数:
      commit_each: 是否在处理每条记录后立即提交（True -> 实时写入）
      limit: 可选，最多处理的记录数
    """
    print("--- 开始为现有图片生成感知哈希 (实时写入模式) ---")
    conn = None
    try:
        conn = sqlite3.connect(config.DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT id, file_path FROM artworks WHERE phash IS NULL")
        records_to_process = cursor.fetchall()

        if not records_to_process:
            print("所有图片都已拥有哈希值，无需操作。")
            return

        total = len(records_to_process)
        if limit is not None:
            records_to_process = records_to_process[:limit]
            total = len(records_to_process)

        print(f"发现 {total} 张图片需要生成哈希...")
        processed_count = 0
        for row in records_to_process:
            artwork_id = row['id']
            file_path = row['file_path']

            processed_count += 1
            status_msg = f"处理中 ({processed_count}/{total}): ID {artwork_id:06d}"
            print(status_msg, end='\r', flush=True)

            norm_path = normalize_path(file_path)
            if not os.path.exists(norm_path):
                print(f"\n[警告] 文件未找到，已跳过: {file_path}")
                continue

            try:
                with Image.open(norm_path) as img:
                    hash_value = imagehash.phash(img)
                cursor.execute("UPDATE artworks SET phash = ? WHERE id = ?", (str(hash_value), artwork_id))
                if commit_each:
                    conn.commit()
            except KeyboardInterrupt:
                print('\n[中断] 用户终止，正在退出。')
                break
            except Exception as e:
                print(f"\n[错误] 处理文件 {file_path} 失败: {e}")
                continue

        # 如果选择不每次提交，则在最后统一提交
        if not commit_each:
            conn.commit()

        print("\n\n所有处理已完成（已写入数据库）。")

    except sqlite3.Error as e:
        print(f"\n数据库操作发生错误: {e}")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Backfill perceptual hashes (phash) for artworks')
    parser.add_argument('--no-commit-each', action='store_true', help='不要在每条记录后提交（默认会实时提交）')
    parser.add_argument('--limit', type=int, default=None, help='最多处理的记录数（可选）')
    args = parser.parse_args()

    try:
        backfill_hashes(commit_each=not args.no_commit_each, limit=args.limit)
    except Exception as exc:
        print(f"运行时发生错误: {exc}")
        sys.exit(1)
