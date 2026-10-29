import config_loader
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Strategy B Capturer: 策略 B 直接下载抓取引擎 (Direct Web/Native Capture)
负责执行 News_Sources_Registry.md 中标注为【策略 B】的站点：
- P1: Mondo Visione（全量抓取，无篇数上限）
- P2: 官方与公开聚合源（共 14 个：CFTC, ESMA, FCA, FIA, ICE, LME, CME, ISDA, DMIST, SEBI, 雅虎财经, NewsNow, SEC, IOSCO，单站 0~3 篇）

支持命令行参数：
--priority P1 (仅执行 P1) 或 --priority P2 (仅执行 P2) 或 --priority P1,P2
--date <YYYY-MM-DD>
--dir <目标存证目录>
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
    "trading volume", "adv", "open interest", "exchange"
]

SITE_SHORT_CODE_MAP = {
    "Mondo Visione": "Mondo",
    "美国商品期货交易委员会（CFTC）": "CFTC",
    "欧洲证券及市场管理局（ESMA）": "ESMA",
    "英国金融行为监管局（FCA）": "FSA",
    "英国金融行为监管局（FSA）": "FSA",
    "国际期货业协会（FIA）": "FIA",
    "期货业协会（FIA）": "FIA",
    "洲际交易所（ICE）": "ICE",
    "伦敦金属交易所（LME）": "LME",
    "芝商所（CME）": "CME",
    "国际掉期与衍生工具协会（ISDA）": "ISDA",
    "国际掉期与衍生品协会（ISDA）": "ISDA",
    "衍生品市场标准研究所（DMIST）": "DMIST",
    "衍生品市场标准化倡议组织（DMIST）": "DMIST",
    "印度证监会（SEBI）": "SEBI",
    "印度证券交易委员会（SEBI）": "SEBI",
    "雅虎财经": "Yahoo",
    "NewsNow": "NewsNow",
    "美国证券交易委员（SEC）": "SEC",
    "美国证券交易委员会（SEC）": "SEC",
    "国际证监会组织（IOSCO）": "IOSCO"
}

def get_site_code(site_name):
    for k, v in SITE_SHORT_CODE_MAP.items():
        if k in site_name or site_name in k:
            return v
    clean = re.sub(r'[^A-Za-z0-9]', '', site_name)
    return clean[:8] if clean else "News"

def load_dedup_history(ignore_history=False):
    if ignore_history:
        return set()
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

def resolve_real_url(page, raw_url):
    """解析真实 URL，通过 googlenewsdecoder 毫秒级直解原始媒体源网址，彻底绕过 Google 重定向"""
    if "news.google.com" in raw_url:
        try:
            import googlenewsdecoder
            dec_res = googlenewsdecoder.new_decoderv1(raw_url)
            if dec_res and dec_res.get("status") and dec_res.get("decoded_url"):
                real = dec_res["decoded_url"]
                if real.startswith("http://"):
                    real = "https://" + real[7:]
                return real
        except Exception as e:
            pass
            
    if raw_url.startswith("http://www.mondovisione.com/"):
        return raw_url.replace("http://www.mondovisione.com/", "https://mondovisione.com/")
    if raw_url.startswith("http://"):
        return "https://" + raw_url[7:]
    return raw_url

def parse_mondo_date_from_slug(slug):
    """从 Mondo Visione 的 URL slug 中智能提取 YYYY-MM-DD 日期"""
    m = re.search(r'-(\d{4})(\d{1,4})/?$', slug)
    if not m:
        return ''
    year = int(m.group(1))
    rest = m.group(2)
    if len(rest) == 3:
        month = int(rest[0])
        day = int(rest[1:])
    elif len(rest) == 4:
        month = int(rest[:2])
        day = int(rest[2:])
    elif len(rest) == 2:
        month = int(rest[0])
        day = int(rest[1])
    else:
        return ''
    if 1 <= month <= 12 and 1 <= day <= 31:
        return f'{year:04d}-{month:02d}-{day:02d}'
    return ''

