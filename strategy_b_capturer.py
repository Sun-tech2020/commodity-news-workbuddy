#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Strategy B Capturer: 策略 B 抓取标题 + 全网二次检索公开全文引擎 (Title Scraping & Cross-Search v7.0.0)
负责执行 News_Sources_Registry.md 中标注为【策略 B】的站点（共 2 站，全量抓取，无篇数上限）：
1. 英国期货期权世界 (FOW Insights, https://www.fow.com/insights)
2. Mondo Visione (MV, https://mondovisione.com/)

技术工作流：
1. 访问 FOW Insights 列表页与 Mondo Visione 列表页/RSS，抓取当日文章卡片（标题、发布日期、摘要）；
2. 严格核验发布日期属于 T 或 T-1（周一支持扩展到上周五），并命中目标主题/品种；
3. 将抓取到的标题核心词传入 Google News RSS / 全网搜索引擎进行二次检索，寻找公开来源全文（如 Investing.com, FIA, PR Newswire, 交易所公告等）；
   - 若原站落地页为公开完整全文，亦可作为直接候选；若存在付费墙阻断，则自动采用二次检索公开替代源；
   - 独家无公开替代源文章按规则优雅跳过；
4. 联合溯源标注为 "英国期货期权世界（FOW Insights / <公开源>）" 或 "Mondo Visione（MV / <公开源>）"；
5. Playwright 原生打印 PDF，严格审计魔数 b'%PDF'、字数 >= 150 词与物理日期；
6. 产出 manifest_strategy_b_raw.json。
"""

import os
import sys
import json
import time
import re
import argparse
import hashlib
import urllib.request
from datetime import datetime, timedelta
import feedparser
from bs4 import BeautifulSoup
import pypdf
from playwright.sync_api import sync_playwright
from full_text_verifier import verify_full_text_integrity
import config_loader

EXEMPT_KEYWORDS = [
    "regulation", "regulator", "regulatory", "compliance", "enforcement",
    "fraud", "clone", "warning", "penalties", "fine", "restitution", "lawsuit",
    "sec", "cftc", "fca", "esma", "iosco", "sebi", "bafin", "osc",
    "rule", "guidance", "consultation", "statement", "whistleblower",
    "innovation", "fintech", "ai", "carbon", "esg", "tokenization", "blockchain",
    "new contract", "launch", "listing", "index", "market maker",
    "partnership", "mou", "alliance", "acquisition", "clearing", "settlement",
    "prediction market", "event contract", "kalshi", "polymarket", "forecastex",
    "trading volume", "adv", "open interest", "exchange", "futures", "options", "derivatives",
    "clearing house", "margin", "liquidity", "etf", "commodities", "crypto"
]

TARGET_COMMODITIES = [
    "sugar", "white sugar", "raw sugar", "cotton", "cotton yarn",
    "rapeseed", "canola", "rapeseed oil", "canola oil", "rapeseed meal",
    "peanut", "peanuts", "groundnut", "apple", "apples", "jujube", "red date",
    "pta", "purified terephthalic acid", "methanol", "urea",
    "polyester", "staple fiber", "psf", "soda ash", "caustic soda",
    "px", "paraxylene", "pet flakes", "bottle-grade pet",
    "glass", "thermal coal", "ferrosilicon", "silicon manganese"
]

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
            rf"\b{dt.strftime('%B')}\s+0?{d_str},?\s+{dt.year}\b",
            rf"\b{dt.strftime('%b')}\.?\s+0?{d_str},?\s+{dt.year}\b",
            rf"\b0?{d_str}(?:st|nd|rd|th)?\s+{dt.strftime('%B')},?\s+{dt.year}\b",
            rf"\b0?{d_str}(?:st|nd|rd|th)?\s+{dt.strftime('%b')}\.?,?\s+{dt.year}\b",
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

def parse_fow_date_string(date_str):
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_str).strip()
    for fmt in ["%d %B, %Y", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%Y-%m-%d"]:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None

def fetch_fow_insights_articles(target_date):
    """FOW Insights 网页卡片扫描 + 分页回溯"""
    print("[*] Strategy B: Accessing FOW Insights (Multi-page traversal)...")
    articles = []
    
    window = get_target_date_window(target_date)
    valid_dates = window["valid_dates_set"]
    
    seen_titles = set()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            page.goto("https://www.fow.com/insights", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2.0)
            
            # 清除干扰点击的 Cookie 弹窗遮罩
            page.evaluate('''() => {
                document.querySelectorAll('.cky-consent-container, .cky-overlay, #cky-banner').forEach(el => el.remove());
            }''')
            
            current_page = 1
            max_traversal_steps = 65
            cutoff_date = window["cutoff_date"]
            
            for step in range(1, max_traversal_steps + 1):
                page.evaluate('''() => {
                    document.querySelectorAll('.cky-consent-container, .cky-overlay, #cky-banner').forEach(el => el.remove());
                }''')
                
                content = page.content()
                soup = BeautifulSoup(content, "html.parser")
                links = soup.find_all("a", href=True)
                
                dates_on_page = []
                for a in links:
                    href = a["href"].strip()
                    if not href.startswith("/insights/"):
                        continue
                        
                    t_cand = a.find(["h5", "h2", "h3", "h4", "span"])
                    title_text = t_cand.get_text(strip=True) if t_cand else a.get_text(strip=True)
                    title_text = re.sub(r'^\d+(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+\d{4}', '', title_text).strip()
                    
                    if len(title_text) < 10 or title_text in seen_titles:
                        continue
                        
                    p_tags = a.find_all("p")
                    pub_date = None
                    summary_text = ""
                    
                    for p_item in p_tags:
                        p_txt = p_item.get_text(strip=True)
                        parsed_d = parse_fow_date_string(p_txt)
                        if parsed_d:
                            pub_date = parsed_d
                            dates_on_page.append(parsed_d)
                        elif len(p_txt) > 25:
                            summary_text = p_txt
                            
                    if not pub_date or pub_date not in valid_dates:
                        continue
                        
                    if not matches_theme_or_commodity(title_text, summary_text):
                        continue
                        
                    full_fow_url = "https://www.fow.com" + href
                    seen_titles.add(title_text)
                    articles.append({
                        "source_name": "英国期货期权世界 (FOW Insights)",
                        "site_code": "FOW",
                        "title": title_text,
                        "publish_date": pub_date,
                        "summary": summary_text,
                        "orig_url": full_fow_url
                    })
                    print(f"    [+] FOW Qualified ({pub_date}): {title_text}")
                    
                if dates_on_page and all(d < cutoff_date for d in dates_on_page):
                    print(f"    [*] Reached articles older than cutoff ({cutoff_date}). Stopping FOW traversal.")
                    break
                    
                # 寻找下一页按钮
                next_page = current_page + 1
                btn = page.query_selector(f'button[aria-label="Page {next_page}"]')
                if not btn:
                    buttons = page.query_selector_all('nav[aria-label="Pagination"] button')
                    max_num = current_page
                    for b in buttons:
                        label = b.get_attribute("aria-label") or ""
                        if label.startswith("Page "):
                            try:
                                num = int(label.replace("Page ", ""))
                                if num > max_num:
                                    max_num = num
                                    btn = b
                            except Exception:
                                pass
                    if max_num > current_page:
                        next_page = max_num
                    else:
                        print("    [*] No more pagination forward buttons found on FOW.")
                        break
                        
                current_page = next_page
                btn.click(force=True)
                time.sleep(2.0)
                
        except Exception as e:
            print(f"[!] FOW dynamic traversal error: {e}")
        finally:
            browser.close()
        
    # Google News Syndication 辅助索引
    try:
        d_min = window["valid_dates"][-1]
        dt_max = datetime.strptime(window["valid_dates"][0], "%Y-%m-%d") + timedelta(days=1)
        d_max = dt_max.strftime("%Y-%m-%d")
        
        rss_query = f"site:fow.com after:{d_min} before:{d_max}"
        rss_url = f"https://news.google.com/rss/search?q={rss_query.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
        f = feedparser.parse(rss_url)
        for entry in f.entries:
            t = entry.get("title", "").strip()
            clean_t = re.sub(r"\s+-\s+[^-]+$", "", t).strip()
            pub_date = ""
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub_date = time.strftime("%Y-%m-%d", entry.published_parsed)
            if pub_date in valid_dates and clean_t not in seen_titles:
                if matches_theme_or_commodity(clean_t, entry.get("summary", "")):
                    seen_titles.add(clean_t)
                    articles.append({
                        "source_name": "英国期货期权世界 (FOW Insights)",
                        "site_code": "FOW",
                        "title": clean_t,
                        "publish_date": pub_date,
                        "summary": entry.get("summary", ""),
                        "orig_url": entry.get("link", "")
                    })
    except Exception as e:
        print(f"[!] Google News FOW indexing error: {e}")
        
    print(f"[*] Found {len(articles)} total valid articles from FOW Insights across all pages.")
    return articles

def parse_mondo_date_from_slug(slug):
    """从 Mondo Visione 的 URL slug 中提取 YYYY-MM-DD 日期"""
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

def fetch_mondo_visione_articles(target_date, seen_urls):
    """Mondo Visione (MV) 标题卡片抓取 (RSS + Web 分页遍历 + Google News 索引)"""
    print("[*] Strategy B: Accessing Mondo Visione (RSS + Web traversal)...")
    articles = []
    seen = set(seen_urls)
    seen_titles = set()
    
    window = get_target_date_window(target_date)
    valid_dates = window["valid_dates_set"]
    cutoff_date = window["cutoff_date"]
    
    # 1. RSS 源
    feed_url = "https://mondovisione.com/media-and-resources/news/rss/"
    try:
        f = safe_fetch_rss(feed_url)
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
                
            if pub_date not in valid_dates or link in seen or title in seen_titles:
                continue
            if not matches_theme_or_commodity(title, summary):
                continue
                
            seen.add(link)
            seen_titles.add(title)
            articles.append({
                "source_name": "Mondo Visione",
                "site_code": "Mondo",
                "title": title,
                "publish_date": pub_date,
                "summary": summary,
                "orig_url": link
            })
    except Exception as e:
        print(f"[!] Error fetching Mondo Visione RSS: {e}")
        
    # 2. Google News 回溯索引
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
            f_g = safe_fetch_rss(g_url)
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
                if dec_url in seen or t_clean in seen_titles:
                    continue
                pub_d = parse_mondo_date_from_slug(dec_url)
                if not pub_d and hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_d = time.strftime("%Y-%m-%d", entry.published_parsed)
                if pub_d and pub_d in valid_dates and matches_theme_or_commodity(t_clean):
                    seen.add(dec_url)
                    seen_titles.add(t_clean)
                    articles.append({
                        "source_name": "Mondo Visione",
                        "site_code": "Mondo",
                        "title": t_clean,
                        "publish_date": pub_d,
                        "summary": entry.get("summary", ""),
                        "orig_url": dec_url
                    })
                    print(f"    [+] Mondo Visione (Google Index) Qualified ({pub_d}): {t_clean}")
    except Exception as e:
        print(f"[!] Mondo Visione Google Index helper error: {e}")

    # 3. 多页 Web 列表翻页遍历
    import urllib.request
    for page_no in range(1, 10):
        page_url = f"https://mondovisione.com/media-and-resources/news/?page={page_no}"
        html = None
        for retry in range(2):
            try:
                req = urllib.request.Request(page_url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
                html = urllib.request.urlopen(req, timeout=8).read().decode("utf-8")
                break
            except Exception:
                time.sleep(0.5)
                
        if not html:
            continue
            
        try:
            soup = BeautifulSoup(html, "html.parser")
            found_in_page = 0
            has_older = False
            
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
                            if full_url not in seen and title not in seen_titles:
                                seen.add(full_url)
                                seen_titles.add(title)
                                if matches_theme_or_commodity(title):
                                    articles.append({
                                        "source_name": "Mondo Visione",
                                        "site_code": "Mondo",
                                        "title": title,
                                        "publish_date": item_date,
                                        "summary": "",
                                        "orig_url": full_url
                                    })
                        elif item_date < cutoff_date:
                            has_older = True
                            
            if has_older and found_in_page == 0 and len(articles) > 0:
                print(f"    [*] Reached Mondo dates older than {cutoff_date} at page {page_no}. Stopping pagination.")
                break
        except Exception as e:
            print(f"    [!] Error parsing Mondo Visione page {page_no}: {e}")
            break
            
    print(f"[*] Found {len(articles)} total valid articles from Mondo Visione.")
    return articles

def safe_fetch_rss(url, timeout=12):
    """高鲁棒性 RSS 获取与解析器，具备沙箱代理自适应回退能力"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*'
    }
    req = urllib.request.Request(url, headers=headers)
    last_err = None
    
    # 1. 优先使用当前环境设置请求
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            f = feedparser.parse(data)
            if not f.bozo or len(f.entries) > 0:
                return f
            last_err = getattr(f, "bozo_exception", "Parse error")
    except Exception as e:
        last_err = e
        
    # 2. 若代理阻断或报错（如 502/403），自动绕过代理直连重试
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as resp:
            data = resp.read()
            f = feedparser.parse(data)
            if not f.bozo or len(f.entries) > 0:
                return f
            last_err = getattr(f, "bozo_exception", "Parse error")
    except Exception as e:
        last_err = e
        
    # 3. 回退到 feedparser 原生重试
    try:
        f = feedparser.parse(url)
        if f.entries:
            return f
        if f.bozo and getattr(f, "bozo_exception", None):
            last_err = f.bozo_exception
    except Exception as e:
        last_err = e
        
    if last_err:
        print(f"    [!] Warning: RSS retrieval error: {last_err}")
    return feedparser.parse("")

def cross_search_public_articles(title, target_date, seen_urls, max_candidates=4):
    """
    全网二次搜索公开全文引擎：
    接收文章标题，在 Google News / 全网检索匹配公开全文来源
    """
    clean_kw = re.sub(r"[^\w\s]", "", title)
    words = clean_kw.split()
    query_words = words[:6] if len(words) >= 6 else words
    query = " ".join(query_words)
    
    window = get_target_date_window(target_date)
    d_min = window["valid_dates"][-1]
    dt_max = datetime.strptime(window["valid_dates"][0], "%Y-%m-%d") + timedelta(days=1)
    d_max = dt_max.strftime("%Y-%m-%d")
    
    queries_to_try = [
        f"{query} after:{d_min} before:{d_max}",
        f"{query} {window['google_when']}",
        query
    ]
    
    candidates = []
    seen_links = set()
    
    for q_try in queries_to_try:
        if len(candidates) >= max_candidates:
            break
        rss_url = f"https://news.google.com/rss/search?q={q_try.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
        try:
            f = safe_fetch_rss(rss_url)
            for entry in f.entries:
                link = entry.get("link", "")
                e_title = entry.get("title", "")
                if not link or link in seen_urls or link in seen_links:
                    continue
                seen_links.add(link)
                source_match = re.search(r"\s+-\s+([^-]+)$", e_title)
                pub_source = source_match.group(1).strip() if source_match else "Public Cross-Search"
                candidates.append({
                    "public_url": link,
                    "public_title": e_title,
                    "public_source": pub_source
                })
                if len(candidates) >= max_candidates:
                    break
        except Exception as e:
            print(f"    [!] Cross-search query error ({q_try}): {e}")
            
    return candidates

def resolve_real_url(raw_url):
    """解析真实 URL，通过 googlenewsdecoder 毫秒级直解原始媒体源落地页"""
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
            
    if raw_url.startswith("http://www.mondovisione.com/"):
        return raw_url.replace("http://www.mondovisione.com/", "https://mondovisione.com/")
    if raw_url.startswith("http://"):
        return "https://" + raw_url[7:]
    return raw_url

def print_to_pdf_native(page, url, target_path):
    """高保真网页原生打印 PDF"""
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
                "User-Agent": "CommodityNewsScraper/2.0 (commodity_news_agent@internal.com)",
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
            margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"}
        )
        return True
    except Exception as e:
        print(f"    [!] PDF export error: {e}")
        return False

