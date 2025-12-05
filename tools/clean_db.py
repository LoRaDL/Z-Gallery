import os
import sqlite3
import sys
from pathlib import Path

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
        for record in all_records:
            # os.path.exists() 是检查文件或目录是否存在的标准方法
            if not os.path.exists(record['file_path']):
                invalid_records.append({
                    "id": record['id'],
                    "path": record['file_path']
                })

        print(f"扫描完成！共检查了 {len(all_records)} 条记录。")
        
        # --- 展示报告 ---
        if not invalid_records:
            print("\n恭喜！所有数据库记录的文件路径都有效。无需任何操作。")
            return

        print(f"\n警告：发现了 {len(invalid_records)} 条无效的文件路径记录：")
        for record in invalid_records:
            print(f"  - ID: {record['id']:<6d} | 路径: {record['path']}")

        # --- 请求确认 ---
        print("\n你想要从数据库中永久删除以上这些记录吗？")
        print("此操作不可恢复，但不会删除任何真实的文件（因为它们已经不存在了）。")
        choice = input("请输入 'yes' 以确认删除: ")

        if choice.lower() == 'yes':
            # --- 执行删除 ---
            ids_to_delete = [rec['id'] for rec in invalid_records]
            
            # 使用 'IN' 子句和参数化查询，一次性删除所有记录，高效且安全
            placeholders = ','.join(['?'] * len(ids_to_delete))
            sql_query = f"DELETE FROM artworks WHERE id IN ({placeholders})"
            
            cursor.execute(sql_query, ids_to_delete)
            conn.commit()
            
            print(f"\n操作成功！已从数据库中删除了 {len(ids_to_delete)} 条无效记录。")
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