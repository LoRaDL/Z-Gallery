import os
import sqlite3
import sys
from pathlib import Path
from PIL import Image

# 禁用 PIL 的解压炸弹保护（允许处理大图片）
Image.MAX_IMAGE_PIXELS = None

# 添加项目根目录到Python路径
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)  # 切换工作目录到项目根目录

import config # 导入你的配置文件以获取数据库名

def check_and_clean_paths():
    """
    检查数据库中所有文件路径的有效性，并根据用户确认删除无效记录。
    """
    db_file = config.DB_FILE
    if not os.path.exists(db_file):
        print(f"错误: 数据库文件 '{db_file}' 未找到。")
        sys.exit(1)

    conn = None
    try:
        conn = sqlite3.connect(db_file)
        # 让返回的行可以像字典一样访问，提高代码可读性
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        print(f"成功连接到数据库 '{db_file}'。")
        print("正在查询所有记录并验证文件路径，请稍候...")

        cursor.execute("SELECT id, file_path FROM artworks")
        all_records = cursor.fetchall()
        
        invalid_records = []
        corrupted_records = []
        
        for record in all_records:
            file_path = record['file_path']
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                invalid_records.append({
                    "id": record['id'],
                    "path": file_path,
                    "reason": "文件不存在"
                })
            else:
                # 文件存在，检查是否损坏
                try:
                    with Image.open(file_path) as img:
                        img.verify()  # 验证图片完整性
                except Exception as e:
                    corrupted_records.append({
                        "id": record['id'],
                        "path": file_path,
                        "reason": f"图片损坏: {str(e)}"
                    })
        
        # 合并无效记录和损坏记录
        all_invalid = invalid_records + corrupted_records

        print(f"扫描完成！共检查了 {len(all_records)} 条记录。")
        
        # --- 展示报告 ---
        if not all_invalid:
            print("\n恭喜！所有数据库记录的文件都有效且完整。无需任何操作。")
            return

        print(f"\n警告：发现了 {len(all_invalid)} 条问题记录：")
        
        if invalid_records:
            print(f"\n文件不存在 ({len(invalid_records)} 条):")
            for record in invalid_records:
                print(f"  - ID: {record['id']:<6d} | 路径: {record['path']}")
        
        if corrupted_records:
            print(f"\n图片损坏 ({len(corrupted_records)} 条):")
            for record in corrupted_records:
                print(f"  - ID: {record['id']:<6d} | 原因: {record['reason']}")
                print(f"    路径: {record['path']}")

        # --- 请求确认 ---
        print("\n你想要从数据库中永久删除以上这些记录吗？")
        if corrupted_records:
            print("注意：损坏的图片文件本身不会被删除，只会删除数据库记录。")
            print("如果需要删除损坏的文件，请手动删除。")
        choice = input("请输入 'yes' 以确认删除: ")

        if choice.lower() == 'yes':
            # --- 执行删除 ---
            ids_to_delete = [rec['id'] for rec in all_invalid]
            
            # 使用 'IN' 子句和参数化查询，一次性删除所有记录，高效且安全
            placeholders = ','.join(['?'] * len(ids_to_delete))
            sql_query = f"DELETE FROM artworks WHERE id IN ({placeholders})"
            
            cursor.execute(sql_query, ids_to_delete)
            conn.commit()
            
            print(f"\n操作成功！已从数据库中删除了 {len(ids_to_delete)} 条问题记录。")
            
            # 询问是否删除损坏的文件
            if corrupted_records:
                print(f"\n发现 {len(corrupted_records)} 个损坏的图片文件。")
                delete_files = input("是否同时删除这些损坏的文件？(yes/no): ")
                if delete_files.lower() == 'yes':
                    deleted_count = 0
                    for record in corrupted_records:
                        try:
                            os.remove(record['path'])
                            print(f"  已删除: {record['path']}")
                            deleted_count += 1
                        except Exception as e:
                            print(f"  删除失败: {record['path']} - {e}")
                    print(f"\n已删除 {deleted_count} 个损坏的文件。")
        else:
            print("\n操作已取消。数据库未作任何更改。")

    except sqlite3.Error as e:
        print(f"\n数据库操作发生错误: {e}")
    finally:
        if conn:
            conn.close()
            print("数据库连接已关闭。")


if __name__ == "__main__":
    print("--- 数据库无效路径清理工具 ---")
    check_and_clean_paths()