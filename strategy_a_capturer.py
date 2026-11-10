#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Strategy A Capturer: 策略 A 直接解析与下载抓取引擎 (Direct Web/Native Capture v7.0.0)
负责执行 News_Sources_Registry.md 中标注为【策略 A】的站点（共 17 站）：
1. 美国商品期货交易委员会（CFTC）
2. 芝商所（CME）
3. 洲际交易所（ICE）
4. 伦敦金属交易所（LME）
5. 期货业协会（FIA）
6. 衍生品市场标准化倡议组织（DMIST）
7. NewsNow
8. 雅虎财经
9. 纳斯达克（Nasdaq）
10. 印度证券交易委员会（SEBI）
11. 美国证券交易委员会（SEC）
12. 英国金融行为监管局（FSA/FCA）
13. 国际掉期与衍生品协会（ISDA）
14. 美国全国期货协会（NFA）
15. 欧洲证券及市场管理局（ESMA）
16. 印度经济时报（The Economic Times）
17. 国际证监会组织（IOSCO）

技术工作流：
1. 通过官方 RSS、定制直爬或 Google News Syndication 直达官方发布厅与新闻落地页；
2. 严格核验发布日期属于 T 或 T-1（周一支持扩展到上周五），并命中目标主题/品种；
3. 使用 Playwright 浏览器原生打印 (page.pdf)，100% 还原排版与图片，清除干扰弹窗与遮罩；
4. 严格审计魔数 b'%PDF'、正文段落、字数及物理正文日期；
5. 产出 manifest_strategy_a_raw.json。
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
    "trading volume", "adv", "open interest", "exchange", "futures", "options"
]

SITE_SHORT_CODE_MAP = {
    "美国商品期货交易委员会（CFTC）": "CFTC",
    "芝商所（CME）": "CME",
    "洲际交易所（ICE）": "ICE",
    "伦敦金属交易所（LME）": "LME",
    "期货业协会（FIA）": "FIA",
    "国际期货业协会（FIA）": "FIA",
    "衍生品市场标准化倡议组织（DMIST）": "DMIST",
    "衍生品市场标准研究所（DMIST）": "DMIST",
    "NewsNow": "NewsNow",
    "雅虎财经": "Yahoo",
    "纳斯达克（Nasdaq）": "Nasdaq",
    "印度证券交易委员会（SEBI）": "SEBI",
    "印度证监会（SEBI）": "SEBI",
    "美国证券交易委员会（SEC）": "SEC",
    "美国证券交易委员（SEC）": "SEC",
    "英国金融行为监管局（FCA）": "FSA",
    "英国金融行为监管局（FSA）": "FSA",
    "国际掉期与衍生品协会（ISDA）": "ISDA",
    "国际掉期与衍生工具协会（ISDA）": "ISDA",
    "美国全国期货协会（NFA）": "NFA",
    "欧洲证券及市场管理局（ESMA）": "ESMA",
    "印度经济时报": "ETimes",
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

def resolve_real_url(page, raw_url):
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
            
    if raw_url.startswith("http://"):
        return "https://" + raw_url[7:]
    return raw_url

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

def fetch_fca(target_date, seen_urls):
    """英国金融行为监管局 FCA (策略 A)"""
    items = []
    feed_url = "https://www.fca.org.uk/news/rss.xml"
    try:
        f = safe_fetch_rss(feed_url)
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
                "strategy": "A",
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
            soup = BeautifulSoup(raw, "html.parser")
            news_items = soup.find_all("div", class_=re.compile(r"hl__inner|newsfeed__item"))
            
            for el in news_items:
                a_tag = el.find("a", class_=re.compile(r"hl__link|newsfeed__link"))
                if not a_tag or not a_tag.get("href"):
                    continue
                link = a_tag["href"]
                title = a_tag.get_text(strip=True)
                
                if link in seen_urls or link in seen_links:
                    continue
                seen_links.add(link)
                
                if not matches_theme_or_commodity(title):
                    continue
                    
                items.append({
                    "tier": "P2",
                    "strategy": "A",
                    "site": "NewsNow",
                    "category": "",
                    "title": f"[{cat}] {title}",
                    "url": link,
                    "publish_date": target_date,
                    "summary": f"NewsNow {cat} 实时专栏资讯"
                })
                if len(items) >= max_count:
                    break
        except Exception as e:
            print(f"[!] Error fetching NewsNow {cat}: {e}")
        if len(items) >= max_count:
            break
            
    return items

def fetch_cftc_official(target_date, seen_urls, max_count=3):
    """美国商品期货交易委员会 CFTC 官网发布厅直采 (官方高可用直达信道)"""
    items = []
    window = get_target_date_window(target_date)
    valid_dates = window["valid_dates_set"]
    url = "https://www.cftc.gov/PressRoom/PressReleases"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")
        
        links = []
        for a in soup.find_all("a"):
            href = a.get("href", "")
            if "/PressRoom/PressReleases/" in href and len(a.text.strip()) > 15:
                full_url = "https://www.cftc.gov" + href if href.startswith("/") else href
                if full_url not in seen_urls and full_url not in [x["url"] for x in links]:
                    links.append({"title": a.text.strip(), "url": full_url})
                    
        for item in links[:6]:
            try:
                sub_req = urllib.request.Request(item["url"], headers=headers)
                with urllib.request.urlopen(sub_req, timeout=10) as s_resp:
                    sub_html = s_resp.read().decode("utf-8", errors="ignore")
                sub_soup = BeautifulSoup(sub_html, "html.parser")
                main = sub_soup.select_one("article") or sub_soup.select_one("main") or sub_soup.select_one(".region-content")
                if not main:
                    continue
                text_lines = [l.strip() for l in main.text.split("\n") if l.strip()]
                pub_d = ""
                for line in text_lines[:6]:
                    m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})", line)
                    if m:
                        month_str, day_str, year_str = m.group(1), m.group(2), m.group(3)
                        dt_obj = datetime.strptime(f"{month_str} {day_str} {year_str}", "%B %d %Y")
                        pub_d = dt_obj.strftime("%Y-%m-%d")
                        break
                if pub_d in valid_dates and matches_theme_or_commodity(item["title"]):
                    items.append({
                        "tier": "P2",
                        "strategy": "A",
                        "site": "美国商品期货交易委员会（CFTC）",
                        "category": "三、监管动态",
                        "title": item["title"],
                        "url": item["url"],
                        "publish_date": pub_d,
                        "summary": f"CFTC 官方新闻发布 (Release {item['url'].split('/')[-1]})"
                    })
                    if len(items) >= max_count:
                        break
            except Exception:
                continue
    except Exception as e:
        print(f"    [!] CFTC official direct probe note: {e}")
    return items

