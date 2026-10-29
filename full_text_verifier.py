#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Full-Text Integrity Verifier (全文完整度与付费墙深度核验引擎)
统一为所有抓取策略（A/B/C）与存证合并阶段（Merger）提供高精度的全文真伪核验：
1. 付费墙/会员锁阻断检测（Paywall / Subscription Lock Detection）
2. Cookie/GDPR Consent 弹窗遮罩污染检测（Consent Banner Pollution Detection）
3. 有效正文段落与有效词数深度审计（Valid Paragraph & Word Count Audit）
4. 物理文件与 Manifest 清单的自动清洗删除（Automated Physical Deletion & Pruning）
"""

import os
import sys
import re
import json
import pypdf
from typing import Tuple, Dict, Any, List

# 1. 国际主流媒体与财经专栏付费墙/会员阻断模式
PAYWALL_PATTERNS = [
    r"already a member\? sign in",
    r"exclusively available to .* (members|subscribers|prime)",
    r"subscribe to (discover|read|continue|unlock|access)",
    r"join .* (membership|prime|premium|plus)",
    r"this article is for subscribers only",
    r"to continue reading, please subscribe",
    r"you have reached your limit of free articles",
    r"sign in to read the full",
    r"start your free trial to continue",
    r"unlock full (story|article|analysis|report)",
    r"read the rest of this (story|article)",
    r"become a member to access",
    r"access to this article is restricted",
    r"this content is reserved for",
    r"subscribe now for unlimited access",
    r"create a free account to continue reading",
    r"log in or register to read the full article",
    r"for full access, please subscribe",
    r"upgrade to premium to read",
    r"full article is available to paying subscribers",
    r"this story is exclusive to subscribers",
    r"listen to this article in summarized format\s+listen\s+.*\s+already a member",
    r"your choices regarding cookies and identifiers"
]

# 2. 弹窗/Cookie 遮罩模式（如果重复出现说明有效正文被遮挡）
CONSENT_BANNER_PATTERNS = [
    r"this site asks for consent to use your data",
    r"personalised advertising and content",
    r"manage or withdraw consent in privacy",
    r"store and/or access information on a device",
    r"your personal data will be processed and information from your device",
    r"look for a link at the bottom of this page or in the site menu to manage or withdraw consent",
    r"we and our partners process personal data",
    r"accept all cookies",
    r"cookie preferences",
    r"your choices regarding cookies and identifiers",
    r"bloomberg required cookies",
    r"bloomberg advertising cookies"
]

# 3. 需排除的样板、导航、版权与社交分享文本
BOILERPLATE_SUBSTRINGS = [
    "terms of service", "privacy policy", "all rights reserved", "cookie settings",
    "download on the app store", "get it on google play", "manage options", "list of partners",
    "sign up for newsletter", "follow us on twitter", "follow us on linkedin",
    "share this article", "related topics", "recommended stories", "trending links",
    "feedback", "contact us", "site map", "advertisement", "copyright"
]

def extract_text_from_pdf(pdf_path: str) -> str:
    """从物理 PDF 文件中安全提取全部文本"""
    if not os.path.exists(pdf_path):
        return ""
    try:
        reader = pypdf.PdfReader(pdf_path)
        pages_text = []
        for p in reader.pages:
            t = p.extract_text()
            if t:
                pages_text.append(t)
        return "\n".join(pages_text)
    except Exception as e:
        return ""

def clean_and_extract_valid_paragraphs(raw_text: str, min_line_len: int = 30) -> List[str]:
    """清洗提取真实的有效正文段落（剔除短标题、广告、导航栏、样板字句，兼容监管公告列表与短段落）"""
    raw_lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    valid_paras = []
    
    for line in raw_lines:
        line_lower = line.lower()
        # 长度过滤：过短通常是菜单或图标标签，放宽至 30 字符以保留条目式政策要点
        if len(line) < min_line_len:
            continue
        # 排除样板字句
        if any(bp in line_lower for bp in BOILERPLATE_SUBSTRINGS):
            continue
        # 排除 Consent 弹窗
        if any(re.search(cp, line_lower) for cp in CONSENT_BANNER_PATTERNS):
            continue
        valid_paras.append(line)
        
    return valid_paras

def verify_full_text_integrity(
    target: Any,
    original_title: str = "",
    min_paragraphs: int = 2,
    min_words: int = 90
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    严格核验是否为真实全文。
    target: 可以是物理 PDF 文件路径 (str)，也可以是已提取的文本 (str)
    
    返回: (is_valid: bool, reason: str, stats: dict)
    """
    if os.path.exists(str(target)) and str(target).endswith(".pdf"):
        raw_text = extract_text_from_pdf(str(target))
        file_path = str(target)
    else:
        raw_text = str(target)
        file_path = None
        
    if not raw_text or len(raw_text.strip()) == 0:
        return False, "PDF/Text is completely empty (0 characters)", {"total_chars": 0, "total_words": 0}
        
    raw_text_lower = raw_text.lower()
    
    # 1. 付费墙特征词深度检测
    for pat in PAYWALL_PATTERNS:
        m = re.search(pat, raw_text_lower)
        if m:
            # 如果在前半段出现，判定为付费墙拦截
            if m.start() < 2000 or m.start() < len(raw_text_lower) * 0.6:
                return False, f"Paywall / Subscription barrier detected: '{pat}' at char {m.start()}", {
                    "matched_pattern": pat,
                    "pos": m.start()
                }
                
    # 2. 重复 Consent / Cookie 遮罩检测
    for cp in CONSENT_BANNER_PATTERNS:
        matches = re.findall(cp, raw_text_lower)
        if len(matches) >= 2:
            return False, f"Repeated Consent/Cookie banner overlay detected ({len(matches)} times: '{cp}')", {
                "consent_count": len(matches)
            }
            
    # 3. 真实有效正文段落与词数深度审计
    valid_paras = clean_and_extract_valid_paragraphs(raw_text, min_line_len=30)
    total_valid_words = sum(len(p.split()) for p in valid_paras)
    
    stats = {
        "valid_paragraphs_count": len(valid_paras),
        "valid_words_count": total_valid_words,
        "total_extracted_words": len(raw_text.split()),
        "file_path": file_path
    }
    
    # 如果总有效词数充沛 (>=120 词)，即使段落格式紧凑也视为合规
    if len(valid_paras) < min_paragraphs and total_valid_words < 120:
        return False, f"Insufficient valid content paragraphs: found {len(valid_paras)}, required >= {min_paragraphs}", stats
        
    if total_valid_words < min_words:
        return False, f"Insufficient valid body word count: found {total_valid_words} words, required >= {min_words}", stats
        
    # 4. 标题核心实体关联度审计（防 404 / 纯空白页 / 抓错文章）
    #    旧实现仅要求「命中 1 个关键词」即放行，导致聚合站(如 Stock Titan 的 SEC 申报页)
    #    只要出现机构名(如 CME)就能通过，正文实为另一篇无关文章。
    #    改为比例判定：需命中至少 40% 的核心实体词，且不少于 2 个（关键词少于 3 个时放宽至 1 个）。
    if original_title:
        STOPWORDS = ["with", "that", "this", "from", "over", "into", "plans", "adds", "eyes",
                     "been", "have", "will", "would", "could", "their", "there", "about", "after"]
        clean_kw = [w.lower() for w in re.findall(r"\b[A-Za-z0-9]{4,}\b", original_title)
                    if w.lower() not in STOPWORDS]
        if clean_kw:
            matched_kw = [k for k in clean_kw if k in raw_text_lower]
            if len(clean_kw) >= 3:
                required = max(2, -(-len(clean_kw) * 40 // 100))  # ceil(40%)
            else:
                required = 1
            stats["title_keywords"] = clean_kw
            stats["title_matched"] = matched_kw
            if len(matched_kw) < required:
                return False, (
                    f"Document text insufficiently relevant to original title "
                    f"({len(matched_kw)}/{len(clean_kw)} keywords matched, required >= {required}; "
                    f"matched={matched_kw})"
                ), stats

    return True, f"Verified Full Text ({len(valid_paras)} paragraphs, {total_valid_words} valid words)", stats

def audit_and_cleanup_directory(target_dir: str, delete_invalid: bool = True) -> Dict[str, Any]:
    """
    扫描并清洗指定目录下的所有 PDF 文件：
    1. 逐个核验全文完整度；
    2. 若不是全文，直接从磁盘物理删除；
    3. 自动同步更新所有 manifest JSON 清单文件。
    """
    print(f"\n[*] Starting Full-Text Integrity Audit & Cleanup on: {target_dir}")
    if not os.path.exists(target_dir):
        print(f"[!] Directory not found: {target_dir}")
        return {"audited": 0, "passed": 0, "deleted": 0}
        
    pdf_files = [f for f in os.listdir(target_dir) if f.endswith(".pdf")]
    deleted_files = set()
    passed_files = []
    
    for pdf_name in sorted(pdf_files):
        pdf_path = os.path.join(target_dir, pdf_name)
        is_full, reason, stats = verify_full_text_integrity(pdf_path)
        
        if not is_full:
            print(f"  ❌ REJECTED (Non-Full-Text): {pdf_name}")
            print(f"     Reason: {reason}")
            if delete_invalid:
                try:
                    os.remove(pdf_path)
                    print(f"     🗑️  Physically deleted: {pdf_name}")
                    deleted_files.add(pdf_name)
                except Exception as e:
                    print(f"     [!] Failed to delete file: {e}")
        else:
            print(f"  ✅ PASSED: {pdf_name} ({stats['valid_words_count']} words, {stats['valid_paragraphs_count']} paras)")
            passed_files.append(pdf_name)
            
    # 更新所有 manifest json 文件
    manifest_files = [f for f in os.listdir(target_dir) if f.startswith("manifest_") or f == "download_manifest.json"]
    for m_file in manifest_files:
        m_path = os.path.join(target_dir, m_file)
        try:
            with open(m_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("items", [])
            new_items = []
            for it in items:
                loc = it.get("local_filename", "")
                # 检查是否是被删除的文件
                if loc in deleted_files or any(loc.endswith(df) for df in deleted_files):
                    continue
                # 检查物理文件是否存在
                if loc and not os.path.exists(os.path.join(target_dir, loc)):
                    continue
                new_items.append(it)
                
            data["items"] = new_items
            data["total_captured"] = len(new_items)
            with open(m_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"[*] Updated manifest: {m_file} (Retained {len(new_items)} items)")
        except Exception as e:
            print(f"[!] Error updating manifest {m_file}: {e}")
            
    summary = {
        "audited": len(pdf_files),
        "passed": len(passed_files),
        "deleted": len(deleted_files),
        "deleted_list": list(deleted_files)
    }
    print(f"\n🎉 Audit completed: {len(pdf_files)} checked, {len(passed_files)} passed, {len(deleted_files)} deleted.")
    return summary

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Full-Text Integrity Verifier & Cleaner")
    parser.add_argument("--dir", type=str, required=True, help="Directory to audit and clean")
    parser.add_argument("--no-delete", action="store_true", help="Only audit without deleting")
    args = parser.parse_args()
    
    audit_and_cleanup_directory(args.dir, delete_invalid=not args.no_delete)