def fetch_mondo_visione(target_date, seen_urls):
    """Mondo Visione (P1 / 策略 B: RSS + Web 分页遍历全量抓取，无篇数上限)"""
    items = []
    seen = set(seen_urls)
    window = get_target_date_window(target_date)
    valid_dates = window["valid_dates_set"]
    cutoff_date = window["cutoff_date"]
    
    # 1. 尝试 RSS 源（获取最新 20 条）
    feed_url = "https://mondovisione.com/media-and-resources/news/rss/"
    try:
        f = feedparser.parse(feed_url)
        for entry in f.entries:
            link = entry.get("link", "").strip()
            if link.startswith("http://www.mondovisione.com/"):
                link = link.replace("http://www.mondovisione.com/", "https://mondovisione.com/")
            elif link.startswith("http://"):
                link = "https://" + link[7:]
                
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "").strip()
            
            pub_date = ""
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub_date = time.strftime("%Y-%m-%d", entry.published_parsed)
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                pub_date = time.strftime("%Y-%m-%d", entry.updated_parsed)
                
            if pub_date not in valid_dates or link in seen:
                continue
            if not matches_theme_or_commodity(title, summary):
                continue
                
            seen.add(link)
            items.append({
                "tier": "P1",
                "strategy": "B",
                "site": "Mondo Visione",
                "category": "",
                "title": title,
                "url": link,
                "publish_date": pub_date,
                "summary": summary
            })
    except Exception as e:
        print(f"[!] Error fetching Mondo Visione RSS: {e}")
        
    # 1.5 Google News 对 Mondo Visione 精确回溯索引 (确保历史采编与当日更新秒级召回)
    try:
        d_min = window["valid_dates"][-1]
        dt_max = datetime.strptime(window["valid_dates"][0], "%Y-%m-%d") + timedelta(days=1)
        d_max = dt_max.strftime("%Y-%m-%d")
        queries = [
            f"site:mondovisione.com after:{d_min} before:{d_max}",
            f"site:mondovisione.com {window['google_when']}"
        ]
        import googlenewsdecoder
        for q in queries:
            g_url = f"https://news.google.com/rss/search?q={q.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
            f_g = feedparser.parse(g_url)
            for entry in f_g.entries:
                t = entry.get("title", "").strip()
                t_clean = re.sub(r"\s+-\s+Mondo Visione.*$", "", t, flags=re.IGNORECASE).strip()
                link = entry.get("link", "")
                dec_url = link
                if "news.google.com" in link:
                    try:
                        res = googlenewsdecoder.new_decoderv1(link)
                        if res and res.get("status") and res.get("decoded_url"):
                            dec_url = res["decoded_url"]
                    except Exception:
                        pass
                if dec_url in seen:
                    continue
                pub_d = parse_mondo_date_from_slug(dec_url)
                if not pub_d and hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_d = time.strftime("%Y-%m-%d", entry.published_parsed)
                if pub_d and pub_d in valid_dates and matches_theme_or_commodity(t_clean):
                    seen.add(dec_url)
                    items.append({
                        "tier": "P1",
                        "strategy": "B",
                        "site": "Mondo Visione",
                        "category": "",
                        "title": t_clean,
                        "url": dec_url,
                        "publish_date": pub_d,
                        "summary": entry.get("summary", "")
                    })
                    print(f"    [+] Mondo Visione (Google Index) Qualified ({pub_d}): {t_clean}")
    except Exception as e:
        print(f"[!] Mondo Visione Google Index helper error: {e}")

    # 2. 多页 Web 列表翻页遍历（防止单页或 RSS 遗漏当天/前一天大量新闻）
    import urllib.request
    print("[*] Traversing Mondo Visione web pagination for full coverage...")
    for page in range(1, 10):
        page_url = f"https://mondovisione.com/media-and-resources/news/?page={page}"
        html = None
        for retry in range(2):
            try:
                req = urllib.request.Request(page_url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
                html = urllib.request.urlopen(req, timeout=8).read().decode("utf-8")
                break
            except Exception as e:
                time.sleep(0.5)
                
        if not html:
            continue
            
        try:
            soup = BeautifulSoup(html, "html.parser")
            
            found_in_page = 0
            has_older_than_cutoff = False
            
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                title = a.get_text(strip=True)
                if "/media-and-resources/news/" in href and href != "/media-and-resources/news/" and len(title) > 15:
                    item_date = parse_mondo_date_from_slug(href)
                    full_url = href if href.startswith("http") else "https://mondovisione.com" + href
                    if full_url.startswith("http://www.mondovisione.com/"):
                        full_url = full_url.replace("http://www.mondovisione.com/", "https://mondovisione.com/")
                    elif full_url.startswith("http://"):
                        full_url = "https://" + full_url[7:]
                        
                    if item_date:
                        if item_date in valid_dates:
                            found_in_page += 1
                            if full_url not in seen:
                                seen.add(full_url)
                                if matches_theme_or_commodity(title):
                                    items.append({
                                        "tier": "P1",
                                        "strategy": "B",
                                        "site": "Mondo Visione",
                                        "category": "",
                                        "title": title,
                                        "url": full_url,
                                        "publish_date": item_date,
                                        "summary": ""
                                    })
                        elif item_date < cutoff_date:
                            has_older_than_cutoff = True
            
            print(f"    Page {page}: found {found_in_page} T/T-1 items (total qualified so far: {len(items)})")
            if has_older_than_cutoff and found_in_page == 0 and len(items) > 0:
                print(f"    [*] Reached dates older than {cutoff_date} at page {page}. Stopping pagination.")
                break
        except Exception as e:
            print(f"    [!] Error parsing Mondo Visione page {page}: {e}")
            break
            
    print(f"[*] Total Mondo Visione full items gathered: {len(items)}")
    return items

def parse_fca_raw_date(raw_pub):
    """解析 FCA 原始时间格式"""
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', raw_pub)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m2 = re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', raw_pub)
    if m2:
        day_str, month_str, year_str = m2.group(1), m2.group(2), m2.group(3)
        try:
            dt = datetime.strptime(f'{month_str} {day_str} {year_str}', '%B %d %Y')
            return dt.strftime('%Y-%m-%d')
        except Exception:
            pass
    return ''

