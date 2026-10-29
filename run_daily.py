#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大宗商品与衍生品每日新闻自动化采编系统 - 极简一键运行入口 (run_daily.py)
自动自检跨平台环境、加载配置并驱动全波次新闻抓取与高保真 PDF 物理存证。
"""

import os
import sys
import time
import argparse
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import config_loader

def check_environment():
    """环境预检：检测关键依赖是否已就绪"""
    missing_deps = []
    for pkg in ["playwright", "bs4", "feedparser", "pypdf"]:
        try:
            __import__(pkg)
        except ImportError:
            missing_deps.append(pkg)
    
    if missing_deps:
        print("\n" + "="*60)
        print("🚨 [环境提示] 检测到以下必要的 Python 依赖包尚未安装:")
        for d in missing_deps:
            print(f"   - {d}")
        print("\n请在终端中运行以下命令完成一键安装:")
        print(f"   pip install -r \"{os.path.join(SCRIPT_DIR, 'requirements.txt')}\"")
        print("   playwright install chromium")
        print("="*60 + "\n")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="大宗商品与衍生品每日新闻采编流水线 - 一键启动器")
    parser.add_argument("--date", type=str, default=time.strftime("%Y-%m-%d"), help="目标采编日期 YYYY-MM-DD (默认当天)")
    parser.add_argument("--dir", type=str, default=None, help="自定义目标存证目录 (留空则读取 config.json 或默认 Obsidian 路径)")
    parser.add_argument("--ignore-history", action="store_true", help="是否忽略去重历史进行全量重采")
    args = parser.parse_args()

    print("\n" + "★"*60)
    print("   🌐 国际大宗商品与衍生品市场新闻自动化采编流水线")
    print("★"*60)
    
    # 1. 环境预检
    check_environment()
    
    # 2. 目录解析
    target_dir = config_loader.get_target_dir(args.date, args.dir)
    print(f"📅 运行日期: {args.date}")
    print(f"📂 存证路径: {target_dir}")
    print(f"⚙️ 配置文件: {config_loader.CONFIG_PATH}")
    
    # 3. 驱动调度执行底层流水线
    pipeline_script = os.path.join(SCRIPT_DIR, "run_daily_pipeline.py")
    cmd = [sys.executable, pipeline_script, "--date", args.date, "--dir", target_dir]
    if args.ignore_history:
        cmd.append("--ignore-history")
        
    start_time = time.time()
    res = subprocess.run(cmd)
    elapsed = time.time() - start_time
    
    if res.returncode == 0:
        print("\n" + "✔"*60)
        print(f"🎉 底层新闻采集与高保真 PDF 物理存证已全部完成！(总耗时: {elapsed:.1f}s)")
        print(f"📂 目标存证目录: {target_dir}")
        print(f"📋 清单文件: {os.path.join(target_dir, 'download_manifest.json')}")
        print("✔"*60 + "\n")
    else:
        print(f"\n❌ 流水线执行过程中遇到异常，退出码: {res.returncode}")
        sys.exit(res.returncode)

if __name__ == "__main__":
    main()

