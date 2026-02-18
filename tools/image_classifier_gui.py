#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片分类审核工具
读取my_review.txt中的图片ID，逐个显示并允许修改classification
"""

import sqlite3
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import os
import sys

# 添加父目录到路径以导入config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


class ImageClassifierApp:
    def __init__(self, root, image_ids):
        self.root = root
        self.root.title("图片分类审核工具")
        self.image_ids = image_ids
        self.current_index = 0
        self.conn = sqlite3.connect(config.DB_FILE)
        self.conn.row_factory = sqlite3.Row
        
        # 设置窗口大小
        self.root.geometry("1000x900")
        
        # 创建UI组件
        self.create_widgets()
        
        # 加载第一张图片
        self.load_current_image()
    
    def create_widgets(self):
        # 顶部信息栏
        info_frame = tk.Frame(self.root, bg='#f0f0f0', pady=10)
        info_frame.pack(fill=tk.X)
        
        self.info_label = tk.Label(
            info_frame, 
            text="", 
            font=('Arial', 12),
            bg='#f0f0f0'
        )
        self.info_label.pack()
        
        # 图片显示区域
        self.image_label = tk.Label(self.root, bg='white')
        self.image_label.pack(expand=True, fill=tk.BOTH, padx=20, pady=10)
        
        # 当前分类显示
        classification_frame = tk.Frame(self.root, pady=10)
        classification_frame.pack()
        
        tk.Label(
            classification_frame, 
            text="当前分类:", 
            font=('Arial', 14, 'bold')
        ).pack(side=tk.LEFT, padx=5)
        
        self.classification_label = tk.Label(
            classification_frame,
            text="",
            font=('Arial', 14),
            fg='blue'
        )
        self.classification_label.pack(side=tk.LEFT, padx=5)
        
        # 按钮区域
        button_frame = tk.Frame(self.root, pady=20)
        button_frame.pack()
        
        # SFW按钮
        self.sfw_button = tk.Button(
            button_frame,
            text="SFW",
            font=('Arial', 14, 'bold'),
            bg='#4CAF50',
            fg='white',
            width=12,
            height=2,
            command=lambda: self.update_classification('sfw')
        )
        self.sfw_button.pack(side=tk.LEFT, padx=10)
        
        # Mature按钮
        self.mature_button = tk.Button(
            button_frame,
            text="MATURE",
            font=('Arial', 14, 'bold'),
            bg='#FF9800',
            fg='white',
            width=12,
            height=2,
            command=lambda: self.update_classification('mature')
        )
        self.mature_button.pack(side=tk.LEFT, padx=10)
        
        # NSFW按钮
        self.nsfw_button = tk.Button(
            button_frame,
            text="NSFW",
            font=('Arial', 14, 'bold'),
            bg='#F44336',
            fg='white',
            width=12,
            height=2,
            command=lambda: self.update_classification('nsfw')
        )
        self.nsfw_button.pack(side=tk.LEFT, padx=10)
        
        # 导航按钮
        nav_frame = tk.Frame(self.root, pady=10)
        nav_frame.pack()
        
        self.prev_button = tk.Button(
            nav_frame,
            text="← 上一张",
            font=('Arial', 12),
            width=12,
            command=self.prev_image
        )
        self.prev_button.pack(side=tk.LEFT, padx=10)
        
        self.skip_button = tk.Button(
            nav_frame,
            text="跳过",
            font=('Arial', 12),
            width=12,
            command=self.next_image
        )
        self.skip_button.pack(side=tk.LEFT, padx=10)
        
        # 键盘快捷键
        self.root.bind('1', lambda e: self.update_classification('sfw'))
        self.root.bind('2', lambda e: self.update_classification('mature'))
        self.root.bind('3', lambda e: self.update_classification('nsfw'))
        self.root.bind('<Left>', lambda e: self.prev_image())
        self.root.bind('<Right>', lambda e: self.next_image())
        self.root.bind('<space>', lambda e: self.next_image())
    
    def load_current_image(self):
        if self.current_index >= len(self.image_ids):
            messagebox.showinfo("完成", "所有图片已审核完毕！")
            self.root.quit()
            return
        
        image_id = self.image_ids[self.current_index]
        
        # 从数据库获取图片信息
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT id, file_path, file_name, artist, title, classification FROM artworks WHERE id = ?",
            (image_id,)
        ).fetchone()
        
        if not row:
            messagebox.showerror("错误", f"找不到ID为 {image_id} 的图片")
            self.next_image()
            return
        
        self.current_artwork = dict(row)
        
        # 更新信息显示
        progress = f"{self.current_index + 1}/{len(self.image_ids)}"
        artist = self.current_artwork['artist'] or '未知'
        title = self.current_artwork['title'] or '无标题'
        self.info_label.config(
            text=f"进度: {progress} | ID: {image_id:06d} | 艺术家: {artist} | 标题: {title}"
        )
        
        # 更新当前分类显示
        current_class = self.current_artwork['classification'] or '未分类'
        self.classification_label.config(text=current_class.upper())
        
        # 加载并显示图片
        image_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            self.current_artwork['file_path']
        )
        
        if not os.path.exists(image_path):
            messagebox.showerror("错误", f"图片文件不存在: {image_path}")
            self.next_image()
            return
        
        try:
            # 加载图片并调整大小以适应窗口
            image = Image.open(image_path)
            
            # 计算缩放比例以适应显示区域（最大800x600）
            max_width = 800
            max_height = 600
            image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            
            # 转换为PhotoImage
            self.photo = ImageTk.PhotoImage(image)
            self.image_label.config(image=self.photo)
            
        except Exception as e:
            messagebox.showerror("错误", f"无法加载图片: {str(e)}")
            self.next_image()
    
    def update_classification(self, new_classification):
        """更新数据库中的分类并切换到下一张"""
        image_id = self.current_artwork['id']
        
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE artworks SET classification = ? WHERE id = ?",
                (new_classification, image_id)
            )
            self.conn.commit()
            
            print(f"✓ ID {image_id:06d} 已更新为: {new_classification}")
            
            # 自动切换到下一张
            self.current_index += 1
            self.load_current_image()
            
        except Exception as e:
            messagebox.showerror("错误", f"更新数据库失败: {str(e)}")
    
    def next_image(self):
        """跳过当前图片，切换到下一张"""
        self.current_index += 1
        self.load_current_image()
    
    def prev_image(self):
        """返回上一张图片"""
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_image()
    
    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()


def load_image_ids(file_path):
    """从文件中读取图片ID列表"""
    ids = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and line.isdigit():
                ids.append(int(line))
    return ids


def main():
    # 读取图片ID列表
    review_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'my_review.txt'
    )
    
    if not os.path.exists(review_file):
        print(f"错误: 找不到文件 {review_file}")
        sys.exit(1)
    
    image_ids = load_image_ids(review_file)
    
    if not image_ids:
        print("错误: my_review.txt 中没有有效的图片ID")
        sys.exit(1)
    
    print(f"已加载 {len(image_ids)} 个图片ID")
    print("快捷键:")
    print("  1 - 标记为 SFW")
    print("  2 - 标记为 MATURE")
    print("  3 - 标记为 NSFW")
    print("  ← - 上一张")
    print("  → 或 空格 - 跳过")
    print()
    
    # 创建GUI
    root = tk.Tk()
    app = ImageClassifierApp(root, image_ids)
    root.mainloop()


if __name__ == '__main__':
    main()
