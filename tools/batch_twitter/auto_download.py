#!/usr/bin/env python3
"""
自动化Twitter下载脚本
自动检测最新的日期文件夹，生成下一个日期范围并执行下载
支持指定下载之后n天的内容
"""

import os
import re
import subprocess
import sys
from datetime import datetime, timedelta


def parse_date_folder(folder_name):
    """解析日期文件夹名称，返回结束日期和年份"""
    # 格式: MMDD-MMDD
    match = re.match(r'(\d{2})(\d{2})-(\d{2})(\d{2})', folder_name)
    if match:
        start_month, start_day, end_month, end_day = match.groups()
        # 从2025年开始
        year = 2025
        try:
            end_date = datetime(year, int(end_month), int(end_day))
            return end_date, year
        except ValueError:
            return None, None
    return None, None


def get_latest_date_folder():
    """获取最新的日期文件夹"""
    script_dir = os.path.dirname(__file__)
    downloads_dir = os.path.join(script_dir, 'downloads')
    
    if not os.path.exists(downloads_dir):
        return None
    
    date_folders = []
    for dirname in os.listdir(downloads_dir):
        end_date, year = parse_date_folder(dirname)
        if end_date:
            date_folders.append((dirname, end_date, year))
    
    if not date_folders:
        return None
    
    # 返回最新的文件夹
    date_folders.sort(key=lambda x: x[1])
    return date_folders[-1]


def generate_next_date_range(last_end_date, base_year):
    """生成下一个日期范围"""
    # 下一天作为开始日期
    start_date = last_end_date
    # 结束日期是开始日期的下一天
    end_date = start_date + timedelta(days=1)
    
    # 检查是否跨年
    if end_date.year > base_year:
        # 跨年了，更新年份
        base_year = end_date.year
    
    # 格式化为 MMDD-MMDD
    folder_name = f"{start_date.strftime('%m%d')}-{end_date.strftime('%m%d')}"
    
    # 格式化为 URL 中的日期格式 YYYY-MM-DD
    url_start = start_date.strftime('%Y-%m-%d')
    url_end = end_date.strftime('%Y-%m-%d')
    
    return folder_name, url_start, url_end, base_year


def check_folder_exists(folder_name):
    """检查文件夹是否已存在"""
    script_dir = os.path.dirname(__file__)
    downloads_dir = os.path.join(script_dir, 'downloads')
    folder_path = os.path.join(downloads_dir, folder_name)
    return os.path.exists(folder_path)


def main():
    # 解析命令行参数
    days_to_download = 1  # 默认下载1天
    if len(sys.argv) > 1:
        try:
            days_to_download = int(sys.argv[1])
            if days_to_download < 1:
                print("错误: 天数必须大于0")
                sys.exit(1)
        except ValueError:
            print("用法: python auto_download.py [天数]")
            print("示例: python auto_download.py 7  # 下载之后7天的内容")
            sys.exit(1)
    
    print("=" * 70)
    print("自动化Twitter下载脚本")
    print("=" * 70)
    
    # 获取最新的日期文件夹
    latest = get_latest_date_folder()
    
    if latest is None:
        print("\n错误: 未找到任何日期格式的文件夹 (MMDD-MMDD)")
        print("请先手动创建第一个文件夹，例如: 1224-1225")
        sys.exit(1)
    
    folder_name, last_end_date, base_year = latest
    print(f"\n最新文件夹: {folder_name}")
    print(f"最后日期: {last_end_date.strftime('%Y-%m-%d')}")
    print(f"计划下载: 之后 {days_to_download} 天的内容")
    
    # 预先生成所有日期范围并显示
    print(f"\n将下载以下批次:")
    print("-" * 70)
    
    download_plan = []
    current_date = last_end_date
    current_year = base_year
    
    for day_num in range(days_to_download):
        next_folder, url_start, url_end, current_year = generate_next_date_range(current_date, current_year)
        
        # 检查是否已存在同名文件夹（不同年份）
        if check_folder_exists(next_folder) and day_num > 0:
            print(f"\n警告: 文件夹 {next_folder} 已存在（可能是不同年份）")
            print(f"将只下载前 {day_num} 个批次")
            break
        
        download_plan.append({
            'folder': next_folder,
            'url_start': url_start,
            'url_end': url_end,
            'year': current_year
        })
        
        print(f"{day_num + 1:2d}. {next_folder}  ({url_start} 到 {url_end})")
        
        # 更新当前日期为这次的结束日期
        current_date = datetime.strptime(url_end, '%Y-%m-%d')
    
    print("-" * 70)
    print(f"共 {len(download_plan)} 个批次")
    
    # 询问用户确认
    response = input("\n是否继续? (y/n): ").strip().lower()
    if response != 'y':
        print("已取消")
        sys.exit(0)
    
    # 执行下载
    print("\n" + "=" * 70)
    print("开始批量下载...")
    print("=" * 70)
    
    for day_num, plan in enumerate(download_plan):
        print(f"\n{'=' * 70}")
        print(f"批次 {day_num + 1}/{len(download_plan)}: {plan['folder']}")
        print(f"日期范围: {plan['url_start']} 到 {plan['url_end']}")
        print("=" * 70)
        
        # 构建URL
        url = (
            f"https://x.com/search?q=(%23zootopia2%20OR%20%23zootopia%20OR%20"
            f"%23wildehopps%20OR%20%23zootopiafanart)%20"
            f"until%3A{plan['url_end']}%20since%3A{plan['url_start']}&src=typed_query&f=live"
        )
        
        # 执行下载命令
        script_dir = os.path.dirname(__file__)
        download_script = os.path.join(script_dir, 'download.py')
        
        command = [
            sys.executable,  # 使用当前Python解释器
            download_script,
            url,
            '--resume', plan['folder'],
            '--sleep', '0.5'
        ]
        
        try:
            subprocess.run(command, check=True)
            print(f"\n✓ 批次 {day_num + 1} 下载完成: {plan['folder']}")
            
        except subprocess.CalledProcessError:
            print(f"\n✗ 批次 {day_num + 1} 下载失败")
            print(f"已完成 {day_num}/{len(download_plan)} 个批次")
            sys.exit(1)
        except KeyboardInterrupt:
            print(f"\n\n下载已中断")
            print(f"已完成 {day_num}/{len(download_plan)} 个批次")
            sys.exit(1)
    
    print("\n" + "=" * 70)
    print(f"✓ 全部完成! 共下载 {len(download_plan)} 个批次")
    print("=" * 70)


if __name__ == "__main__":
    main()