def fetch_fca(target_date, seen_urls):
    """英国金融行为监管局 FCA (P2 / 策略 B)"""
    items = []
    feed_url = "https://www.fca.org.uk/news/rss.xml"
    try:
        f = feedparser.parse(feed_url)
        window = get_target_date_window(target_date)
        valid_dates = window["valid_dates_set"]
        
        for entry in f.entries:
            link = entry.get("link", "")
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            
            pub_date = ""
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub_date = time.strftime("%Y-%m-%d", entry.published_parsed)
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                pub_date = time.strftime("%Y-%m-%d", entry.updated_parsed)
            else:
                pub_date = parse_fca_raw_date(entry.get("published", ""))
                
            if pub_date not in valid_dates:
                continue
            if link in seen_urls:
                continue
            if not matches_theme_or_commodity(title, summary):
                continue
                
            items.append({
                "tier": "P2",
                "strategy": "B",
                "site": "英国金融行为监管局（FCA）",
                "category": "",
                "title": title,
                "url": link,
                "publish_date": pub_date,
                "summary": summary
            })
            if len(items) >= 3:
                break
    except Exception as e:
        print(f"[!] Error fetching FCA RSS: {e}")
    return items

NON_FINANCIAL_EXCLUDE = [
    "sugar land", "sugar-free", "recipe", "diet", "blood sugar", "lagree",
    "cookies", "cake", "yoghurt", "yogurt", "baking", "sweet", "flavor", "toddler", "children"
]

