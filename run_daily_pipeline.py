import config_loader
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大宗商品与衍生品市场日报一键自动化调度流水线 (One-Click Daily Pipeline v6.3.0)
架构设计：
- 爬虫按【策略 A/B/C】分类解耦实现：
  * 策略 A: 抓取标题 + 全网二次检索公开源 (英国期货期权世界 FOW Insights)
  * 策略 B: 直接下载 / 原生网页打印 (P1: Mondo Visione; P2: 官方机构与公开源共 14 个)
  * 策略 C: 专有高防穿透下载 (P3: 彭博社, 标普全球洞察)
- 调度按【业务优先级独立波次 Wave 1(P1) -> Wave 2(P2) -> Wave 3(P3) -> Wave 4(Merger) -> Wave 5(Translator)】执行：

1. Wave 1 (P1 核心专线全量抓取):
   - 步骤 1.1: 策略 A (抓标题+二次检索) -> 英国期货期权世界 (FOW Insights, 全量)
   - 步骤 1.2: 策略 B (直接抓取) -> Mondo Visione (全量)

2. Wave 2 (P2 官方与公开聚合源抓取，单站 0~3 篇):
   - 步骤 2: 策略 B (直接抓取) -> CFTC, ESMA, FCA, FIA, ICE, LME, CME, ISDA, DMIST, SEBI, 雅虎财经, NewsNow, SEC, IOSCO

3. Wave 3 (P3 头部商业媒体专有高防穿透抓取，单站 0~3 篇):
   - 步骤 3: 策略 C (穿透通道) -> 彭博社 (Bloomberg), 标普全球洞察 (S&P Global)

4. Wave 4 (存证汇总与全局重命名):
   - 步骤 4: manifest_merger.py 汇总 raw manifest、三大板块严格排序、[1]~[N] 全局重命名

5. Wave 5 (智能体出报交接):
   - 步骤 5: 由 WorkBuddy 智能体阅读物理 PDF 全文并编译三段式零幻视专业市场日报
     （脚本侧不再调用不存在的 translate_manifest_to_report.py，仅做交接与门禁提示）