def run_strategy_b(target_date, target_dir, source_filter="all", ignore_history=False):
    """
    执行策略 B（抓取标题 + 全网二次检索）：
    覆盖 FOW Insights 和 Mondo Visione（全量抓取，无篇数上限）
    """
    os.makedirs(target_dir, exist_ok=True)
    seen_urls = load_dedup_history(ignore_history=ignore_history)
    print(f"[*] Strategy B (Title Scraping & Cross-Search): Scanning FOW & Mondo Visione on Date: {target_date} (Filter: {source_filter}, Ignore History: {ignore_history})...")
    
    gathered_articles = []
    
    # 1. 抓取 FOW Insights
    if source_filter in ["all", "fow"]:
        fow_items = fetch_fow_insights_articles(target_date)
        gathered_articles.extend(fow_items)
        
    # 2. 抓取 Mondo Visione
    if source_filter in ["all", "mv"]:
        mv_items = fetch_mondo_visione_articles(target_date, seen_urls)
        gathered_articles.extend(mv_items)
        
    verified_items = []
    
    if not gathered_articles:
        print("[*] No target articles found from FOW or Mondo Visione today. Proceeding with empty result.")
    else:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            for idx, art in enumerate(gathered_articles, 1):
                raw_title = art["title"]
                art_date = art["publish_date"]
                site_code = art["site_code"]
                source_name = art["source_name"]
                orig_url = art["orig_url"]
                
                print(f"\n[{idx}/{len(gathered_articles)}] Strategy B processing: [{site_code}] {raw_title[:45]}...")
                
                # 候选队列构建：如果是 Mondo Visione，先将自身原网址作为首选候选；之后追加全网二次检索
                candidate_queue = []
                if site_code == "Mondo" and orig_url:
                    candidate_queue.append({
                        "public_url": orig_url,
                        "public_title": raw_title,
                        "public_source": "Mondo Visione"
                    })
                    
                # 全网二次检索候选源
                cross_candidates = cross_search_public_articles(raw_title, target_date, seen_urls)
                candidate_queue.extend(cross_candidates)
                
                if not candidate_queue:
                    print("    [!] No public cross-search match found (Exclusive paywall story). Skipping.")
                    continue
                    
                captured_for_article = False
                clean_t = clean_filename(raw_title)
                raw_pdf_name = f"{site_code}_{idx:02d}_{clean_t}.pdf"
                raw_pdf_path = os.path.join(target_dir, raw_pdf_name)
                
                for c_idx, cand in enumerate(candidate_queue, 1):
                    pub_url = cand["public_url"]
                    pub_source = cand["public_source"]
                    
                    if pub_source == "Mondo Visione":
                        joint_site_name = "Mondo Visione"
                    elif "FOW" in site_code:
                        joint_site_name = f"英国期货期权世界（FOW Insights / {pub_source}）"
                    else:
                        joint_site_name = f"Mondo Visione（MV / {pub_source}）"
                        
                    real_pub_url = resolve_real_url(pub_url)
                    print(f"    Candidate {c_idx}/{len(candidate_queue)}: {pub_source} -> {real_pub_url[:60]}...")
                    
                    if os.path.exists(raw_pdf_path):
                        os.remove(raw_pdf_path)
                        
                    success = print_to_pdf_native(page, real_pub_url, raw_pdf_path)
                    if not success or not os.path.exists(raw_pdf_path):
                        continue
                        
                    file_size = os.path.getsize(raw_pdf_path)
                    if file_size < 1000:
                        os.remove(raw_pdf_path)
                        continue
                        
                    with open(raw_pdf_path, "rb") as f:
                        content_bytes = f.read()
                        if not content_bytes.startswith(b"%PDF"):
                            os.remove(raw_pdf_path)
                            continue
                        sha256_hash = hashlib.sha256(content_bytes).hexdigest()
                        
                    try:
                        reader = pypdf.PdfReader(raw_pdf_path)
                        extracted_text = "\n".join([p_el.extract_text() for p_el in reader.pages if p_el.extract_text()])
                        word_count = len(extracted_text.split())
                        num_pages = len(reader.pages)
                    except Exception:
                        os.remove(raw_pdf_path)
                        continue
                        
                    # 严格执行全文完整度与付费墙核验
                    min_words_req = 80 if site_code == "Mondo" and pub_source == "Mondo Visione" else 120
                    is_full_text, fail_reason, stats = verify_full_text_integrity(
                        raw_pdf_path,
                        original_title=raw_title,
                        min_paragraphs=1,
                        min_words=min_words_req
                    )
                    if not is_full_text:
                        print(f"    [!] Candidate rejected: {fail_reason}. Trying next candidate...")
                        os.remove(raw_pdf_path)
                        continue
                        
                    has_valid_date = is_strict_date_in_text(extracted_text, target_date)
                    if not has_valid_date and art_date != target_date:
                        print(f"    [!] Candidate rejected: Missing strict date ({target_date}) in text!")
                        os.remove(raw_pdf_path)
                        continue
                        
                    print(f"    ✅ Verified Strategy B Full-Text PDF: {file_size // 1024} KB | Pages: {num_pages} | Valid Words: {stats.get('valid_words_count', word_count)}")
                    
                    verified_items.append({
                        "tier": "P1",
                        "strategy": "B",
                        "site": joint_site_name,
                        "category": "",
                        "original_title": raw_title,
                        "publish_date": art_date,
                        "source_url": real_pub_url,
                        "local_filename": raw_pdf_name,
                        "file_size_bytes": file_size,
                        "sha256": sha256_hash,
                        "extracted_word_count": word_count,
                        "status": "SUCCESS",
                        "binary_verified": True
                    })
                    captured_for_article = True
                    break
                    
                if not captured_for_article:
                    print(f"    [!] Dropped: All candidates failed validation for: {raw_title[:35]}")
                    
            browser.close()
            
    manifest_path = os.path.join(target_dir, "manifest_strategy_b_raw.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "run_id": f"strategy_b_{target_date}",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "strategy": "B",
            "source_filter": source_filter,
            "total_captured": len(verified_items),
            "items": verified_items
        }, f, indent=2, ensure_ascii=False)
        
    print(f"\n🎉 Strategy B finished! Captured {len(verified_items)} items. Manifest: {manifest_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Strategy B Capturer (Title Scraping & Cross Search for FOW & Mondo Visione)")
    parser.add_argument("--source", type=str, default="all", choices=["all", "fow", "mv"], help="Source filter: all, fow, or mv")
    parser.add_argument("--date", type=str, default=time.strftime("%Y-%m-%d"), help="Target Date YYYY-MM-DD")
    parser.add_argument("--dir", type=str, default=None, help="Target storage dir")
    parser.add_argument("--ignore-history", action="store_true", help="Ignore deduplication history for isolated testing")
    args = parser.parse_args()
    
    try:
        from config_loader import get_target_dir
        target_dir = get_target_dir(args.date, cli_dir=args.dir)
    except Exception:
        target_dir = args.dir if args.dir else os.path.expanduser(f"~/Documents/Obsidian Vault/工作/新闻/{args.date} 新闻")
    run_strategy_b(args.date, target_dir, source_filter=args.source, ignore_history=args.ignore_history)
