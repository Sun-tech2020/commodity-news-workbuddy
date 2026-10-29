import config_loader
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Strategy C Penetrator: 策略 C 专有高防穿透下载引擎 (Dedicated Anti-Bot & Native Print Penetration Engine v5.0.0)
负责执行 News_Sources_Registry.md 中标注为【策略 C】的站点：
- P3: 彭博社 (Bloomberg), 标普全球洞察 (S&P Global)（单站 0~3 篇）

========================================================================================
🔒【架构防回退与反爬穿透铁律 (CRITICAL INVARIANT RULES - DO NOT REVERT)】🔒
========================================================================================
1. 真实网页原生打印铁律（彻底根除人造 PDF 与幻视）：
   - 严禁使用 ReportLab 等工具在 Python 内部提取文字后人工拼接生成伪造 PDF；
   - 必须统一调用 Playwright 浏览器原生打印引擎 (page.pdf)，100% 还原网站原始 CSS 排版、图片、图表与真实段落！

2. 彭博社 403 根因与穿透信道：
   - 彭博主站 (bloomberg.com) 部署了 Akamai Bot Manager v3 动态 JS 混淆挑战；
   - 必须通过彭博社官方无阻断开放分发站 (BNN Bloomberg: site:bnnbloomberg.ca) 与彭博法律 (site:bloomberglaw.com) 检索；
   - 结合 googlenewsdecoder 毫秒级直解原始媒体落地页，彻底规避 Google 重定向；
   - 严禁篡改回裸请求主站 (site:bloomberg.com/news)，否则必遭 403 阻断！

3. 全文深度防伪审计：
   - 导出的原生 PDF 必须通过 full_text_verifier.py 执行有效正文段落、字数 >= 150 词与严格日期校验；
   - 单站 0~3 篇，零容忍残缺摘要或旧闻凑数。
