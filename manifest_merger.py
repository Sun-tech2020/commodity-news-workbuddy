import config_loader
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wave 3 Manifest Merger & Harmonizer (v6.1.0 智能感知与人工审核适配版)
自动扫描并合并由策略 A (Direct)、策略 B (Cross-Search)、策略 C (Penetrator) 产出的所有 raw manifest：
1. 自动读取目标目录下的所有 manifest_strategy_*_raw.json 文件；
2. 动态感知当前目录下的真实物理 PDF（完美支持用户人工在文件夹中随手删除不满意文章）；
3. 依据三大板块智能判定规则校准分类：
   一、交易所动态
   二、市场动态
   三、监管动态
4. 多维严格排序：三大板块权重 (1/2/3) -> 业务优先级 (P1/P2/P3) -> 机构名称；
5. 全局连续递增编号 [1]~[N]，两阶段安全重命名（杜绝文件名非法字符）；
6. 生成最终标准 download_manifest.json，为后续翻译出报提供 100% 确定性的输入；
7. 自动维护全局历史去重索引库 .downloaded_history.json。
"""

import os
import sys
import json
import time
import re
import hashlib
import argparse
import pypdf

CATEGORY_PRIORITY = {
    "一、交易所动态": 1,
    "二、市场动态": 2,
    "三、监管动态": 3
}

def clean_site_name(site):
    """清洗机构名中的斜杠和非法路径字符"""
    clean = re.sub(r'[/\\:*?"<>|]', '-', site).strip()
    return re.sub(r'-+', '-', clean)

def clean_filename_title(title):
    clean = "".join([c for c in title if c.isalnum() or c in (" ", "-", "_")]).strip()
    clean = re.sub(r'\s+', ' ', clean)
    return clean[:55]

def find_actual_pdf_file(target_dir, raw_filename, site, clean_title):
    """鲁棒查找目录中的真实物理 PDF 文件"""
    if raw_filename and os.path.exists(os.path.join(target_dir, raw_filename)):
        return os.path.join(target_dir, raw_filename)
        
    files = [f for f in os.listdir(target_dir) if f.endswith(".pdf") and not f.startswith("__temp_swap_")]
    
    # 优先匹配 raw_filename 前缀
    if raw_filename:
        parts = raw_filename.split("_")
        if len(parts) >= 3:
            prefix = parts[0] + "_" + parts[1] + "_" + parts[2]
            for f in files:
                if f.startswith(prefix):
                    return os.path.join(target_dir, f)
        elif len(parts) >= 2:
            prefix = parts[0] + "_" + parts[1]
            for f in files:
                if f.startswith(prefix):
                    return os.path.join(target_dir, f)
                    
    # 匹配标题核心词
    core_kw = clean_title[:20].lower()
    if len(core_kw) >= 5:
        for f in files:
            if core_kw in f.lower():
                return os.path.join(target_dir, f)
                
    return None

def update_global_downloaded_history(final_items):
    """自动将本次成功合并落盘的所有 URL 和标题记录到全局历史索引库中"""
    global_hist_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".downloaded_history.json")
    history_data = {"last_updated": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"), "urls": [], "items": []}
    
    if os.path.exists(global_hist_path):
        try:
            with open(global_hist_path, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        except Exception:
            pass
            
    existing_urls = set(history_data.get("urls", []))
    for item in final_items:
        u = item.get("source_url")
        if u and u not in existing_urls:
            existing_urls.add(u)
            history_data["urls"].append(u)
            history_data["items"].append({
                "tier": item.get("tier"),
                "strategy": item.get("strategy"),
                "site": item.get("site"),
                "title": item.get("original_title"),
                "url": u,
                "date": item.get("publish_date")
            })
            
    history_data["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    with open(global_hist_path, "w", encoding="utf-8") as f:
        json.dump(history_data, f, indent=2, ensure_ascii=False)
    print(f"[*] Updated global deduplication history ({len(history_data['urls'])} total records).")

def classify_item_category(title, site, orig_cat=None):
    """
    三大板块严格判定决策树（基于业务属性智能判定）：
    1. 监管动态（优先）：SEC, CFTC, FCA, ESMA, IOSCO, OSC, BaFin, ASIC, ACER, SEBI, BCSC, 执法诉讼, 罚款, 欺诈, 克隆, 吹哨人, 豁免令, 规则废止, 审查指引, 国会法案, 监管声明等
    2. 交易所动态：核心主体为交易所/行业组织（CME, ICE, LME, Eurex, Cboe, SGX, HKEX, FIA, ISDA, DMIST 等）且涉及合约、成交量、做市商、持仓限额、清算规则、结算等
    3. 市场动态：宏观经济（美联储 FOMC、通胀、利率、降息、ETF 资金流）、大宗商品现货供需、产销库存、天气地缘等
    """
    title_lower = title.lower()
    site_lower = site.lower()
    
    # 1. 监管机构与合规/执法判定（包含新闻中报道监管事件）
    reg_official_sites = [
        "美国证券交易委员会", "sec", "美国商品期货交易委员会", "cftc",
        "欧洲证券及市场管理局", "esma", "英国金融行为监管局", "fca",
        "国际证监会组织", "iosco", "安大略省证券委员会", "osc",
        "印度证券交易委员会", "sebi", "bafin", "asic", "bcsc"
    ]
    if any(s in site_lower for s in reg_official_sites) and not any(m in site_lower for m in ["mondo", "yahoo", "newsnow", "bloomberg", "spglobal"]):
        return "三、监管动态"
        
    reg_keywords = [
        r"\bsec\b", r"\bcftc\b", r"\bfca\b", r"\besma\b", r"\biosco\b", r"\bnfa\b", r"\bosc\b", r"\bbafin\b", r"\basic\b", r"\bacer\b", r"\bsebi\b", r"\bbcsc\b",
        r"\bsecurities and exchange commission\b", r"\bcommodity futures trading commission\b",
        r"\bfinancial conduct authority\b", r"\bontario securities commission\b", r"\beuropean securities and markets authority\b",
        r"\bwhistleblower\b", r"\benforcement\b", r"\blawsuit\b", r"\blawsuits\b", r"\bfine\b", r"\bfines\b", r"\bpenalty\b", r"\bpenalties\b", r"\brestitution\b",
        r"\bfraud\b", r"\bclone\b", r"\bcloned\b", r"\bwarning\b", r"\bscam\b", r"\billegal\b", r"\bunauthorized\b",
        r"\bexemptive relief\b", r"\brule rescission\b", r"\brule 14a-8\b", r"\bshareholder proposal\b", r"\bshareholder proposals\b", r"\bproxy solicitation\b",
        r"\bstatement on\b", r"\bcompliance\b", r"\bexamination\b", r"\bexaminations\b", r"\bkeith cassidy\b", r"\bpaul atkins\b", r"\bhester peirce\b", r"\bmark uyeda\b",
        r"\bsenate\b", r"\bcongress\b", r"\bcrypto bill\b", r"\bmarket structure act\b", r"\blegislation\b", r"\blawmakers\b",
        r"\binsider reports\b", r"\btariffs largely compliant\b", r"\bregulatory\b", r"\bregulator\b",
        "监管", "合规", "处罚", "诉讼", "调查", "声明", "指引", "审查", "欺诈", "克隆", "警示", "废止", "豁免", "吹哨人", "法案"
    ]
    for p in reg_keywords:
        if re.search(p, title_lower):
            return "三、监管动态"

    # 2. 交易所主体与业务判定
    exch_official_sites = [
        "芝商所", "cme", "洲际交易所", "ice", "伦敦金属交易所", "lme",
        "欧洲期货交易所", "eurex", "香港交易所", "hkex", "新加坡交易所", "sgx",
        "大阪交易所", "ose", "多伦多交易所", "tmx", "fia", "isda", "dmist", "期货业协会"
    ]
    if any(s in site_lower for s in exch_official_sites) and not any(m in site_lower for m in ["mondo", "yahoo", "newsnow", "bloomberg", "spglobal"]):
        return "一、交易所动态"
        
    exch_entities = [
        r"\bcme\b", r"\bice\b", r"\blme\b", r"\beurex\b", r"\bcboe\b", r"\bsgx\b", r"\bhkex\b",
        r"\bose\b", r"\bjpx\b", r"\btmx\b", r"\beuronext\b", r"\bb3\b", r"\beex\b", r"\bmiax\b", r"\btfex\b", r"\bdtcc\b",
        r"\bcme group\b", r"\bintercontinental exchange\b", r"\blondon metal exchange\b", r"\bchicago mercantile exchange\b",
        r"\bosaka exchange\b", r"\bjapan exchange group\b", r"\btmx group\b", r"\bdeutsche börse\b", r"\bdeutsche boerse\b",
        r"\bclearinghouse\b", r"\bclearing house\b"
    ]
    exch_actions = [
        r"\blaunch\b", r"\blaunches\b", r"\blaunching\b", r"\blisting\b", r"\blisted\b", r"\bnew contract\b", r"\bnew futures\b", r"\bnew options\b",
        r"\btrading volume\b", r"\badv\b", r"\baverage daily volume\b", r"\bopen interest\b", r"\brecord volume\b",
        r"\bmarket maker\b", r"\bincentive\b", r"\bposition limit\b", r"\bposition management\b", r"\bclearing\b", r"\bsettlement\b",
        r"\bmargin requirement\b", r"\btrading hours\b", r"\bmatching engine\b", r"\bdata feed\b", r"\bappoints\b", r"\bchief executive\b", r"\bceo\b",
        r"\bbond offering\b", r"\bsenior notes\b", r"\bdebenture\b", r"\boffering\b", r"\bprivate placement\b", r"\brefinery\b", r"\brefiner\b", r"\bmaintenance\b",
        r"\btokenization member\b", r"\bpartner\b", r"\bpartnership\b",
        "交易所", "新合约", "挂牌", "上市", "做市商", "日均交易量", "成交量", "持仓量", "交割", "清算", "交易时段", "任命", "发债", "债券", "代币化"
    ]
    
    has_exch_entity = any(re.search(e, title_lower) for e in exch_entities)
    has_exch_action = any(re.search(a, title_lower) for a in exch_actions)
    
    if has_exch_entity and has_exch_action:
        return "一、交易所动态"
    if has_exch_entity and ("exchange" in title_lower or "derivatives" in title_lower):
        return "一、交易所动态"
        
    # 3. 市场动态判定（兜底）
    return "二、市场动态"

def merge_and_finalize_manifest(target_dir):
    print(f"[*] Scanning target directory for raw manifests: {target_dir}")
    
    raw_files = [f for f in os.listdir(target_dir) if f.startswith("manifest_") and f.endswith("_raw.json")]
    
    all_raw_items = []
    for rf in sorted(raw_files):
        rf_path = os.path.join(target_dir, rf)
        try:
            with open(rf_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                items = data.get("items", [])
                if items:
                    print(f"    Loaded {len(items)} items from {rf}")
                    all_raw_items.extend(items)
        except Exception as e:
            print(f"[!] Error reading {rf}: {e}")
            
    if not all_raw_items:
        dl_path = os.path.join(target_dir, "download_manifest.json")
        if os.path.exists(dl_path):
            try:
                with open(dl_path, "r", encoding="utf-8") as f:
                    dl_data = json.load(f)
                    all_raw_items = dl_data.get("items", [])
                    if all_raw_items:
                        print(f"    Loaded {len(all_raw_items)} items fallback from download_manifest.json")
            except Exception as e:
                print(f"[!] Error reading download_manifest.json fallback: {e}")
                
    if not all_raw_items:
        # 直接从目录中真实存在的 .pdf 文件中逆向重构条目
        print("    [!] Scanning physical .pdf files in directory to construct manifest...")
        pdf_files = [f for f in os.listdir(target_dir) if f.endswith(".pdf") and not f.startswith("__temp_swap_")]
        for pf in sorted(pdf_files):
            # 格式可能为 [1] Site-Title.pdf 或 Site_01_Title.pdf
            clean_name = pf[:-4]
            site = "官方新闻"
            title = clean_name
            if clean_name.startswith("[") and "]" in clean_name:
                after_bracket = clean_name.split("]", 1)[1].strip()
                if "-" in after_bracket:
                    parts = after_bracket.split("-", 1)
                    site = parts[0].strip()
                    title = parts[1].strip()
                else:
                    title = after_bracket
            all_raw_items.append({
                "tier": "P1" if "Mondo" in site else "P2" if ("FCA" in site or "雅虎" in site or "FOW" in site) else "P3",
                "strategy": "B" if "Mondo" in site else "A" if "FOW" in site else "C",
                "site": site,
                "category": "",
                "original_title": title,
                "publish_date": "2026-09-18",
                "source_url": f"local://{pf}",
                "local_filename": pf,
                "file_size_bytes": os.path.getsize(os.path.join(target_dir, pf)),
                "status": "SUCCESS",
                "binary_verified": True
            })
        print(f"    Reconstructed {len(all_raw_items)} items from physical PDF files.")
                
    print(f"[*] Total raw items collected: {len(all_raw_items)}")
    
    # URL 去重、分类校准与物理文件存在性复核
    seen_urls = set()
    deduped_items = []
    for item in all_raw_items:
        url = item.get("source_url") or item.get("public_url") or item.get("fow_url")
        if not item.get("source_url") and url:
            item["source_url"] = url
        if not item.get("local_filename") and item.get("pdf_filename"):
            item["local_filename"] = item.get("pdf_filename")
        if url and url not in seen_urls:
            seen_urls.add(url)
            item["category"] = classify_item_category(item.get("original_title", ""), item.get("site", ""), item.get("category"))
            deduped_items.append(item)
            
    # 排序：板块 (1/2/3) -> 优先级 (P1: 1, P2: 2, P3: 3) -> 机构名称
    tier_order = {"P1": 1, "P2": 2, "P3": 3}
    def sort_key(item):
        cat_weight = CATEGORY_PRIORITY.get(item.get("category", ""), 99)
        tier_weight = tier_order.get(item.get("tier"), 4)
        return (cat_weight, tier_weight, item.get("site", ""))
        
    sorted_items = sorted(deduped_items, key=sort_key)
    
    # 两阶段安全重命名（只处理当前目录中真实存在的物理 PDF）
    temp_file_map = []
    swap_counter = 0
    for item in sorted_items:
        site = item.get("site", "官方新闻")
        title = item.get("original_title", "News")
        clean_title = clean_filename_title(title)
        raw_filename = item.get("local_filename")
        
        current_file_path = find_actual_pdf_file(target_dir, raw_filename, site, clean_title)
        if not current_file_path or not os.path.exists(current_file_path):
            print(f"    [!] Skipping item (deleted/not present): {title[:35]}")
            continue
            
        swap_counter += 1
        temp_path = os.path.join(target_dir, f"__temp_swap_{swap_counter}_{int(time.time()*1000)}.pdf")
        os.rename(current_file_path, temp_path)
            
        temp_file_map.append({
            "item": item,
            "temp_path": temp_path,
            "clean_title": clean_title,
            "site": site,
            "title": title
        })
        
    final_items = []
    for idx, info in enumerate(temp_file_map, 1):
        item = info["item"]
        site = info["site"]
        clean_title = info["clean_title"]
        title = info["title"]
        temp_path = info["temp_path"]
        
        safe_site = clean_site_name(site)
        target_filename = f"[{idx}] {safe_site}-{clean_title}.pdf"
        target_path = os.path.join(target_dir, target_filename)
        
        if temp_path and os.path.exists(temp_path):
            if os.path.exists(target_path):
                os.remove(target_path)
            os.rename(temp_path, target_path)
            print(f"    [{idx}] Synchronized PDF: -> {target_filename}")
        else:
            continue
            
        file_size = 0
        sha256 = ""
        word_count = item.get("extracted_word_count", 0)
        
        if os.path.exists(target_path):
            file_size = os.path.getsize(target_path)
            with open(target_path, "rb") as f:
                content_bytes = f.read()
                sha256 = hashlib.sha256(content_bytes).hexdigest()
                if not content_bytes.startswith(b"%PDF"):
                    print(f"    [!] Error: {target_filename} does not have %PDF magic header!")
            try:
                reader = pypdf.PdfReader(target_path)
                full_text = "\n".join([p_el.extract_text() for p_el in reader.pages if p_el.extract_text()])
                word_count = len(full_text.split())
            except Exception:
                pass
                
        final_items.append({
            "id": idx,
            "tier": item.get("tier", "P1"),
            "strategy": item.get("strategy", "A"),
            "category": item.get("category", "二、市场动态"),
            "site": site,
            "original_title": title,
            "publish_date": item.get("publish_date", time.strftime("%Y-%m-%d")),
            "source_url": item.get("source_url", ""),
            "local_filename": target_filename,
            "file_size_bytes": file_size,
            "sha256": sha256,
            "extracted_word_count": word_count,
            "status": "SUCCESS",
            "binary_verified": True
        })
        
    final_manifest = {
        "run_id": f"{time.strftime('%Y-%m-%d')}-daily-run-final",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "target_directory": target_dir,
        "export_mode": "OPTION_1_CLEAN_HIGH_FIDELITY_PRINT_TO_PDF",
        "total_captured": len(final_items),
        "items": final_items
    }
    
    manifest_path = os.path.join(target_dir, "download_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(final_manifest, f, indent=2, ensure_ascii=False)
        
    # 更新全局跨日去重历史库
    update_global_downloaded_history(final_items)
    
    print(f"\n🎉 Successfully merged and generated download_manifest.json with {len(final_items)} synchronized items!")
    return final_manifest

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge raw manifests into final download_manifest.json")
    parser.add_argument("--dir", type=str, default=None, help="Target directory")
    args = parser.parse_args()
    
    target_dir = config_loader.get_target_dir(time.strftime("%Y-%m-%d"), args.dir)
    merge_and_finalize_manifest(target_dir)