def fetch_newsnow(target_date, seen_urls, max_count=3):
    """NewsNow 重点品种分类实时直爬（白糖、棉花、农产品）"""
    import urllib.request
    import ssl
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    urls = [
        ("https://www.newsnow.co.uk/h/Business+&+Finance/Commodities/Sugar", "白糖"),
        ("https://www.newsnow.co.uk/h/Business+&+Finance/Commodities/Cotton", "棉花"),
        ("https://www.newsnow.co.uk/h/Business+&+Finance/Commodities/Agriculture", "综合农业")
    ]
    
    window = get_target_date_window(target_date)
    valid_dates = window["valid_dates_set"]
    
    items = []
    seen_links = set()
    
    for u, cat in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
            raw = urllib.request.urlopen(req, context=ctx, timeout=10).read()
            html = raw.decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/A/" in href:
                    title = a.get_text(strip=True)
                    if len(title) < 15 or href in seen_links or href in seen_urls:
                        continue
                    if any(ex in title.lower() for ex in NON_FINANCIAL_EXCLUDE):
                        continue
                    if not matches_theme_or_commodity(title):
                        continue
                    
                    parent = a.find_parent("div")
                    src_tag = parent.find("span", class_="src") if parent else None
                    src_name = src_tag.get_text(strip=True) if src_tag else "Public Web"
                    
                    seen_links.add(href)
                    items.append({
                        "tier": "P2",
                        "strategy": "B",
                        "site": f"NewsNow（{src_name}）",
                        "category": "",
                        "title": title,
                        "url": href,
                        "publish_date": target_date,
                        "summary": ""
                    })
                    if len(items) >= max_count:
                        return items
        except Exception as e:
            print(f"[!] Error fetching NewsNow ({u}): {e}")
    return items

def fetch_google_news_syndication_b(query, site_name, tier, target_date, seen_urls, max_count=3):
    """针对 P2 官方与公开聚合源的策略 B 检索"""
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
                    "strategy": "B",
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
            print(f"[!] Error fetching Google syndication for {site_name} ({q_str}): {e}")
            
    return items

