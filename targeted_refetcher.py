import config_loader
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Targeted Article Refetcher & Cross-Search Engine (靶向文章重搜与多源补全引擎 v4.0.0)
业务场景：
当用户在人工审核 Wave 1 或存证结果时，若发现某篇文章存在付费墙拦截、
内容残缺或希望替换为更高质量的公开媒体源时，本脚本提供针对性的精准重搜与下载服务：
1. 接收用户输入的文章标题或核心关键词；
2. 全网多引擎（Google News / DuckDuckGo）发散检索公开无墙的权威替代源；
3. 使用 Playwright 自动渲染并打印为高质量 PDF；
4. 调用 full_text_verifier 执行魔数与全文完整度审计；
5. 生成 manifest_strategy_refetch_raw.json，无缝供 Wave 4 (manifest_merger) 合并归档。
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

def clean_filename(text):
    return "".join([c for c in text if c.isalnum() or c in (" ", "-", "_")]).strip()[:50]

def is_strict_date_in_text(text, target_date_str):
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    prev_dt = target_dt - timedelta(days=1)
    
    target_d_str = target_dt.strftime("%-d") if sys.platform != "win32" else str(target_dt.day)
    prev_d_str = prev_dt.strftime("%-d") if sys.platform != "win32" else str(prev_dt.day)
    
    patterns = [
        target_date_str,
        prev_dt.strftime("%Y-%m-%d"),
        target_dt.strftime("%d/%m/%Y"),
        prev_dt.strftime("%d/%m/%Y"),
        target_dt.strftime("%m/%d/%Y"),
        prev_dt.strftime("%m/%d/%Y"),
        target_dt.strftime("%b %d, %Y"),
        target_dt.strftime("%B %d, %Y"),
        prev_dt.strftime("%b %d, %Y"),
        prev_dt.strftime("%B %d, %Y"),
        f"{target_dt.strftime('%b')} {target_d_str}, {target_dt.year}",
        f"{prev_dt.strftime('%b')} {prev_d_str}, {prev_dt.year}",
        f"{target_dt.strftime('%B')} {target_d_str}, {target_dt.year}",
        f"{prev_dt.strftime('%B')} {prev_d_str}, {prev_dt.year}",
        target_dt.strftime("%d %b %Y"),
        prev_dt.strftime("%d %b %Y"),
        f"{target_d_str} {target_dt.strftime('%b')} {target_dt.year}",
        f"{prev_d_str} {prev_dt.strftime('%b')} {prev_dt.year}",
        "hours ago",
        "hour ago",
        "mins ago",
        "minutes ago",
        "yesterday",
        "today"
    ]
    text_lower = text.lower()
    for p in patterns:
        if p.lower() in text_lower:
            return True
    return False

def search_candidate_sources(query, max_results=5):
    """通过 Google News RSS 检索替代公开源"""
    encoded_query = urllib_parse_quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    
    candidates = []
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:max_results]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            source_name = entry.get("source", {}).get("title", "全网检索")
            
            # 过滤掉已知的强付费墙源
            if any(bad in source_name.lower() for bad in ["ft.com", "financial times", "wsj.com"]):
                continue
                
            candidates.append({
                "title": title,
                "link": link,
                "source": source_name
            })
    except Exception as e:
        print(f"[!] 检索候选源时出错: {e}")
        
    return candidates

def urllib_parse_quote(text):
    import urllib.parse
    return urllib.parse.quote(text)