"""

import os
import sys
import json
import time
import argparse
import subprocess

def verify_pipeline_invariants(script_dir):
    """防回退硬性检查：确保核心穿透信道与知乎 BPC 机制未被后续迭代误删"""
    strat_c_file = os.path.join(script_dir, "strategy_c_penetrator.py")
    if os.path.exists(strat_c_file):
        with open(strat_c_file, "r", encoding="utf-8") as f:
            content = f.read()
            if "site:bnnbloomberg.ca" not in content:
                print("\n🚨 [FATAL ERROR] 架构防回退警报：strategy_c_penetrator.py 丢失了 BNN Bloomberg 官方无墙穿透信道！")
                print("   请勿将检索词改回易导致 403 的裸请求主站 (site:bloomberg.com/news)！")
                sys.exit(1)
            if "googlenewsdecoder" not in content:
                print("\n🚨 [FATAL ERROR] 架构防回退警报：strategy_c_penetrator.py 丢失了 googlenewsdecoder 直解机制！")
                sys.exit(1)

def run_command(cmd_args, step_name):
    print(f"\n==================================================")
    print(f"[*] 正在执行 {step_name}...")
    print(f"    命令: {' '.join(cmd_args)}")
    print(f"==================================================")
    
    start_time = time.time()
    res = subprocess.run(cmd_args, capture_output=False, text=True)
    elapsed = time.time() - start_time
    
    if res.returncode != 0:
        print(f"\n❌ [{step_name}] 执行失败 (耗时: {elapsed:.1f}s)，退出码: {res.returncode}")
        sys.exit(res.returncode)
    else:
        print(f"\n✅ [{step_name}] 执行成功 (耗时: {elapsed:.1f}s)")

def main():
    parser = argparse.ArgumentParser(description="国际大宗商品与衍生品市场日报一键全流程调度器")
    parser.add_argument("--date", type=str, default=time.strftime("%Y-%m-%d"), help="目标日期 YYYY-MM-DD (默认当天)")
    parser.add_argument("--dir", type=str, default=None, help="目标存证与日报输出目录")
    parser.add_argument("--interactive", action="store_true", help="是否在 Wave 1 完成后开启控制台交互式换源审核")
    parser.add_argument("--ignore-history", action="store_true", help="是否忽略去重历史进行重新全量抓取")
    args = parser.parse_args()
    
    target_date = args.date
    base_dir = config_loader.get_target_dir(target_date, args.dir)
    os.makedirs(base_dir, exist_ok=True)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    verify_pipeline_invariants(script_dir)
    
    strat_a_script = os.path.join(script_dir, "strategy_a_capturer.py")
    strat_b_script = os.path.join(script_dir, "strategy_b_capturer.py")
    strat_c_script = os.path.join(script_dir, "strategy_c_penetrator.py")
    refetch_script = os.path.join(script_dir, "targeted_refetcher.py")
    merger_script = os.path.join(script_dir, "manifest_merger.py")
    
    print(f"🚀 启动大宗商品与衍生品日报全自动流水线 (v6.3.0 P1/P2/P3 独立分波架构)")
    print(f"📅 运行日期: {target_date}")
    print(f"📂 存证路径: {base_dir}")
    print(f"🔄 忽略去重历史: {args.ignore_history}")
    
    # ---------------- Wave 1: P1 ----------------
    print(f"\n>>> 🌊 进入 Wave 1 (P1 核心专线全量抓取) <<<")
    cmd_a = [sys.executable, strat_a_script, "--date", target_date, "--dir", base_dir]
    if args.ignore_history:
        cmd_a.append("--ignore-history")
    run_command(cmd_a, "步骤 1.1: Wave 1 (策略 A - 英国期货期权世界 FOW Insights 全量抓取)")
    
    cmd_b1 = [sys.executable, strat_b_script, "--priority", "P1", "--date", target_date, "--dir", base_dir]
    if args.ignore_history:
        cmd_b1.append("--ignore-history")
    run_command(cmd_b1, "步骤 1.2: Wave 1 (策略 B - Mondo Visione 全量抓取)")
    
    # 控制台交互式审核（若开启）
    if args.interactive:
        while True:
            ans = input("\n[❓ 人工审核] 针对 FOW 捕获结果，哪几篇需要换源重搜？(输入搜索关键词或文章标题，无则输入 N): ").strip()
            if not ans or ans.upper() == 'N':
                print("[*] 人工审核确认完成，继续推进后续波次。")
                break
            run_command([sys.executable, refetch_script, "--query", ans, "--date", target_date, "--dir", base_dir], f"靶向重搜换源: {ans}")

    
    # ---------------- Wave 2: P2 ----------------
    print(f"\n>>> 🌊 进入 Wave 2 (P2 官方机构与公开聚合源抓取，单站 0~3 篇) <<<")
    cmd_b2 = [sys.executable, strat_b_script, "--priority", "P2", "--date", target_date, "--dir", base_dir]
    if args.ignore_history:
        cmd_b2.append("--ignore-history")
    run_command(cmd_b2, "步骤 2: Wave 2 (策略 B - P2 官方与公开聚合源抓取)")
    
    # ---------------- Wave 3: P3 ----------------
    print(f"\n>>> 🌊 进入 Wave 3 (P3 头部商业媒体高防穿透抓取，单站 0~3 篇) <<<")
    cmd_c = [sys.executable, strat_c_script, "--date", target_date, "--dir", base_dir]
    if args.ignore_history:
        cmd_c.append("--ignore-history")
    run_command(cmd_c, "步骤 3: Wave 3 (策略 C - P3 彭博社与标普全球穿透抓取)")
    
    # ---------------- Wave 4: Merger ----------------
    print(f"\n>>> 🌊 进入 Wave 4 (存证汇总、三大板块排序与全局 [1]~[N] 重命名) <<<")
    run_command([sys.executable, merger_script, "--dir", base_dir], "步骤 4: Wave 4 (Manifest 汇总与全局物理重命名)")
    
    # ---------------- Wave 5: 智能体出报（非脚本环节）----------------
    # 说明：Wave 5 的公文级三段式内参编译由 WorkBuddy 智能体承担——
    # 需阅读物理 PDF 全文并按「三大板块 / 标题 15~35 字符 / 正文 150~220 字 / 零幻视」红线编译，
    # 不存在等价的脚本实现。此处不再调用不存在的 translate_manifest_to_report.py，
    # 仅做交接提示，保证 Wave 1~4 的采集成果不被误判为流水线失败。
    print(f"\n>>> 🌊 进入 Wave 5 (智能体出报交接) <<<")
    print(f"[*] Wave 1~4 采集与存证已完成，共 {len(json.load(open(os.path.join(base_dir, 'download_manifest.json'), encoding='utf-8'))['items'])} 篇。")
    print(f"[*] 请由 WorkBuddy 智能体阅读 download_manifest.json 与各物理 PDF 全文，")
    print(f"    按 WORKBUDDY_INSTRUCTIONS.md 的四大质量红线编译日报。")
    print(f"[*] 出报完成后可执行质量门禁自检：")
    print(f"    python3 {os.path.join(script_dir, 'report_quality_checker.py')} --dir \"{base_dir}\"")

    print(f"\n🎉 采集与存证全流程执行完毕！")
    print(f"📄 待生成日报: {os.path.join(base_dir, f'{target_date} 国际大宗商品与衍生品市场日报.md')}")
    print(f"📋 审计清单: {os.path.join(base_dir, 'download_manifest.json')}")

if __name__ == "__main__":
    main()
