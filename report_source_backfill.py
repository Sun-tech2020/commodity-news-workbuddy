#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日报来源引用回填 (report_source_backfill.py)

按 WORKBUDDY_INSTRUCTIONS.md「单条新闻强制排版结构模板」，为日报中每条新闻
在标题下方注入来源引用行：

    ### [{编号}] {标题}
    > **来源**：[{site}]({source_url}) | **时间**：{publish_date}

    {正文}

site / source_url / publish_date 严格 1:1 读取自同目录 download_manifest.json
对应 id 的字段，不做任何改写、翻译或省略。

特性：
  - 幂等：已存在来源行时按清单覆盖刷新，重复执行不会产生第二行；
  - 安全：仅处理 `### [n] ` 标题行，其余内容（含页眉、板块标题、存证说明）原样保留；
  - 校验：清单缺失 id 或日报多余 id 均会报错并中止，不静默跳过。

用法：
  python3 report_source_backfill.py --dir "<目标存证目录>"
  python3 report_source_backfill.py --dir "<目录>" --report "<日报文件名>"
"""

import os
import re
import sys
import json
import argparse

HEADING_RE = re.compile(r"^### \[(\d+)\] (.+)$")
# 来源行既有的写法（用于幂等覆盖），兼容不同空格/全半角
SOURCE_RE = re.compile(r"^>\s*\*\*来源\*\*\s*[：:].*$")


def build_source_line(item: dict) -> str:
    site = item["site"]
    url = item["source_url"]
    date = item.get("publish_date") or ""
    return f"> **来源**：[{site}]({url}) | **时间**：{date}"


def main():
    ap = argparse.ArgumentParser(description="为内参日报逐条回填来源与时间引用行")
    ap.add_argument("--dir", required=True, help="目标存证目录")
    ap.add_argument("--report", default=None, help="日报文件名（默认按目录自动推断）")
    ap.add_argument("--dry-run", action="store_true", help="仅预览，不写盘")
    args = ap.parse_args()

    target = os.path.abspath(args.dir)
    manifest_path = os.path.join(target, "download_manifest.json")
    if not os.path.exists(manifest_path):
        print(f"[错误] 未找到存证清单：{manifest_path}")
        sys.exit(1)

    report = args.report
    if report is None:
        cands = [f for f in os.listdir(target) if f.endswith("国际大宗商品与衍生品市场日报.md")]
        if not cands:
            print("[错误] 未找到日报文件，请用 --report 指定。")
            sys.exit(1)
        report = sorted(cands)[0]
    rp = os.path.join(target, report)
    if not os.path.exists(rp):
        print(f"[错误] 日报不存在：{rp}")
        sys.exit(1)

    manifest = json.load(open(manifest_path, encoding="utf-8"))
    items = {x["id"]: x for x in manifest["items"]}

    lines = open(rp, encoding="utf-8").read().split("\n")
    out, cur_id = [], None
    filled, replaced, skipped = [], 0, []

    for ln in lines:
        m = HEADING_RE.match(ln)
        if m:
            cur_id = int(m.group(1))
            out.append(ln)
            item = items.get(cur_id)
            if item is None:
                print(f"[错误] 日报编号 [{cur_id}] 在存证清单中不存在，已中止。")
                sys.exit(1)
            # 幂等：若下一行已是来源行，则在后续循环中被替换掉
            out.append(build_source_line(item))
            filled.append(cur_id)
            continue
        if SOURCE_RE.match(ln):
            replaced += 1
            continue  # 丢弃旧来源行，保留刚写入的新行
        out.append(ln)

    missing = sorted(set(items) - set(filled))
    if missing:
        print(f"[错误] 存证清单中以下 id 在日报中无对应条目：{missing}")
        sys.exit(1)

    if args.dry_run:
        print(f"[预览] 将写入 {len(filled)} 条来源行，覆盖旧行 {replaced} 条（未写盘）")
        return

    open(rp, "w", encoding="utf-8").write("\n".join(out))
    print(f"日报：{rp}")
    print(f"回填来源行：{len(filled)} 条（覆盖旧行 {replaced} 条）")
    print(f"编号覆盖：[{min(filled)}] ~ [{max(filled)}]，与清单 {len(items)} 条一致")


if __name__ == "__main__":
    main()
