import config_loader
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Strategy A Capturer: 策略 A 抓取标题 + 全网二次检索公开全文引擎 (Title Scraping & Cross-Search)
负责执行 News_Sources_Registry.md 中标注为【策略 A】的站点：
- P0: 英国期货期权世界 (FOW Insights, https://www.fow.com/insights)（全量抓取，无篇数上限）

技术工作流：
1. 访问 FOW Insights 列表页，提取当日文章卡片（标题、发布日期、摘要）；
2. 严格核验发布日期属于 T 或 T-1，并命中目标主题/品种；
3. 将标题核心词传入 Google News RSS / 全网检索公开来源全文（如 Investing.com, FIA, PR Newswire 等）；
4. 联合溯源标注为 "英国期货期权世界（FOW Insights / <公开源>）" 并原生打印 PDF；
5. 严格审计魔数 b'%PDF'、字数 >= 150 词与物理日期；
6. 产出 manifest_strategy_a_raw.json。
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
            rf"\b{dt.strftime('%B')}\s+{d_str},?\s+{dt.year}\b",
            rf"\b{dt.strftime('%b')}\.?\s+{d_str},?\s+{dt.year}\b",
            rf"\b{d_str}(?:st|nd|rd|th)?\s+{dt.strftime('%B')},?\s+{dt.year}\b",
            rf"\b{d_str}(?:st|nd|rd|th)?\s+{dt.strftime('%b')}\.?,?\s+{dt.year}\b",
        ])
    
    for pat in patterns:
        if re.search(pat, norm_text, re.IGNORECASE):
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
    print("[*] Strategy A: Accessing FOW Insights (Multi-page traversal)...")
    articles = []
    
    window = get_target_date_window(target_date)
    valid_dates = window["valid_dates_set"]
    google_when = window["google_when"]
    
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
                # 持续确保弹窗遮罩不拦截
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
                        
                    comb = (title_text + " " + summary_text).lower()
                    if not (any(k in comb for k in EXEMPT_KEYWORDS) or any(c in comb for c in TARGET_COMMODITIES)):
                        continue
                        
                    full_fow_url = "https://www.fow.com" + href
                    seen_titles.add(title_text)
                    articles.append({
                        "title": title_text,
                        "publish_date": pub_date,
                        "summary": summary_text,
                        "fow_url": full_fow_url
                    })
                    print(f"    [+] FOW Qualified ({pub_date}): {title_text}")
                    
                # 若已抓到早于截止日期的文章且当前页无合法日期，说明已完全回溯到目标区间之前
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
        
    # 2. Google News Syndication 辅助索引（补充捕获）
    try:
        # 支持按绝对日期或相对日期进行检索
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
                comb = (clean_t + " " + entry.get("summary", "")).lower()
                if any(k in comb for k in EXEMPT_KEYWORDS) or any(c in comb for c in TARGET_COMMODITIES):
                    seen_titles.add(clean_t)
                    articles.append({
                        "title": clean_t,
                        "publish_date": pub_date,
                        "summary": entry.get("summary", ""),
                        "fow_url": entry.get("link", "")
                    })
    except Exception as e:
        print(f"[!] Google News FOW indexing error: {e}")
        
    print(f"[*] Found {len(articles)} total valid articles from FOW Insights across all pages.")
    return articles


from full_text_verifier import verify_full_text_integrity


def cross_search_public_articles(title, target_date, seen_urls, max_candidates=4):
    clean_kw = re.sub(r"[^\w\s]", "", title)
    words = clean_kw.split()
    query_words = words[:6] if len(words) >= 6 else words
    query = " ".join(query_words)
    
    window = get_target_date_window(target_date)
    d_min = window["valid_dates"][-1]
    dt_max = datetime.strptime(window["valid_dates"][0], "%Y-%m-%d") + timedelta(days=1)
    d_max = dt_max.strftime("%Y-%m-%d")
    
    # 策略 1: 带日期窗口检索
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
            f = feedparser.parse(rss_url)
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
            pass
            
    return candidates

def resolve_real_url(page, raw_url):
    """解析真实 URL，通过 googlenewsdecoder 毫秒级直解原始媒体源网址"""
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

