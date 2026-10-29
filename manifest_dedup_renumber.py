#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wave 4.5: 存证去重与全局重编号 (manifest_dedup_renumber.py)

背景：Wave 4 的 manifest_merger 只做了跨波次合并与编号分配，未做跨信源语义去重。
当同一篇文章被多个信源（如 Mondo Visione 的 news 与 exchange 两个 feed）分别捕获时，
会生成两份内容重复、sha256 不同的 PDF，并各自占用一个编号，导致内参出现重复条目。

本脚本在 Wave 4 之后、Wave 5 出报之前执行：
  1. 按「归一化标题」识别重复组，每组保留编号最小者（证据链最完整者）；
  2. 冗余件**移入 _duplicates/ 子目录**（不删除，保留原始存证）；
  3. 保留件按三大板块顺序重新编号 [1]~[N]，编号与物理文件名前缀严格一致且绝对连续；
  4. 回写 download_manifest.json。

用法：
  python3 manifest_dedup_renumber.py --dir "<目标存证目录>"
"""

import os
import re
import json
import shutil
import argparse
import collections

CATEGORY_ORDER = ["一、交易所动态", "二、市场动态", "三、监管动态"]


def normalize_title(title: str) -> str:
    """归一化标题：小写化、压缩空白、剥离标点，用于判定是否同一篇文章。"""
    t = title.lower().strip()
    t = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def strip_prefix(filename: str) -> str:
    """去掉文件名开头的 [n] 编号前缀。"""
    return re.sub(r"^\[\d+\]\s*", "", filename)


def main():
    ap = argparse.ArgumentParser(description="存证去重与全局重编号")
    ap.add_argument("--dir", required=True, help="目标存证目录")
    args = ap.parse_args()

    target_dir = os.path.abspath(args.dir)
    manifest_path = os.path.join(target_dir, "download_manifest.json")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    items = manifest["items"]
    total_before = len(items)

    # ---- 1. 分组识别重复 ------------------------------------------------------
    groups = collections.defaultdict(list)
    for x in items:
        groups[normalize_title(x["original_title"])].append(x)

    retained, dup_items = [], []
    dup_groups = []
    for key, group in groups.items():
        group.sort(key=lambda z: z["id"])
        retained.append(group[0])
        if len(group) > 1:
            dup_groups.append([g["id"] for g in group])
            dup_items.extend(group[1:])

    # ---- 2. 排序：先按板块顺序，板块内按原编号 --------------------------------
    def sort_key(x):
        cat = CATEGORY_ORDER.index(x["category"]) if x["category"] in CATEGORY_ORDER else 99
        return (cat, x["id"])

    retained.sort(key=sort_key)

    # ---- 3. 先归档冗余件，再重编号保留件 -------------------------------------
    # 顺序至关重要：剥离编号前缀后，重复件与保留件的基础文件名可能完全相同。
    # 若先重命名保留件，新文件名会与尚未移走的重复件撞名并被静默覆盖。
    dup_dir = os.path.join(target_dir, "_duplicates")
    os.makedirs(dup_dir, exist_ok=True)

    for x in dup_items:
        src = os.path.join(target_dir, x["local_filename"])
        if not os.path.exists(src):
            continue
        dst = os.path.join(dup_dir, strip_prefix(x["local_filename"]))
        n = 1
        base, ext = os.path.splitext(dst)
        while os.path.exists(dst):
            dst = f"{base} ({n}){ext}"
            n += 1
        shutil.move(src, dst)

    # ---- 4. 两阶段重命名，避免编号碰撞 ---------------------------------------
    # 阶段 A：保留件先改为临时名
    tmp_map = {}
    for x in retained:
        old = os.path.join(target_dir, x["local_filename"])
        tmp_name = f"__renumber_tmp_{x['id']}__{strip_prefix(x['local_filename'])}"
        tmp_path = os.path.join(target_dir, tmp_name)
        if os.path.exists(old):
            os.rename(old, tmp_path)
            tmp_map[x["id"]] = tmp_path
        else:
            tmp_map[x["id"]] = None

    # 阶段 B：改为最终 [新编号] 名称
    for new_id, x in enumerate(retained, start=1):
        tmp_path = tmp_map[x["id"]]
        if tmp_path is None:
            continue
        new_name = f"[{new_id}] {strip_prefix(x['local_filename'])}"
        final_path = os.path.join(target_dir, new_name)
        os.rename(tmp_path, final_path)
        x["id"] = new_id
        x["local_filename"] = new_name

    moved = len(dup_items)

    # ---- 5. 回写 manifest ----------------------------------------------------
    manifest["items"] = retained
    manifest["total_captured"] = len(retained)
    manifest["dedup"] = {
        "applied": True,
        "total_before": total_before,
        "total_after": len(retained),
        "duplicates_removed": moved,
        "duplicate_groups": dup_groups,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # ---- 6. 汇报 -------------------------------------------------------------
    print(f"[*] 去重前: {total_before} 篇 | 去重后: {len(retained)} 篇 | 移入 _duplicates/: {moved} 篇")
    for g in dup_groups:
        print(f"    重复组 {g} -> 保留 [{g[0]}]")
    dist = collections.Counter(x["category"] for x in retained)
    print("[*] 板块分布:")
    for c in CATEGORY_ORDER:
        print(f"    {c}: {dist.get(c, 0)} 篇")
    print(f"[*] 物理编号已重排为 [1] ~ [{len(retained)}]，与文件名前缀严格一致。")


if __name__ == "__main__":
    main()