========================================================================================
"""

import os
import sys
import json
import time
import re
import argparse
import hashlib
from datetime import datetime, timedelta
import feedparser
from bs4 import BeautifulSoup
import pypdf
from playwright.sync_api import sync_playwright
from full_text_verifier import verify_full_text_integrity

# 目标品种清单（郑商所核心品种）
TARGET_COMMODITIES = [
    "sugar", "white sugar", "raw sugar", "cotton", "cotton yarn",
    "rapeseed", "canola", "rapeseed oil", "canola oil", "rapeseed meal",
    "peanut", "peanuts", "groundnut", "apple", "apples", "jujube", "red date",
    "pta", "purified terephthalic acid", "methanol", "urea",
    "polyester", "staple fiber", "psf", "soda ash", "caustic soda",
    "px", "paraxylene", "pet flakes", "bottle-grade pet",
    "glass", "thermal coal", "ferrosilicon", "silicon manganese",
    "derivatives", "options", "futures contract"
]

EXEMPT_KEYWORDS = [
    "regulation", "regulator", "regulatory", "compliance", "enforcement",
    "fraud", "clone", "warning", "penalties", "fine", "restitution", "lawsuit",
    "sec", "cftc", "fca", "esma", "iosco", "sebi", "bafin", "osc",
    "rule", "guidance", "consultation", "statement", "whistleblower",
    "innovation", "fintech", "ai", "carbon", "esg", "tokenization", "blockchain",
    "new contract", "launch", "listing", "index", "market maker",
    "partnership", "mou", "alliance", "acquisition", "clearing", "settlement",
    "prediction market", "event contract", "kalshi", "polymarket", "forecastex",
    "trading volume", "adv", "open interest", "exchange", "cme", "bloomberg", "spglobal"
]

def load_dedup_history():
    hist_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".downloaded_history.json")
    if os.path.exists(hist_file):
        try:
            with open(hist_file, "r", encoding="utf-8") as f:
                return set(json.load(f).get("urls", []))
        except Exception:
            pass
    return set()

def clean_filename(text):
    return "".join([c for c in text if c.isalnum() or c in (" ", "-", "_")]).strip()[:50]

def get_target_date_window(target_date_str):
    """
    根据目标日期计算合法日期窗口与参数：
    - 若目标日期为周一 (weekday() == 0)：窗口扩展为 [T, T-1, T-2, T-3] (周一、周日、周六、上周五)，cutoff 为 T-3，Google 检索为 when:4d
    - 若目标日期为周二至周五/周末：窗口为 [T, T-1]，cutoff 为 T-1，Google 检索为 when:2d
    """
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    is_monday = (target_dt.weekday() == 0)
    
    if is_monday:
        dts = [target_dt - timedelta(days=i) for i in range(4)]
        valid_dates = [dt.strftime("%Y-%m-%d") for dt in dts]
        cutoff_date = valid_dates[-1]  # T-3 (上周五)
        google_when = "when:4d"
    else:
        dts = [target_dt - timedelta(days=i) for i in range(2)]
        valid_dates = [dt.strftime("%Y-%m-%d") for dt in dts]
        cutoff_date = valid_dates[-1]  # T-1
        google_when = "when:2d"
        
    return {
        "is_monday": is_monday,
        "dts": dts,
        "valid_dates": valid_dates,
        "valid_dates_set": set(valid_dates),
        "cutoff_date": cutoff_date,
        "google_when": google_when
    }

def is_strict_date_in_text(text, target_date_str):
    window = get_target_date_window(target_date_str)
    
    # 消除 PDF 字体提取可能产生的数字间异常空格（如 '20 26' -> '2026'）
    norm_text = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
    norm_text = re.sub(r'(\d)\s+(\d)', r'\1\2', norm_text)
    
    patterns = []
    for dt in window["dts"]:
        d_str = dt.strftime("%-d") if sys.platform != "win32" else str(dt.day)
        patterns.extend([
            dt.strftime("%Y-%m-%d"),
            dt.strftime("%d/%m/%Y"),
            dt.strftime("%m/%d/%Y"),
            dt.strftime("%d-%m-%Y"),
            rf"\b{dt.strftime('%B')}\s+{d_str},?\s+{dt.year}\b",
            rf"\b{dt.strftime('%b')}\.?\s+{d_str},?\s+{dt.year}\b",
            rf"\b{d_str}(?:st|nd|rd|th)?\s+{dt.strftime('%B')},?\s+{dt.year}\b",
            rf"\b{d_str}(?:st|nd|rd|th)?\s+{dt.strftime('%b')}\.?,?\s+{dt.year}\b",
        ])
    
    for pat in patterns:
        if re.search(pat, norm_text, re.IGNORECASE):
            return True
    return False

def matches_theme_or_commodity(title, summary=""):
    comb = (title + " " + summary).lower()
    if any(k in comb for k in EXEMPT_KEYWORDS):
        return True
    if any(c in comb for c in TARGET_COMMODITIES):
        return True
    return False

def fetch_google_news_syndication_c(query, site_name, tier, target_date, seen_urls, max_count=3):
    """针对 P3 头部商业媒体的策略 C 检索"""
    items = []
    window = get_target_date_window(target_date)
    valid_dates = window["valid_dates_set"]
    
    d_min = window["valid_dates"][-1]
    dt_max = datetime.strptime(window["valid_dates"][0], "%Y-%m-%d") + timedelta(days=1)
    d_max = dt_max.strftime("%Y-%m-%d")
    
    encoded_q = query.replace(" ", "+")
    rss_queries = [
        f"{encoded_q}+after:{d_min}+before:{d_max}",
        f"{encoded_q}+{window['google_when']}"
    ]
    
    seen_links = set()
    for q_str in rss_queries:
        if len(items) >= max_count:
            break
        rss_url = f"https://news.google.com/rss/search?q={q_str}&hl=en-US&gl=US&ceid=US:en"
        try:
            f = feedparser.parse(rss_url)
            for entry in f.entries:
                link = entry.get("link", "")
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                
                clean_title = re.sub(r"\s+-\s+[^-]+$", "", title).strip()
                
                pub_date = ""
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_date = time.strftime("%Y-%m-%d", entry.published_parsed)
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    pub_date = time.strftime("%Y-%m-%d", entry.updated_parsed)
                    
                if pub_date not in valid_dates:
                    continue
                if link in seen_urls or link in seen_links:
                    continue
                seen_links.add(link)
                if not matches_theme_or_commodity(clean_title, summary):
                    continue
                    
                items.append({
                    "tier": tier,
                    "strategy": "C",
                    "site": site_name,
                    "category": "",
                    "title": clean_title,
                    "url": link,
                    "publish_date": pub_date,
                    "summary": summary
                })
                if len(items) >= max_count:
                    break
        except Exception as e:
            print(f"[!] Error syndicating for {site_name} ({q_str}): {e}")
            
    return items

def resolve_real_url_playwright(page, raw_url):
    """优先使用 googlenewsdecoder 毫秒级直解真实落地页 URL，备选 Playwright"""
    if "news.google.com" in raw_url:
        try:
            import googlenewsdecoder
            dec_res = googlenewsdecoder.new_decoderv1(raw_url)
            if dec_res and dec_res.get("status") and dec_res.get("decoded_url"):
                real = dec_res["decoded_url"]
                if real.startswith("http://"):
                    real = "https://" + real[7:]
                return real
        except Exception:
            pass
            
    if "news.google.com" not in raw_url:
        return raw_url
    try:
        page.goto(raw_url, wait_until="domcontentloaded", timeout=25000)
        if "consent.google.com" in page.url:
            buttons = page.query_selector_all("button")
            for b in buttons:
                txt = b.inner_text().strip().lower()
                if any(w in txt for w in ["accept", "agree", "akzeptieren", "accepter"]):
                    b.click()
                    break
        for _ in range(15):
            if "google.com" not in page.url:
                break
            page.wait_for_timeout(500)
        return page.url
    except Exception:
        return raw_url

def print_to_pdf_native(page, url, target_path):
    """方案 1：无遮罩高保真网页原生打印 PDF（真实网站右键导出 PDF）"""
    if url.startswith("http://"):
        url = "https://" + url[7:]
        
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2.0)
        
        # 模拟平滑滚动触发所有图片与延迟加载段落渲染（多段推进与充分等待）
        page.evaluate("""
        () => {
            window.scrollTo(0, document.body.scrollHeight / 3);
        }
        """)
        time.sleep(1.0)
        page.evaluate("""
        () => {
            window.scrollTo(0, document.body.scrollHeight / 1.5);
        }
        """)
        time.sleep(1.0)
        page.evaluate("""
        () => {
            window.scrollTo(0, 0);
        }
        """)
        time.sleep(1.0)
    except Exception as e:
        print(f"    [!] Failed to load URL ({url}): {e}")
        return False
        
    # 通用清理广告、cookie banner、弹窗与遮罩、以及导致空白页的高侧边栏容器
    js_clean = """
    () => {
        const selectors = [
            '#onetrust-consent-sdk', '.cookie-banner', '.modal', '.popup',
            '.overlay', '#CybotCookiebotDialog', '.ot-sdk-container',
            '#gdpr-banner', '.privacy-prompt', '.ad-banner', '.advertisement',
            '.tp-backdrop', '.tp-modal', '.consent-banner', '.paywall-overlay',
            '#sp_message_container', '.sp_message_container', '#qc-cmp2-container',
            '[aria-label*="cookie"]', '[aria-label*="Cookie"]', '[id*="consent"]',
            'aside', '.ad-slot', '.advertisement', '.right-rail',
            '.recommended-stories', '.related-articles', '.video-player-container',
            '#footer', 'footer', '.site-footer', '.persistent-player',
            '.b-right-rail__main-right-rail', '#flyout-overlay',
            '.b-header-nav-chain-custom__flyout-nav-wrapper', '.c-chain--recirc'
        ];
        selectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => el.remove());
        });
        document.querySelectorAll('html[class], body[class]').forEach(e => e.removeAttribute('class'));
        document.body.style.height = 'auto';
        document.body.style.minHeight = 'auto';
        document.documentElement.style.height = 'auto';
    }
    """
    try:
        page.evaluate(js_clean)
    except Exception:
        pass
        
    try:
        page.pdf(
            path=target_path,
            format="A4",
            print_background=True,
            margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"}
        )
        return True
    except Exception as e:
        print(f"    [!] Native PDF export error: {e}")
        return False

def run_strategy_c(target_date, target_dir, ignore_history=False):
    os.makedirs(target_dir, exist_ok=True)
    seen_urls = set() if ignore_history else load_dedup_history()
    print(f"[*] Strategy C (Native Print Penetration Engine) on Date: {target_date} (Ignore History: {ignore_history})...")
    
    candidates = []
    
    # P3 (策略 C): 17. Bloomberg, 18. S&P Global
    print("[*] Syndicating P3 (Strategy C: Bloomberg, S&P Global)...")
    # 17. 彭博社 (BNN Bloomberg 官方无墙开放站 + Bloomberg Law 深度报道)
    candidates.extend(fetch_google_news_syndication_c('site:bnnbloomberg.ca ("commodities" OR "oil" OR "gas" OR "futures" OR "rates" OR "cme")', "彭博社", "P3", target_date, seen_urls, 3))
    candidates.extend(fetch_google_news_syndication_c('site:bloomberglaw.com ("securities" OR "derivatives" OR "sec" OR "cftc")', "彭博社", "P3", target_date, seen_urls, 3))
    # 18. 标普全球洞察 (S&P Global Commodity Insights)
    candidates.extend(fetch_google_news_syndication_c('site:spglobal.com/commodityinsights ("commodities" OR "oil" OR "gas" OR "sugar" OR "petrochemical" OR "metals" OR "futures")', "标普全球", "P3", target_date, seen_urls, 3))
    
    # 去重
    unique_candidates = []
    seen = set()
    for c in candidates:
        if c["url"] not in seen:
            seen.add(c["url"])
            unique_candidates.append(c)
            
    print(f"[*] Total Strategy C candidates to process: {len(unique_candidates)}")
    
    verified_items = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # 全局拦截 BPC 付费墙样式表与跟踪
        def handle_global_route(route):
            try:
                req_url = route.request.url.lower()
                if "bwbx.io/s3/fence/fortress-client" in req_url or "sp_message_container" in req_url:
                    route.abort()
                else:
                    route.continue_()
            except Exception:
                pass
        context.route("**/*", handle_global_route)
        
        page = context.new_page()
        
        site_counter = {}
        for idx, item in enumerate(unique_candidates, 1):
            title = item["title"]
            site = item["site"]
            raw_url = item["url"]
            tier = item["tier"]
            clean_t = clean_filename(title)
            
            site_code = "Bloomberg" if "彭博" in site or "bloomberg" in site.lower() else "SPGlobal"
            site_counter[site_code] = site_counter.get(site_code, 0) + 1
            cur_site_idx = site_counter[site_code]
            
            raw_pdf_name = f"{site_code}_{cur_site_idx:02d}_{clean_t}.pdf"
            raw_pdf_path = os.path.join(target_dir, raw_pdf_name)
            
            print(f"\n[{idx}/{len(unique_candidates)}] Processing Strategy C Native Print ({tier}): {site} -> {title[:40]}...")
            real_url = resolve_real_url_playwright(page, raw_url)
            print(f"    Real URL: {real_url}")
            
            # 真实网页原生打印 PDF
            success = print_to_pdf_native(page, real_url, raw_pdf_path)
            if not success or not os.path.exists(raw_pdf_path):
                print("    [!] Failed to generate native PDF!")
                continue
                
            file_size = os.path.getsize(raw_pdf_path)
            if file_size < 1000:
                print(f"    [!] Dropped: File size ({file_size} B) too small!")
                os.remove(raw_pdf_path)
                continue
                
            with open(raw_pdf_path, "rb") as f:
                content_bytes = f.read()
                if not content_bytes.startswith(b"%PDF"):
                    print("    [!] Dropped: Missing %PDF header!")
                    os.remove(raw_pdf_path)
                    continue
                sha256_hash = hashlib.sha256(content_bytes).hexdigest()
                
            try:
                reader = pypdf.PdfReader(raw_pdf_path)
                extracted_text = "\n".join([p_el.extract_text() for p_el in reader.pages if p_el.extract_text()])
                word_count = len(extracted_text.split())
                num_pages = len(reader.pages)
            except Exception as e:
                print(f"    [!] Dropped: PDF parse error: {e}")
                os.remove(raw_pdf_path)
                continue
                
            # 严格执行全文完整度与付费墙核验（针对物理 PDF 进行段落、词数、弹窗深度审计）
            is_full_text, fail_reason, stats = verify_full_text_integrity(raw_pdf_path, original_title=title)
            if not is_full_text:
                print(f"    [!] Dropped: {fail_reason}")
                os.remove(raw_pdf_path)
                continue
                
            print(f"    ✅ Verified Strategy C Native PDF: {file_size // 1024} KB | Pages: {num_pages} | Valid Words: {stats.get('valid_words_count', word_count)}")
            
            verified_items.append({
                "tier": tier,
                "strategy": "C",
                "site": site,
                "category": "",
                "original_title": title,
                "publish_date": item["publish_date"],
                "source_url": real_url,
                "local_filename": raw_pdf_name,
                "file_size_bytes": file_size,
                "sha256": sha256_hash,
                "extracted_word_count": word_count,
                "status": "SUCCESS",
                "binary_verified": True
            })
            
        browser.close()
        
    manifest_path = os.path.join(target_dir, "manifest_strategy_c_raw.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "run_id": f"strategy_c_{target_date}",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "strategy": "C",
            "total_captured": len(verified_items),
            "items": verified_items
        }, f, indent=2, ensure_ascii=False)
        
    print(f"\n🎉 Strategy C finished! Captured {len(verified_items)} native PDF items. Manifest: {manifest_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Strategy C Penetrator (Native Playwright Print)")
    parser.add_argument("--date", type=str, default=time.strftime("%Y-%m-%d"), help="Target Date YYYY-MM-DD")
    parser.add_argument("--dir", type=str, default=None, help="Target storage dir")
    parser.add_argument("--ignore-history", action="store_true", help="Ignore deduplication history for isolated testing")
    args = parser.parse_args()
    
    target_dir = config_loader.get_target_dir(args.date, args.dir)
    run_strategy_c(args.date, target_dir, ignore_history=args.ignore_history)
