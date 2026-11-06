#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大宗商品与衍生品市场日报一键自动化调度流水线 (One-Click Daily Pipeline v7.1.0)
架构设计：
- 业务信息源分类体系（采用中文大写数字“一类、二类、三类”，彻底与访问策略 A/B/C 解耦）：
  * 一类信息源（当月编译人员负责 · 核心主责库，共 25 站：人工 4 站 + 自动化 21 站）
  * 二类信息源（协助成员 1 负责 · 外围协同库，共 23 站，目前依托人工协同巡检）
  * 三类信息源（协助成员 2 负责 · 外围协同库，共 23 站，目前依托人工协同巡检）

- 爬虫策略解耦与对应脚本：
  * 策略 A: 直接解析与下载 (17 个官方与公开聚合源) -> strategy_a_capturer.py
  * 策略 B: 抓取标题 + 全网二次检索公开全文 (英国期货期权世界 FOW Insights 与 Mondo Visione MV) -> strategy_b_capturer.py
  * 策略 C: 专有高防穿透下载 (彭博社 Bloomberg, 标普全球洞察 S&P Global) -> strategy_c_penetrator.py
  * 人工: 人工协同重点巡检 (金融时报 FT, MarketScreener, 商业标准报, NSE/NCDEX)

- 调度分波 Wave 1(策略 A 直接抓取) -> Wave 2(策略 B 抓标题二次搜索) -> Wave 3(策略 C 专有穿透) -> Wave 4(Merger) -> Wave 5(Translator)：
  1. Wave 1: 策略 A -> CFTC, CME, ICE, LME, FIA, DMIST, NewsNow, 雅虎财经, 纳斯达克, SEBI, SEC, FCA, ISDA, NFA, ESMA, 印度经济时报, IOSCO (共 17 站直接下载)
  2. Wave 2: 策略 B -> 英国期货期权世界 (FOW Insights) 与 Mondo Visione (MV) 全量抓取 (抓标题+全网二次检索)
  3. Wave 3: 策略 C -> 彭博社 (Bloomberg), 标普全球洞察 (S&P Global) 专有高防穿透下载
  4. Wave 4: 存证汇总与全局重命名 (manifest_merger.py)
  5. Wave 5: 零幻视日报翻译生成 (translate_manifest_to_report.py)
"""

import os
import sys
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

def show_category_2_info():
    print("""
========================================================================================
📋【二类信息源（协助成员 1 负责 · 外围协同库，共 23 站）】
========================================================================================
说明：二类网站由协助成员 1 负责日常浏览与查漏补缺，涵盖境外监管机构、国际组织与专业分析平台。
排序结构：【人工 (2 站) → 策略 A (19 站) → 策略 B (2 站)】

主要站点及访问策略：
 1. [人工] 金融新闻 (fnlondon.com)             2. [人工] 莫斯科交易所 (MOEX，打不开)
 3. [A]   德国联邦金融监督管理局 (BaFin)       4. [A]   香港证券及期货事务监察委员会 (SFC)
 5. [A]   马来西亚证券委员会 (SC)              6. [A]   澳大利亚证券投资委员会 (ASIC)
 7. [A]   澳大利亚审慎监管局 (APRA)            8. [A]   新加坡金融管理局 (MAS)
 9. [A]   日本金融服务机构 (FSA)              10. [A]   金融稳定理事会 (FSB)
11. [A]   英国央行 (BoE)                      12. [A]   伦敦能源经纪人协会 (LEBA)
13. [A]   德意志银行 (Deutsche Bank)          14. [A]   世界交易所联合会 (WFE)
15. [A]   伊斯坦布尔证券交易所 (Borsa Istanbul)16. [A]  韩国交易所 (KRX)
17. [A]   新加坡交易所 (SGX)                  18. [A]   蒙特利尔交易所 (M-X)
19. [A]   波斯顿期权交易所 (BOX)              20. [A]   香港交易及结算所 (HKEX)
21. [A]   台湾期货交易所 (TAIFEX)             22. [B]   TradingView
23. [B]   barchart
----------------------------------------------------------------------------------------
提示：若需对二类中某个特定网站启动自动化定向抓取，请使用对应策略脚本挂载参数。
========================================================================================
""")

def show_category_3_info():
    print("""
