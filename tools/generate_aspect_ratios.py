#!/usr/bin/env python3
"""
生成图片宽高比数据库
遍历所有图片，计算宽高比并存储到独立的数据库中
"""

import sqlite3
import os
import sys
from PIL import Image

# 添加父目录到路径以便导入config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

ASPECT_RATIO_DB = "aspect_ratios.db"
MAIN_DB = config.DB_FILE

def create_aspect_ratio_db():
    """创建宽高比数据库"""
    conn = sqlite3.connect(ASPECT_RATIO_DB)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS aspect_ratios (
            artwork_id INTEGER PRIMARY KEY,
            aspect_ratio REAL NOT NULL,
            width INTEGER NOT NULL,
            height INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    print(f"✓ 宽高比数据库已创建: {ASPECT_RATIO_DB}")

def get_image_aspect_ratio(file_path):
    """获取图片的宽高比"""
    try:
        with Image.open(file_path) as img:
            width, height = img.size
            if height > 0:
                aspect_ratio = width / height
                return aspect_ratio, width, height
    except Exception as e:
        print(f"  ✗ 无法读取图片: {file_path} - {e}")
    return None, None, None

def generate_aspect_ratios(force_update=False):
    """生成所有图片的宽高比数据"""
    # 连接主数据库
    main_conn = sqlite3.connect(MAIN_DB)
    main_conn.row_factory = sqlite3.Row
    main_cursor = main_conn.cursor()
    
    # 连接宽高比数据库
    ar_conn = sqlite3.connect(ASPECT_RATIO_DB)
    ar_cursor = ar_conn.cursor()
    
    # 获取所有图片
    main_cursor.execute("SELECT id, file_path FROM artworks")
    artworks = main_cursor.fetchall()
    
    total = len(artworks)
    processed = 0
    skipped = 0
    updated = 0
    errors = 0
    
    print(f"\n开始处理 {total} 张图片...")
    
    for artwork in artworks:
        artwork_id = artwork['id']
        file_path = artwork['file_path']
        
        # 检查是否已存在
        if not force_update:
            ar_cursor.execute("SELECT artwork_id FROM aspect_ratios WHERE artwork_id = ?", (artwork_id,))
            if ar_cursor.fetchone():
                skipped += 1
                continue
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            print(f"  ✗ 文件不存在: {file_path}")
            errors += 1
            continue
        
        # 获取宽高比
        aspect_ratio, width, height = get_image_aspect_ratio(file_path)
        
        if aspect_ratio is not None:
            # 插入或更新数据库
            ar_cursor.execute("""
                INSERT OR REPLACE INTO aspect_ratios (artwork_id, aspect_ratio, width, height, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (artwork_id, aspect_ratio, width, height))
            
            updated += 1
            processed += 1
            
            if processed % 100 == 0:
                print(f"  进度: {processed}/{total} ({processed*100//total}%)")
                ar_conn.commit()
        else:
            errors += 1
    
    # 提交最后的更改
    ar_conn.commit()
    
    # 关闭连接
    main_conn.close()
    ar_conn.close()
    
    print(f"\n完成!")
    print(f"  总计: {total}")
    print(f"  已更新: {updated}")
    print(f"  已跳过: {skipped}")
    print(f"  错误: {errors}")

def show_stats():
    """显示统计信息"""
    if not os.path.exists(ASPECT_RATIO_DB):
        print("宽高比数据库不存在")
        return
    
    conn = sqlite3.connect(ASPECT_RATIO_DB)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM aspect_ratios")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT AVG(aspect_ratio), MIN(aspect_ratio), MAX(aspect_ratio) FROM aspect_ratios")
    avg, min_ar, max_ar = cursor.fetchone()
    
    print(f"\n宽高比数据库统计:")
    print(f"  记录总数: {total}")
    print(f"  平均宽高比: {avg:.3f}")
    print(f"  最小宽高比: {min_ar:.3f}")
    print(f"  最大宽高比: {max_ar:.3f}")
    
    conn.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="生成图片宽高比数据库")
    parser.add_argument("--force", action="store_true", help="强制更新已存在的记录")
    parser.add_argument("--stats", action="store_true", help="显示统计信息")
    
    args = parser.parse_args()
    
    if args.stats:
        show_stats()
    else:
        create_aspect_ratio_db()
        generate_aspect_ratios(force_update=args.force)
        show_stats()
