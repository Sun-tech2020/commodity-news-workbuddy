#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内参日报质量门禁 (report_quality_checker.py)

在 Wave 5 出报完成后、交付前执行，对照 WORKBUDDY_INSTRUCTIONS.md 的四大质量红线做机器校验：
  1. 三大板块严格归类（板块齐全且顺序正确）
  2. 编号全局绝对连续（[1]~[N]，与物理 PDF 文件名前缀一致，不跳号不断号）
  3. 标题字符红线（严格 15 ~ 35 字符）
  4. 正文字数红线（严格 150 ~ 220 字，按 中文字符数 + 英文单词数 计）

用法：
  python3 report_quality_checker.py --dir "<目标存证目录>"
  python3 report_quality_checker.py --dir "<目录>" --report "2026-10-29 国际大宗商品与衍生品市场日报.md"
"""

import os
import re
import sys
import json
import argparse

TITLE_MIN, TITLE_MAX = 15, 35
BODY_MIN, BODY_MAX = 150, 220
CATEGORIES = ["一、交易所动态", "二、市场动态", "三、监管动态"]


def count_units(s: str) -> int:
    """字数计算标准：中文字符数 + 英文单词数"""
    return len(re.findall(r"[\u4e00-\u9fff]", s)) + len(re.findall(r"[A-Za-z]+", s))


# 来源引用行：> **来源**：[{site}]({source_url}) | **时间**：{publish_date}
SOURCE_LINE_RE = re.compile(
    r"^>\s*\*\*来源\*\*\s*[：:]\s*\[(.+?)\]\((.+?)\)\s*\|\s*\*\*时间\*\*\s*[：:]\s*(\S*)\s*$"
)


def parse_report(path: str):
    """
    解析日报 Markdown，返回条目列表。

    每个条目含 id / section / title / body，以及来源行的 site / url / date。
    来源行位于标题正下方、正文之前，解析时需跳过它，否则正文会被截断。
    """
    lines = open(path, encoding="utf-8").read().split("\n")
    entries, cur, section = [], None, None
    for ln in lines:
        m_sec = re.match(r"^##\s+(.+)$", ln)
        if m_sec:
            section = m_sec.group(1).strip()
        m = re.match(r"^### \[(\d+)\] (.+)$", ln)
        if m:
            if cur:
                entries.append(cur)
            cur = {"id": int(m.group(1)), "section": section, "title": m.group(2),
                   "body": "", "site": None, "url": None, "date": None}
            continue
        if cur is None:
            continue
        if ln.startswith("## ") or ln.startswith("---"):
            entries.append(cur)
            cur = None
            continue
        msrc = SOURCE_LINE_RE.match(ln)
        if msrc and cur["site"] is None and not cur["body"]:
            cur["site"], cur["url"], cur["date"] = msrc.group(1), msrc.group(2), msrc.group(3)
            continue
        if ln.startswith("> "):
            entries.append(cur)
            cur = None
            continue
        if ln.strip():
            cur["body"] += ln
    if cur:
        entries.append(cur)
    return entries


def main():
    ap = argparse.ArgumentParser(description="内参日报四大质量红线校验")
    ap.add_argument("--dir", required=True, help="目标存证目录")
    ap.add_argument("--report", default=None, help="日报文件名（默认按目录日期推断）")
    args = ap.parse_args()

    target = os.path.abspath(args.dir)
    report = args.report
    if report is None:
        cands = [f for f in os.listdir(target) if f.endswith("国际大宗商品与衍生品市场日报.md")]
        if not cands:
            print("[错误] 未找到日报文件，请用 --report 指定。")
            sys.exit(1)
        report = sorted(cands)[0]
    rp = os.path.join(target, report)

    entries = parse_report(rp)
    errors, warnings = [], []

    # 红线 1：板块
    secs = []
    for e in entries:
        if e["section"] not in secs:
            secs.append(e["section"])
    for c in CATEGORIES:
        if c not in secs:
            errors.append(f"缺失板块：{c}")
    if secs != [c for c in CATEGORIES if c in secs]:
        errors.append(f"板块顺序异常：{secs}")

    # 红线 2：编号连续
    ids = [e["id"] for e in entries]
    if ids != list(range(1, len(ids) + 1)):
        errors.append(f"编号不连续：{ids}")

    # 编号与物理文件前缀一致 + 来源引用行 1:1 比对
    manifest_path = os.path.join(target, "download_manifest.json")
    src_ok, src_missing = 0, []
    if os.path.exists(manifest_path):
        m = json.load(open(manifest_path, encoding="utf-8"))
        mitems = {x["id"]: x for x in m["items"]}
        file_ids = sorted(mitems)
        if file_ids != ids:
            errors.append(f"日报编号与存证清单编号不一致：日报 {len(ids)} 条 / 清单 {len(file_ids)} 条")
        for x in m["items"]:
            if not x["local_filename"].startswith(f"[{x['id']}] "):
                errors.append(f"PDF 文件名前缀与编号不符：{x['local_filename']}")
            if not os.path.exists(os.path.join(target, x["local_filename"])):
                errors.append(f"物理存证缺失：[{x['id']}] {x['local_filename']}")
        # 来源行：缺漏、site/url/date 与清单不符均判为错误
        for e in entries:
            it = mitems.get(e["id"])
            if it is None:
                continue
            if e["site"] is None:
                src_missing.append(e["id"])
                errors.append(f"[{e['id']}] 缺少来源引用行")
                continue
            mismatched = False
            for field, key, label in (("site", "site", "来源机构"),
                                      ("url", "source_url", "原文链接"),
                                      ("date", "publish_date", "发布时间")):
                if e[field] != it.get(key):
                    errors.append(f"[{e['id']}] {label}与清单不一致："
                                  f"日报={e[field]!r} / 清单={it.get(key)!r}")
                    mismatched = True
            if not mismatched:
                src_ok += 1
    else:
        warnings.append("未找到 download_manifest.json，跳过来源引用行校验")

    # 红线 3 / 4
    for e in entries:
        t, b = count_units(e["title"]), count_units(e["body"])
        if not (TITLE_MIN <= t <= TITLE_MAX):
            errors.append(f"[{e['id']}] 标题 {t} 字符，越界（须 {TITLE_MIN}~{TITLE_MAX}）：{e['title']}")
        if not (BODY_MIN <= b <= BODY_MAX):
            errors.append(f"[{e['id']}] 正文 {b} 字，越界（须 {BODY_MIN}~{BODY_MAX}）")
        if re.search(r"^\s*[-*+]\s+", e["body"], re.M):
            warnings.append(f"[{e['id']}] 正文疑似含分点罗列，应改为自然段落流")

    print(f"日报：{rp}")
    print(f"条目：{len(entries)} 篇")
    for c in CATEGORIES:
        print(f"    {c}: {sum(1 for e in entries if e['section'] == c)} 篇")
    print(f"标题字数区间：{min(count_units(e['title']) for e in entries)} ~ "
          f"{max(count_units(e['title']) for e in entries)}")
    print(f"正文字数区间：{min(count_units(e['body']) for e in entries)} ~ "
          f"{max(count_units(e['body']) for e in entries)}")
    print(f"来源引用行：{src_ok}/{len(entries)} 条与存证清单 1:1 一致"
          + (f"，缺失 {len(src_missing)} 条" if src_missing else ""))
    for w in warnings:
        print(f"[警告] {w}")
    if errors:
        print(f"\n❌ 质量门禁未通过，共 {len(errors)} 项：")
        for x in errors:
            print(f"    - {x}")
        sys.exit(1)
    print("\n✅ 四大质量红线全部通过。")


if __name__ == "__main__":
    main()