========================================================================================
📋【三类信息源（协助成员 2 负责 · 外围协同库，共 23 站）】
========================================================================================
说明：三类网站由协助成员 2 负责日常浏览与查漏补缺，全面覆盖境外主要衍生品与现货交易所。
排序结构：【人工 (5 站) → 策略 A (18 站)】

主要站点及访问策略：
 1. [人工] 约翰内斯堡证券交易所 (JSE，Cloudflare拦截)
 2. [人工] 印度国家商品及衍生品交易所 (NCDEX，Akamai拦截)
 3. [人工] 印度商品交易所 (ICEX，已停运)
 4. [人工] 印度多种商品交易所 (MCX，Akamai拦截)
 5. [人工] 马来西亚衍生品交易所 (BMD，Cloudflare拦截)
 6. [A]   MATba ROFEX                          7. [A]   澳大利亚证券交易所 (ASX)
 8. [A]   泛欧交易所 (Euronext)                9. [A]   泰国期货交易所 (TFEX)
10. [A]   东京金融交易所 (TFX)                11. [A]   迪拜商业交易所 (DME)
12. [A]   日本交易所集团 (JPX)                13. [A]   迈阿密国际证券交易所 (MIAX)
14. [A]   德意志交易所集团 (DBAG)             15. [A]   欧洲期货交易所 (Eurex)
16. [A]   欧洲能源交易所 (EEX)                17. [A]   Nodal交易所
18. [A]   芝加哥期权交易所 (Cboe)             19. [A]   孟买证券交易所 (BSE)
20. [A]   巴西交易所 (B3)                     21. [A]   北美衍生品交易所 (Nadex)
22. [A]   会员交易所 (MEMX)                   23. [A]   伦敦证券交易所集团 (LSEG)
----------------------------------------------------------------------------------------
提示：若需对三类中某个特定交易所启动自动化定向抓取，请使用对应策略脚本挂载参数。
========================================================================================
""")

def resolve_category_tag(cat_input: str) -> tuple[str, str, str]:
    """
    解析用户输入的信息源分类，返回：
    (category_key, category_name, category_suffix)
    例如: ("1", "一类信息源", "（一）")
          ("2", "二类信息源", "（二）")
          ("3", "三类信息源", "（三）")
          ("1,2", "一类与二类组合信息源", "（一、二）")
          ("all", "所有信息源（一、二、三类）", "（所有）")
    """
    if not cat_input:
        return "1", "一类信息源", "（一）"
    
    cleaned = cat_input.strip().strip("()（）[]【】")
    
    # 匹配所有/全量
    if cleaned in ["所有", "全部", "全", "all", "ALL", "1,2,3", "1、2、3", "一、二、三", "一二三", "123"]:
        return "all", "所有信息源（一、二、三类）", "（所有）"
    
    # 匹配一、二组合
    if cleaned in ["一、二", "一,二", "一和二", "一二", "1,2", "1、2", "12"]:
        return "1,2", "一类与二类组合信息源", "（一、二）"
        
    # 匹配一、三组合
    if cleaned in ["一、三", "一,三", "一和三", "一三", "1,3", "1、3", "13"]:
        return "1,3", "一类与三类组合信息源", "（一、三）"

    # 匹配二、三组合
    if cleaned in ["二、三", "二,三", "二和三", "二三", "2,3", "2、3", "23"]:
        return "2,3", "二类与三类组合信息源", "（二、三）"

    # 单独分类
    if cleaned in ["1", "一", "一类", "A", "a"]:
        return "1", "一类信息源", "（一）"
    elif cleaned in ["2", "二", "二类", "B", "b"]:
        return "2", "二类信息源", "（二）"
    elif cleaned in ["3", "三", "三类", "C", "c"]:
        return "3", "三类信息源", "（三）"
    
    # 兜底自定义
    return cleaned, f"{cleaned}信息源", f"（{cleaned}）"

def main():
    parser = argparse.ArgumentParser(description="国际大宗商品与衍生品市场日报一键全流程调度器")
    parser.add_argument("--category", type=str, default="一",
                        help="信息源分类: 一 / 二 / 三 / 所有 / 组合(例如 一、二)")
    parser.add_argument("--date", type=str, default=time.strftime("%Y-%m-%d"), help="目标日期 YYYY-MM-DD (默认当天)")
    parser.add_argument("--dir", type=str, default=None, help="目标存证与日报输出目录")
    parser.add_argument("--interactive", action="store_true", help="是否在 Wave 2 (策略 B) 完成后开启控制台交互式换源审核")
    parser.add_argument("--ignore-history", action="store_true", help="是否忽略去重历史进行重新全量抓取")
    args = parser.parse_args()
    
    category_key, category_name, category_suffix = resolve_category_tag(args.category)
    target_date = args.date
    
    try:
        from config_loader import get_target_dir, get_obsidian_news_root
        base_dir = get_target_dir(target_date, category_suffix, args.dir)
        obsidian_root = get_obsidian_news_root()
    except Exception:
        obsidian_root = os.path.expanduser("~/Documents/Obsidian Vault/工作/新闻")
        base_dir = args.dir if args.dir else os.path.join(obsidian_root, f"{target_date} 新闻{category_suffix}")
        os.makedirs(base_dir, exist_ok=True)
    
    # 自动清理历史未带后缀的同名空目录
    legacy_empty_dir = os.path.join(obsidian_root, f"{target_date} 新闻")
    if os.path.isdir(legacy_empty_dir) and not os.listdir(legacy_empty_dir) and legacy_empty_dir != base_dir:
        try:
            os.rmdir(legacy_empty_dir)
            print(f"[*] 自动清理旧版未标注分类的空目录: {legacy_empty_dir}")
        except Exception:
            pass
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    verify_pipeline_invariants(script_dir)
    
    strat_a_script = os.path.join(script_dir, "strategy_a_capturer.py")
    strat_b_script = os.path.join(script_dir, "strategy_b_capturer.py")
    strat_c_script = os.path.join(script_dir, "strategy_c_penetrator.py")
    refetch_script = os.path.join(script_dir, "targeted_refetcher.py")
    merger_script = os.path.join(script_dir, "manifest_merger.py")
    translator_script = os.path.join(script_dir, "translate_manifest_to_report.py")
    
    print(f"🚀 启动大宗商品与衍生品日报全自动流水线 (v7.1.0 策略与分类解耦版)")
    print(f"📌 选定信息源类别: 【{category_name}】")
    print(f"📅 运行日期: {target_date}")
    print(f"📂 存证路径: {base_dir}")
    print(f"🔄 忽略去重历史: {args.ignore_history}")
    
    if category_key == "2":
        show_category_2_info()
        print("\n" + "="*80)
        print("📢【执行二类信息源自动化采集】（涵盖 19 个策略 A 源、2 个策略 B 源，并提示 2 个人工巡检站）")
        print("="*80)
        cat2_script = os.path.join(script_dir, "execute_cat2_pipeline.py")
        if os.path.exists(cat2_script):
            run_command([sys.executable, cat2_script, "--date", target_date, "--dir", base_dir], "执行二类信息源自动化采编全流程")
        return
    elif category_key == "3":
        show_category_3_info()
        print("\n" + "="*80)
        print("📢【执行三类信息源自动化采集】（涵盖 18 个策略 A 境外交易所源，并提示 5 个人工巡检站）")
        print("="*80)
        cat3_script = os.path.join(script_dir, "execute_cat3_pipeline.py")
        if os.path.exists(cat3_script):
            run_command([sys.executable, cat3_script, "--date", target_date, "--dir", base_dir], "执行三类信息源自动化采编全流程")
        return
        
    # ---------------- 一类信息源主流程 ----------------
    print("\n" + "="*80)
    print("📢【执行一类信息源自动化采集】（涵盖 21 个自动化抓取站，并提示 4 个人工巡检站）")
    print("="*80)
    print("ℹ️  人工协同巡检提示：金融时报、MarketScreener、商业标准报、NSE/NCDEX 由值班人员日常浏览分享。")
    
    # ---------------- Wave 1: 策略 A (17 个官方机构与公开聚合源直接解析与下载) ----------------
    print(f"\n>>> 🌊 进入 Wave 1 (策略 A: 官方机构与公开聚合源直接解析与下载，共 17 站，单站 0~3 篇) <<<")
    cmd_a = [sys.executable, strat_a_script, "--date", target_date, "--dir", base_dir]
    if args.ignore_history:
        cmd_a.append("--ignore-history")
    run_command(cmd_a, "步骤 1: Wave 1 (策略 A - 17 家官方监管与公开聚合源直接下载)")

    # ---------------- Wave 2: 策略 B (重点专业资讯源 FOW & MV 全量抓标题+全网二次检索) ----------------
    print(f"\n>>> 🌊 进入 Wave 2 (策略 B: 核心专业资讯源全量抓取 - FOW Insights & Mondo Visione) <<<")
    cmd_b = [sys.executable, strat_b_script, "--source", "all", "--date", target_date, "--dir", base_dir]
    if args.ignore_history:
        cmd_b.append("--ignore-history")
    run_command(cmd_b, "步骤 2: Wave 2 (策略 B - FOW Insights 与 Mondo Visione 抓标题+二次搜索全量抓取)")
    
    # 控制台交互式审核（若开启，针对策略 B 换源重搜）
    if args.interactive:
        while True:
            ans = input("\n[❓ 人工审核] 针对 Wave 2 捕获结果，哪几篇需要换源重搜？(输入搜索关键词或文章标题，无则输入 N): ").strip()
            if not ans or ans.upper() == 'N':
                print("[*] 人工审核确认完成，继续推进后续波次。")
                break
            run_command([sys.executable, refetch_script, "--query", ans, "--date", target_date, "--dir", base_dir], f"靶向重搜换源: {ans}")
    
    # ---------------- Wave 3: 策略 C (头部商业媒体专有高防穿透下载) ----------------
    print(f"\n>>> 🌊 进入 Wave 3 (策略 C: 头部商业媒体高防穿透通道，彭博社与标普全球，单站 0~3 篇) <<<")
    cmd_c = [sys.executable, strat_c_script, "--date", target_date, "--dir", base_dir]
    if args.ignore_history:
        cmd_c.append("--ignore-history")
    run_command(cmd_c, "步骤 3: Wave 3 (策略 C - 彭博社与标普全球专有高防穿透抓取)")
    
    # ---------------- Wave 4: Merger (存证汇总与全局重命名) ----------------
    print(f"\n>>> 🌊 进入 Wave 4 (存证汇总、三大板块排序与全局 [1]~[N] 重命名) <<<")
    run_command([sys.executable, merger_script, "--dir", base_dir], "步骤 4: Wave 4 (Manifest 汇总与全局物理重命名)")
    
    # ---------------- Wave 5: Translator (零幻视日报翻译出报) ----------------
    print(f"\n>>> 🌊 进入 Wave 5 (零幻视翻译出报) <<<")
    cmd_trans = [sys.executable, translator_script, "--date", target_date, "--dir", base_dir, "--category", category_suffix]
    run_command(cmd_trans, "步骤 5: Wave 5 (三段式零幻视专业市场日报生成)")
    
    print(f"\n🎉 全流程执行完毕！")
    expected_report = os.path.join(base_dir, f"{target_date} 国际大宗商品与衍生品市场日报{category_suffix}.md")
    if not os.path.exists(expected_report):
        cands = [f for f in os.listdir(base_dir) if "国际大宗商品与衍生品市场日报" in f and f.endswith(".md")]
        if cands:
            expected_report = os.path.join(base_dir, cands[0])
    print(f"📄 日报文件: {expected_report}")
    print(f"📋 审计清单: {os.path.join(base_dir, 'download_manifest.json')}")

if __name__ == "__main__":
    main()