def print_to_pdf_native(page, url, target_path):
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
            '.tp-backdrop', '.tp-modal', '.consent-banner'
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

def run_strategy_a(target_date, target_dir, ignore_history=False):
    os.makedirs(target_dir, exist_ok=True)
    seen_urls = load_dedup_history(ignore_history=ignore_history)
    print(f"[*] Strategy A (FOW Insights Title Scraping & Cross-Search) on Date: {target_date} (Ignore History: {ignore_history})...")
    
    fow_articles = fetch_fow_insights_articles(target_date)
    verified_items = []
    
    if not fow_articles:
        print("[*] No target articles found on FOW Insights today. Proceeding with empty result.")
    else:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            for idx, art in enumerate(fow_articles, 1):
                fow_title = art["title"]
                fow_date = art["publish_date"]
                print(f"\n[{idx}/{len(fow_articles)}] Cross-searching FOW article: {fow_title}...")
                
                cross_candidates = cross_search_public_articles(fow_title, target_date, seen_urls)
                if not cross_candidates:
                    print("    [!] No public cross-search match found (Exclusive paywall story). Skipping.")
                    continue
                    
                captured_for_article = False
                clean_t = clean_filename(fow_title)
                raw_pdf_name = f"FOW_{idx:02d}_{clean_t}.pdf"
                raw_pdf_path = os.path.join(target_dir, raw_pdf_name)
                
                for c_idx, cand in enumerate(cross_candidates, 1):
                    pub_url = cand["public_url"]
                    pub_source = cand["public_source"]
                    joint_site_name = f"英国期货期权世界（FOW Insights / {pub_source}）"
                    
                    real_pub_url = resolve_real_url(page, pub_url)
                    print(f"    Candidate {c_idx}/{len(cross_candidates)}: {pub_source} -> {real_pub_url[:60]}...")
                    
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
                    except Exception as e:
                        os.remove(raw_pdf_path)
                        continue
                        
                    # 严格执行全文完整度与付费墙核验（包含段落、词数、弹窗与付费阻断）
                    is_full_text, fail_reason, stats = verify_full_text_integrity(raw_pdf_path, original_title=fow_title)
                    if not is_full_text:
                        print(f"    [!] Candidate rejected: {fail_reason}. Trying next candidate...")
                        os.remove(raw_pdf_path)
                        continue
                        
                    has_valid_date = is_strict_date_in_text(extracted_text, target_date)
                    if not has_valid_date and fow_date != target_date:
                        print(f"    [!] Candidate rejected: Missing strict date ({target_date}) in text!")
                        os.remove(raw_pdf_path)
                        continue
                        
                    print(f"    ✅ Verified Strategy A Full-Text PDF: {file_size // 1024} KB | Pages: {num_pages} | Valid Words: {stats.get('valid_words_count', word_count)}")
                    
                    verified_items.append({
                        "tier": "P1",
                        "strategy": "A",
                        "site": joint_site_name,
                        "category": "",
                        "original_title": fow_title,
                        "publish_date": fow_date,
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
                    print(f"    [!] Dropped: All public candidates failed full-text validation for: {fow_title[:35]}")
            
    manifest_path = os.path.join(target_dir, "manifest_strategy_a_raw.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "run_id": f"strategy_a_p0_{target_date}",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "strategy": "A",
            "total_captured": len(verified_items),
            "items": verified_items
        }, f, indent=2, ensure_ascii=False)
        
    print(f"\n🎉 Strategy A finished! Captured {len(verified_items)} items. Manifest: {manifest_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Strategy A Capturer (FOW Insights Title Scraping & Cross Search)")
    parser.add_argument("--date", type=str, default=time.strftime("%Y-%m-%d"), help="Target Date YYYY-MM-DD")
    parser.add_argument("--dir", type=str, default=None, help="Target storage dir")
    parser.add_argument("--ignore-history", action="store_true", help="Ignore history for testing")
    args = parser.parse_args()
    
    target_dir = config_loader.get_target_dir(args.date, args.dir)
    run_strategy_a(args.date, target_dir, ignore_history=args.ignore_history)