def fetch_sec_official(target_date, seen_urls, max_count=3):
    """美国证券交易委员会 SEC 官网发布厅直采 (官方高可用直达信道)"""
    items = []
    window = get_target_date_window(target_date)
    valid_dates = window["valid_dates_set"]
    url = "https://www.sec.gov/newsroom/press-releases"
    headers = {"User-Agent": "CommodityNewsScraper/2.0 (commodity_news_agent@internal.com)"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")
        for tr in soup.select("table tr"):
            tds = tr.select("td")
            if len(tds) >= 2:
                date_txt = tds[0].text.strip()
                title_a = tds[1].select_one("a")
                if not title_a:
                    continue
                title = title_a.text.strip()
                href = title_a.get("href", "")
                full_url = "https://www.sec.gov" + href if href.startswith("/") else href
                if full_url in seen_urls:
                    continue
                cleaned_d = re.sub(r"Sept\.", "Sep.", date_txt)
                pub_d = ""
                for fmt in ["%b. %d, %Y", "%B %d, %Y", "%b %d, %Y"]:
                    try:
                        pub_d = datetime.strptime(cleaned_d, fmt).strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        pass
                if pub_d in valid_dates and matches_theme_or_commodity(title):
                    items.append({
                        "tier": "P2",
                        "strategy": "A",
                        "site": "美国证券交易委员会（SEC）",
                        "category": "三、监管动态",
                        "title": title,
                        "url": full_url,
                        "publish_date": pub_d,
                        "summary": "SEC 官方新闻发布"
                    })
                    if len(items) >= max_count:
                        break
    except Exception as e:
        print(f"    [!] SEC official direct probe note: {e}")
    return items

def fetch_google_news_syndication_a(query, site_name, target_date, seen_urls, max_count=3):
    """针对策略 A 官方与公开聚合源的直达检索与解析"""
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
            f = safe_fetch_rss(rss_url)
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
                    "tier": "P2",
                    "strategy": "A",
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
    """无遮罩高保真网页原生打印 PDF"""
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
            is_slow_site = any(d in url.lower() for d in ["cmegroup.com", "nasdaq.com", "ice.com", "sebi.gov.in"])
            nav_timeout = 28000 if is_slow_site else 15000
            fallback_timeout = 25000 if is_slow_site else 10000
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=nav_timeout)
            except Exception as e_nav:
                if any(err in str(e_nav) for err in ["ERR_HTTP2_PROTOCOL_ERROR", "net::ERR_"]):
                    try:
                        import urllib.request
                        req = urllib.request.Request(url, headers={
                            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                        })
                        html_bytes = urllib.request.urlopen(req, timeout=12).read()
                        page.set_content(html_bytes.decode("utf-8", errors="ignore"), wait_until="domcontentloaded")
                    except Exception:
                        page.goto(url, wait_until="commit", timeout=fallback_timeout)
                else:
                    page.goto(url, wait_until="commit", timeout=fallback_timeout)
                
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