def fetch_and_save_pdf(candidate, target_dir, target_date, category="二、市场动态"):
    title = candidate["title"]
    source_name = candidate["source"]
    link = candidate["link"]
    
    # 尝试解析 Google News 重定向
    resolved_url = link
    try:
        import googlenewsdecoder
        res = googlenewsdecoder.new_decod_response(link, interval=1)
        if res.get("status") and res.get("decoded_url"):
            resolved_url = res.get("decoded_url")
    except Exception:
        pass

    pdf_filename = f"全网检索（{clean_filename(source_name)}）-{clean_filename(title)}.pdf"
    pdf_path = os.path.join(target_dir, pdf_filename)
    
    print(f"[*] 正在通过无头浏览器抓取并渲染 PDF: {resolved_url}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
        )
        page = context.new_page()
        try:
            page.goto(resolved_url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)
            
            # 尝试关闭常见弹窗与遮罩
            try:
                page.evaluate("""() => {
                    const popups = document.querySelectorAll('.modal, .popup, .overlay, #cookie-banner, .banner, .paywall-prompt');
                    popups.forEach(el => el.remove());
                }""")
            except Exception:
                pass
                
            page.emulate_media(media="screen")
            page.pdf(
                path=pdf_path,
                format="A4",
                print_background=True,
                margin={"top": "15mm", "bottom": "15mm", "left": "15mm", "right": "15mm"}
            )
        except Exception as e:
            print(f"[!] 网页渲染 PDF 失败: {e}")
            browser.close()
            return None
        finally:
            browser.close()
            
    # 全文完整度与魔数审计
    valid, audit_msg, stats = verify_full_text_integrity(pdf_path, original_title=title, min_words=100)
    if not valid:
        print(f"[-] 审计未通过: {audit_msg}，移除残缺文件。")
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        return None
        
    print(f"✅ 靶向换源成功落盘: {pdf_path}")
    
    # 构造 manifest 项
    item = {
        "id": 999,
        "category": category,
        "site": f"全网检索（{source_name}）",
        "original_title": title,
        "publish_date": target_date,
        "source_url": resolved_url,
        "pdf_filename": pdf_filename,
        "md5": hashlib.md5(open(pdf_path, "rb").read()).hexdigest(),
        "fetch_strategy": "targeted_refetch_cross_search"
    }
    return item

def main():
    parser = argparse.ArgumentParser(description="靶向文章重搜与多源补全工具")
    parser.add_argument("--query", type=str, required=True, help="需要换源重搜的文章标题或关键词")
    parser.add_argument("--date", type=str, default=time.strftime("%Y-%m-%d"), help="目标日期 YYYY-MM-DD")
    parser.add_argument("--dir", type=str, default=None, help="目标存证目录")
    parser.add_argument("--category", type=str, default="二、市场动态", help="所属业务板块")
    args = parser.parse_args()
    
    target_dir = config_loader.get_target_dir(args.date, args.dir)
    os.makedirs(target_dir, exist_ok=True)
    
    print(f"🔍 启动靶向重搜换源: '{args.query}' (日期: {args.date})")
    candidates = search_candidate_sources(args.query)
    if not candidates:
        print(f"[!] 未检索到可用的公开替代候选源。")
        sys.exit(1)
        
    print(f"[*] 发现 {len(candidates)} 个潜在公开候选源，开始尝试逐一抓取...")
    
    saved_items = []
    for cand in candidates:
        print(f"\n--- 尝试源: {cand['source']} | 标题: {cand['title'][:40]}... ---")
        item = fetch_and_save_pdf(cand, target_dir, args.date, category=args.category)
        if item:
            saved_items.append(item)
            break  # 成功换源一篇即止
            
    if not saved_items:
        print(f"[❌] 所有候选源均未能通过全文完整度审计。")
        sys.exit(1)
        
    # 保存至专属 raw manifest
    manifest_refetch_path = os.path.join(target_dir, "manifest_strategy_refetch_raw.json")
    existing_items = []
    if os.path.exists(manifest_refetch_path):
        try:
            with open(manifest_refetch_path, "r", encoding="utf-8") as f:
                existing_items = json.load(f).get("items", [])
        except Exception:
            pass
            
    existing_items.extend(saved_items)
    with open(manifest_refetch_path, "w", encoding="utf-8") as f:
        json.dump({"items": existing_items}, f, ensure_ascii=False, indent=2)
        
    print(f"\n🎉 靶向重搜完成！已写入: {manifest_refetch_path}")
    print(f"💡 提示：您可以随时执行 python3 manifest_merger.py 重新触发汇总排序与重命名。")

if __name__ == "__main__":
    main()
