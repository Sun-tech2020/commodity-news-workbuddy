#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一配置加载器 (Cross-Platform Config Loader v7.2.0)
提供无缝兼容 macOS 和 Windows 的路径解析、配置加载与运行时辅助。
"""

import os
import json
import pathlib

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

def load_config():
    """读取 config.json，若不存在则返回默认配置"""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] 读取 config.json 失败: {e}，使用默认配置。")
    return {}

def get_obsidian_news_root():
    """
    获取 Obsidian 新闻存放根目录：
    1. 优先读取 config.json 中的 obsidian_news_dir
    2. 其次回退至系统默认用户目录: ~/Documents/Obsidian Vault/工作/新闻
    """
    cfg = load_config()
    custom_dir = cfg.get("obsidian_news_dir", "").strip()
    
    if custom_dir:
        base_dir = os.path.expanduser(custom_dir)
    else:
        user_home = pathlib.Path.home()
        base_dir = str(user_home / "Documents" / "Obsidian Vault" / "工作" / "新闻")
    
    return base_dir

def get_target_dir(target_date, category_suffix="", cli_dir=None):
    """
    智能解析目标新闻目录（跨平台兼容）：
    1. 优先使用命令行参数传入的 cli_dir
    2. 其次拼接 Obsidian 根目录与带有分类后缀的文件夹名称（如 '2026-11-06 新闻（一）'）
    3. 若外部 Obsidian 目录因路径不存在导致创建失败，自动安全回退至当前工作区本地目录并提示用户。
    """
    if cli_dir:
        final_dir = os.path.abspath(cli_dir)
        os.makedirs(final_dir, exist_ok=True)
        return final_dir
    
    base_root = get_obsidian_news_root()
    folder_name = f"{target_date} 新闻{category_suffix}"
    final_dir = os.path.join(base_root, folder_name)
    
    try:
        os.makedirs(final_dir, exist_ok=True)
    except Exception as e:
        print(f"[!] 警告：创建 Obsidian 目录失败 ({final_dir}): {e}")
        # 安全回退至本地工作区
        final_dir = os.path.join(SCRIPT_DIR, folder_name)
        os.makedirs(final_dir, exist_ok=True)
        print(f"[!] 自动回退保存至本地工作区: {final_dir}")
        print(f"[!] 提示：请在 config.json 的 'obsidian_news_dir' 中填入你电脑上正确的 Obsidian 新闻文件夹绝对路径！")
        
    return final_dir

def get_history_file():
    """获取去重历史记录文件路径（保存在当前工作脚本目录下，避免污染其他目录）"""
    return os.path.join(SCRIPT_DIR, ".downloaded_history.json")

def get_user_agent():
    """获取通用的 User-Agent 标头"""
    cfg = load_config()
    return cfg.get("custom_user_agent", "CommodityNewsScraper/2.0 (commodity_news_agent@internal.com)")