def run_strategy_a(target_date, target_dir, site_filter=None, ignore_history=False):
    """
    执行策略 A（直接解析与下载）：
    覆盖 A 类源中 17 个官方与公开聚合站点（单站 0~3 篇限额）
    """
    os.makedirs(target_dir, exist_ok=True)
    seen_urls = load_dedup_history(ignore_history=ignore_history)
    print(f"[*] Strategy A (Direct Web/Native Capture): Scanning 17 Official/Public Sources on Date: {target_date} (Ignore History: {ignore_history})...")
    
    candidates = []
    
    # 17 个策略 A 站点定向检索配置（采用官方直采 + Google 聚合双轨高可用信道）
    def get_cftc_items():
        res = fetch_cftc_official(target_date, seen_urls, 3)
        if len(res) == 0:
            res = fetch_google_news_syndication_a('site:cftc.gov "Press Release"', "美国商品期货交易委员会（CFTC）", target_date, seen_urls, 3)
        return res
        
    def get_sec_items():
        res = fetch_sec_official(target_date, seen_urls, 3)
        if len(res) == 0:
            res = fetch_google_news_syndication_a('site:sec.gov/newsroom/press-releases', "美国证券交易委员会（SEC）", target_date, seen_urls, 3)
        return res

    site_configs = [
        {"name": "美国商品期货交易委员会（CFTC）", "handler": get_cftc_items},
        {"name": "芝商所（CME）", "handler": lambda: fetch_google_news_syndication_a('site:cmegroup.com ("press release" OR "futures" OR "clearing" OR "margin")', "芝商所（CME）", target_date, seen_urls, 3)},
        {"name": "洲际交易所（ICE）", "handler": lambda: fetch_google_news_syndication_a('site:ir.theice.com/press', "洲际交易所（ICE）", target_date, seen_urls, 3)},
        {"name": "伦敦金属交易所（LME）", "handler": lambda: fetch_google_news_syndication_a('site:lme.com', "伦敦金属交易所（LME）", target_date, seen_urls, 3)},
        {"name": "期货业协会（FIA）", "handler": lambda: fetch_google_news_syndication_a('site:fia.org', "期货业协会（FIA）", target_date, seen_urls, 3)},
        {"name": "衍生品市场标准化倡议组织（DMIST）", "handler": lambda: fetch_google_news_syndication_a('site:fia.org/dmist', "衍生品市场标准化倡议组织（DMIST）", target_date, seen_urls, 3)},
        {"name": "NewsNow", "handler": lambda: fetch_newsnow(target_date, seen_urls, 3)},
        {"name": "雅虎财经", "handler": lambda: fetch_google_news_syndication_a('site:finance.yahoo.com (commodities OR futures OR "interest rate" OR "Federal Reserve")', "雅虎财经", target_date, seen_urls, 3)},
        {"name": "纳斯达克（Nasdaq）", "handler": lambda: fetch_google_news_syndication_a('site:nasdaq.com ("press release" OR commodities OR futures OR exchange)', "纳斯达克（Nasdaq）", target_date, seen_urls, 3)},
        {"name": "印度证券交易委员会（SEBI）", "handler": lambda: fetch_google_news_syndication_a('site:sebi.gov.in', "印度证券交易委员会（SEBI）", target_date, seen_urls, 3)},
        {"name": "美国证券交易委员会（SEC）", "handler": get_sec_items},
        {"name": "英国金融行为监管局（FCA）", "handler": lambda: fetch_fca(target_date, seen_urls)},
        {"name": "国际掉期与衍生品协会（ISDA）", "handler": lambda: fetch_google_news_syndication_a('site:isda.org', "国际掉期与衍生品协会（ISDA）", target_date, seen_urls, 3)},
        {"name": "美国全国期货协会（NFA）", "handler": lambda: fetch_google_news_syndication_a('site:nfa.futures.org', "美国全国期货协会（NFA）", target_date, seen_urls, 3)},
        {"name": "欧洲证券及市场管理局（ESMA）", "handler": lambda: fetch_google_news_syndication_a('site:esma.europa.eu', "欧洲证券及市场管理局（ESMA）", target_date, seen_urls, 3)},
        {"name": "印度经济时报", "handler": lambda: fetch_google_news_syndication_a('site:economictimes.indiatimes.com/markets/commodities', "印度经济时报", target_date, seen_urls, 3)},
        {"name": "国际证监会组织（IOSCO）", "handler": lambda: fetch_google_news_syndication_a('site:iosco.org', "国际证监会组织（IOSCO）", target_date, seen_urls, 3)}
    ]
    
    for cfg in site_configs:
        s_name = cfg["name"]
        if site_filter and site_filter.lower() not in s_name.lower():
            continue
        try:
            items = cfg["handler"]()
            if items:
                print(f"    [+] {s_name}: Found {len(items)} candidate items.")
                candidates.extend(items)
            else:
                print(f"    [-] {s_name}: No items matching criteria today (Allowed 0 items).")
        except Exception as e:
            print(f"    [!] Error gathering {s_name}: {e}")

    # 去重
    unique_candidates = []
    seen = set()
    for c in candidates:
        if c["url"] not in seen:
            seen.add(c["url"])
            unique_candidates.append(c)
            
    verified_items = []
    site_counter = {}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-http2",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        processed_real_urls = set()
        
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
            
            print(f"\n[{idx}/{len(unique_candidates)}] Processing Strategy A: {site} -> {title[:40]}...")
            real_url = resolve_real_url(page, raw_url)
            print(f"    Real URL: {real_url}")
            
            if real_url in processed_real_urls:
                print(f"    [*] Duplicate resolved URL ({real_url}), skipping to avoid duplicate processing.")
                continue
            processed_real_urls.add(real_url)
            
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
            is_full_text, fail_reason, stats = verify_full_text_integrity(
                raw_pdf_path,
                original_title=title,
                min_paragraphs=1,
                min_words=80
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
                
            print(f"    ✅ Verified Strategy A PDF: {file_size // 1024} KB | Pages: {num_pages} | Valid Words: {stats.get('valid_words_count', word_count)}")
            
            verified_items.append({
                "tier": tier,
                "strategy": "A",
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
        
    manifest_path = os.path.join(target_dir, "manifest_strategy_a_raw.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "run_id": f"strategy_a_{target_date}",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "strategy": "A",
            "total_captured": len(verified_items),
            "items": verified_items
        }, f, indent=2, ensure_ascii=False)
        
    print(f"\n🎉 Strategy A finished! Captured {len(verified_items)} items. Manifest: {manifest_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Strategy A Capturer (Direct Web / Native Capture for 17 Official/Public Sources)")
    parser.add_argument("--date", type=str, default=time.strftime("%Y-%m-%d"), help="Target Date YYYY-MM-DD")
    parser.add_argument("--dir", type=str, default=None, help="Target storage dir")
    parser.add_argument("--site", type=str, default=None, help="Specific site filter name")
    parser.add_argument("--ignore-history", action="store_true", help="Ignore deduplication history for isolated testing")
    args = parser.parse_args()
    
    try:
        from config_loader import get_target_dir
        target_dir = get_target_dir(args.date, cli_dir=args.dir)
    except Exception:
        target_dir = args.dir if args.dir else os.path.expanduser(f"~/Documents/Obsidian Vault/工作/新闻/{args.date} 新闻")
    run_strategy_a(args.date, target_dir, site_filter=args.site, ignore_history=args.ignore_history)