def print_to_pdf_native(page, url, target_path):
    """方案 1：无遮罩高保真网页原生打印 PDF（毫秒级极速渲染版）"""
    if url.startswith("http://"):
        url = "https://" + url[7:]
        
    try:
        if url.endswith(".pdf") or ".pdf?" in url:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
            content = urllib.request.urlopen(req, timeout=15).read()
            with open(target_path, "wb") as f:
                f.write(content)
            return True
        elif "sec.gov" in url:
            import urllib.request
            req = urllib.request.Request(url, headers={
                "User-Agent": config_loader.get_user_agent(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            })
            html_content = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", errors="ignore")
            page.set_content(html_content, wait_until="domcontentloaded")
            time.sleep(0.3)
        elif "news.google.com" in url:
            page.goto(url, wait_until="domcontentloaded", timeout=12000)
            for _ in range(8):
                if "google.com" not in page.url:
                    break
                time.sleep(0.3)
        else:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=12000)
            except Exception:
                page.goto(url, wait_until="commit", timeout=8000)
                
        # 针对 Yahoo / GDPR 弹窗自动点击同意
        if any(w in page.url for w in ["consent.yahoo.com", "guce.yahoo.com", "consent.google.com"]):
            try:
                page.evaluate("""
                    () => {
                        const btns = Array.from(document.querySelectorAll('button, input[type="submit"], a'));
                        const agree = btns.find(b => /accept all|agree|accept|akzeptieren|accepter|tout accepter/i.test(b.innerText || b.value || ''));
                        if (agree) agree.click();
                    }
                """)
                time.sleep(0.8)
            except Exception:
                pass
    except Exception as e:
        print(f"    [!] Failed to load URL ({url}): {e}")
        return False
        
    time.sleep(0.5)
    
    js_clean = """
    () => {
        const selectors = [
            '#onetrust-consent-sdk', '.cookie-banner', '.modal', '.popup',
            '.overlay', '#CybotCookiebotDialog', '.ot-sdk-container',
            '#gdpr-banner', '.privacy-prompt', '.ad-banner', '.advertisement',
            '.tp-backdrop', '.tp-modal', '.consent-banner', '#consent-page'
        ];
        selectors.forEach(s => {
            document.querySelectorAll(s).forEach(el => el.remove());
        });
        document.body.style.overflow = 'auto';
        document.documentElement.style.overflow = 'auto';
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
            margin={"top": "15mm", "bottom": "15mm", "left": "15mm", "right": "15mm"}
        )
        return True
    except Exception as e:
        print(f"    [!] PDF rendering error: {e}")
        return False

def run_strategy_b(priorities, target_date, target_dir, ignore_history=False):
    os.makedirs(target_dir, exist_ok=True)
    seen_urls = load_dedup_history(ignore_history=ignore_history)
    print(f"[*] Strategy B (Direct Web/Native Capture): Scanning Priorities {priorities} on Date: {target_date} (Ignore History: {ignore_history})...")
    
    candidates = []
    
    # 1. P1 任务 (Mondo Visione)
    if "P1" in priorities:
        print("[*] Gathering P1 (Mondo Visione)...")
        candidates.extend(fetch_mondo_visione(target_date, seen_urls))
        
    # 2. P2 任务 (共 14 个官方与公开聚合源)
    if "P2" in priorities:
        print("[*] Gathering P2 sources (CFTC, ESMA, FCA, FIA, ICE, LME, CME, ISDA, DMIST, SEBI, Yahoo Finance, NewsNow, SEC, IOSCO)...")
        # 3. CFTC
        candidates.extend(fetch_google_news_syndication_b('site:cftc.gov "Press Release"', "美国商品期货交易委员会（CFTC）", "P2", target_date, seen_urls, 3))
        # 4. ESMA
        candidates.extend(fetch_google_news_syndication_b('site:esma.europa.eu', "欧洲证券及市场管理局（ESMA）", "P2", target_date, seen_urls, 3))
        # 5. FCA
        candidates.extend(fetch_fca(target_date, seen_urls))
        # 6. FIA
        candidates.extend(fetch_google_news_syndication_b('site:fia.org', "期货业协会（FIA）", "P2", target_date, seen_urls, 3))
        # 7. ICE
        candidates.extend(fetch_google_news_syndication_b('site:ir.theice.com/press', "洲际交易所（ICE）", "P2", target_date, seen_urls, 3))
        # 8. LME
        candidates.extend(fetch_google_news_syndication_b('site:lme.com', "伦敦金属交易所（LME）", "P2", target_date, seen_urls, 3))
        # 9. CME
        candidates.extend(fetch_google_news_syndication_b('site:cmegroup.com ("press release" OR "futures" OR "clearing" OR "margin")', "芝商所（CME）", "P2", target_date, seen_urls, 3))
        # 10. ISDA
        candidates.extend(fetch_google_news_syndication_b('site:isda.org', "国际掉期与衍生品协会（ISDA）", "P2", target_date, seen_urls, 3))
        # 11. DMIST
        candidates.extend(fetch_google_news_syndication_b('site:fia.org/dmist', "衍生品市场标准化倡议组织（DMIST）", "P2", target_date, seen_urls, 3))
        # 12. SEBI
        candidates.extend(fetch_google_news_syndication_b('site:sebi.gov.in', "印度证券交易委员会（SEBI）", "P2", target_date, seen_urls, 3))
        # 13. 雅虎财经
        candidates.extend(fetch_google_news_syndication_b('site:finance.yahoo.com (commodities OR futures OR "interest rate" OR "Federal Reserve")', "雅虎财经", "P2", target_date, seen_urls, 3))
        # 14. NewsNow
        candidates.extend(fetch_newsnow(target_date, seen_urls, 3))
        # 15. SEC
        candidates.extend(fetch_google_news_syndication_b('site:sec.gov/newsroom/press-releases', "美国证券交易委员会（SEC）", "P2", target_date, seen_urls, 3))
        # 16. IOSCO
        candidates.extend(fetch_google_news_syndication_b('site:iosco.org', "国际证监会组织（IOSCO）", "P2", target_date, seen_urls, 3))

    # 去重
    unique_candidates = []
    seen = set()
    for c in candidates:
        if c["url"] not in seen:
            seen.add(c["url"])
            unique_candidates.append(c)
            
    verified_items = []
    p_tag = "_".join(priorities)
    site_counter = {}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        for idx, item in enumerate(unique_candidates, 1):
            title = item["title"]
            site = item["site"]
            raw_url = item["url"]
            tier = item["tier"]
            clean_t = clean_filename(title)
            
            site_code = get_site_code(site)
            site_counter[site_code] = site_counter.get(site_code, 0) + 1
            cur_site_idx = site_counter[site_code]
            
            raw_pdf_name = f"{site_code}_{cur_site_idx:02d}_{clean_t}.pdf"
            raw_pdf_path = os.path.join(target_dir, raw_pdf_name)
            
            print(f"\n[{idx}/{len(unique_candidates)}] Processing Strategy B ({tier}): {site} -> {title[:40]}...")
            real_url = resolve_real_url(page, raw_url)
            print(f"    Real URL: {real_url}")

            
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
                
            # 严格执行全文完整度与付费墙核验（针对官方机构与公开源适配参数）
            is_reg_or_official = (tier == "P2") or ("Mondo" in site)
            min_w = 80 if is_reg_or_official else 120
            min_p = 1 if is_reg_or_official else 2

            is_full_text, fail_reason, stats = verify_full_text_integrity(
                raw_pdf_path,
                original_title=title,
                min_paragraphs=min_p,
                min_words=min_w
            )
            if not is_full_text:
                print(f"    [!] Dropped: {fail_reason}")
                os.remove(raw_pdf_path)
                continue
                
            has_valid_date = is_strict_date_in_text(extracted_text, target_date)
            if not has_valid_date and item.get("publish_date") != target_date:
                print(f"    [!] Dropped: Physical document does NOT contain strict T/T-1 date ({target_date})!")
                os.remove(raw_pdf_path)
                continue
                
            print(f"    ✅ Verified Strategy B PDF: {file_size // 1024} KB | Pages: {num_pages} | Valid Words: {stats.get('valid_words_count', word_count)}")
            
            verified_items.append({
                "tier": tier,
                "strategy": "B",
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
        
    out_manifest_name = f"manifest_strategy_b_{p_tag.lower()}_raw.json"
    manifest_path = os.path.join(target_dir, out_manifest_name)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "run_id": f"strategy_b_{p_tag.lower()}_{target_date}",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "strategy": "B",
            "priorities": priorities,
            "total_captured": len(verified_items),
            "items": verified_items
        }, f, indent=2, ensure_ascii=False)
        
    print(f"\n🎉 Strategy B ({p_tag}) finished! Captured {len(verified_items)} items. Manifest: {manifest_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Strategy B Capturer (Direct Web / Native Capture)")
    parser.add_argument("--priority", type=str, default="P1", help="Comma separated priorities, e.g. P1 or P2 or P1,P2")
    parser.add_argument("--date", type=str, default=time.strftime("%Y-%m-%d"), help="Target Date YYYY-MM-DD")
    parser.add_argument("--dir", type=str, default=None, help="Target storage dir")
    parser.add_argument("--ignore-history", action="store_true", help="Ignore deduplication history for isolated testing")
    args = parser.parse_args()
    
    target_dir = config_loader.get_target_dir(args.date, args.dir)
    priorities = [p.strip().upper() for p in args.priority.split(",")]
    run_strategy_b(priorities, args.date, target_dir, ignore_history=args.ignore_history)
