#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一配置加载器 (Cross-Platform Config Loader)
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

def get_target_dir(target_date, cli_dir=None):
    """
    智能解析目标新闻目录（跨平台兼容）：
    1. 优先使用命令行参数传入的 --dir
    2. 其次使用 config.json 中配置的 obsidian_news_dir
    3. 默认回退至当前操作系统用户的: ~/Documents/Obsidian Vault/工作/新闻/{target_date} 新闻
    """
    if cli_dir:
        return os.path.abspath(cli_dir)
    
    cfg = load_config()
    custom_dir = cfg.get("obsidian_news_dir", "").strip()
    
    if custom_dir:
        # 支持以 ~ 开头的路径扩展
        base_dir = os.path.expanduser(custom_dir)
    else:
        # 默认跨平台用户路径: ~/Documents/Obsidian Vault/工作/新闻
        user_home = pathlib.Path.home()
        base_dir = str(user_home / "Documents" / "Obsidian Vault" / "工作" / "新闻")
    
    final_dir = os.path.join(base_dir, f"{target_date} 新闻")
    os.makedirs(final_dir, exist_ok=True)
    return final_dir

def get_history_file():
    """获取去重历史记录文件路径（保存在当前工作脚本目录下，避免污染其他目录）"""
    return os.path.join(SCRIPT_DIR, ".downloaded_history.json")

def get_user_agent():
    """获取通用的 User-Agent 标头"""
    cfg = load_config()
    return cfg.get("custom_user_agent", "CommodityNewsScraper/2.0 (commodity_news_agent@internal.com)")

