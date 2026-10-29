#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提取存证 PDF 正文，供智能体阅读并编译内参日报（零幻视：一切以物理存证原文为准）。

输出 JSON：{ id, category, site, title, publish_date, source_url, local_filename, text }
用法： python3 extract_pdf_texts.py --dir "<目标存证目录>" --out /tmp/texts.json
"""

import os
import re
import json
import argparse
from pypdf import PdfReader


def clean(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-chars", type=int, default=6000, help="每篇保留的最大字符数")
    args = ap.parse_args()

    target_dir = os.path.abspath(args.dir)
    with open(os.path.join(target_dir, "download_manifest.json"), "r", encoding="utf-8") as f:
        manifest = json.load(f)

    results = []
    for x in manifest["items"]:
        path = os.path.join(target_dir, x["local_filename"])
        text = ""
        if os.path.exists(path):
            try:
                reader = PdfReader(path)
                text = "\n".join((p.extract_text() or "") for p in reader.pages)
            except Exception as e:
                text = f"[PDF 解析失败: {e}]"
        else:
            text = "[物理文件缺失]"
        results.append({
            "id": x["id"],
            "category": x["category"],
            "site": x["site"],
            "title": x["original_title"],
            "publish_date": x["publish_date"],
            "source_url": x["source_url"],
            "local_filename": x["local_filename"],
            "text": clean(text)[: args.max_chars],
        })

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    empty = [r["id"] for r in results if len(r["text"]) < 100]
    print(f"[*] 已抽取 {len(results)} 篇正文 -> {args.out}")
    print(f"[*] 正文过短(<100字符)的条目: {empty if empty else '无'}")


if __name__ == "__main__":
    main()
