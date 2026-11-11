#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
采编前置网络体检 (preflight_net_check.py)

在运行 run_daily_pipeline.py 之前执行，10 秒内判断本机网络通道能否触达采编所需的境内外站点。
退出码 0 = 关键通道全部可用；退出码 1 = 存在致命故障（应停下来修网络，不要继续采集）。

用法：
  python3 preflight_net_check.py            # 常规体检
  python3 preflight_net_check.py -v         # 显示失败原因
"""

import sys
import time
import argparse
import urllib.error
import urllib.request

BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
PROJECT_UA = "CommodityNewsScraper/2.0 (commodity_news_agent@internal.com)"

# (名称, URL, UA 类型, 是否关键)
TARGETS = [
    ("Google News RSS（策略A 命脉）",
     "https://news.google.com/rss/search?q=CME+Group&hl=en-US&gl=US&ceid=US:en", "project", True),
    ("SEC 美国证监会", "https://www.sec.gov/newsroom/press-releases", "project", True),
    ("CFTC 美国商品期货交易委员会", "https://www.cftc.gov/", "project", True),
    ("ESMA 欧盟证券与市场管理局", "https://www.esma.europa.eu/", "project", True),
    ("Mondo Visione（策略B 主源）", "https://www.mondovisione.com/", "project", True),
    ("FOW 期货期权世界", "https://www.fow.com/", "project", True),
    ("JPX 日本交易所", "https://www.jpx.co.jp/english/", "project", False),
    ("SFC 香港证监会", "https://www.sfc.hk/en/", "project", False),
    ("CME 芝商所", "https://www.cmegroup.com/", "browser", False),
    ("Nasdaq 纳斯达克", "https://www.nasdaq.com/", "browser", False),
    ("LME 伦敦金属交易所", "https://www.lme.com/", "browser", False),
]

TIMEOUT = 12


def probe(url: str, ua: str):
    """返回 (状态码, 耗时秒, 错误描述)"""
    req = urllib.request.Request(url, headers={
        "User-Agent": BROWSER_UA if ua == "browser" else PROJECT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, time.time() - t0, ""
    except urllib.error.HTTPError as e:
        return e.code, time.time() - t0, f"HTTP {e.code}"
    except Exception as e:
        return 0, time.time() - t0, type(e).__name__


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true", help="显示失败原因")
    args = ap.parse_args()

    print("=" * 62)
    print("采编前置网络体检")
    print("=" * 62)

    critical_fail, soft_fail = [], []
    for name, url, ua, critical in TARGETS:
        code, cost, err = probe(url, ua)
        ok = 200 <= code < 400
        flag = "OK  " if ok else ("WARN" if not critical else "FAIL")
        print(f"  [{flag}] {name:<26} {code:>3}  {cost:5.2f}s"
              + (f"  {err}" if args.verbose and err else ""))
        if not ok:
            (critical_fail if critical else soft_fail).append(name)

    print("-" * 62)
    if critical_fail:
        print(f"致命故障 {len(critical_fail)} 项：{'、'.join(critical_fail)}")
        print("处置建议：")
        print("  1) 确认代理处于 TUN（虚拟网卡）模式，且【规则模式下 Proxy 策略组选中的节点可用】；")
        print("  2) 在代理客户端对各节点做一次延迟测试，剔除超时节点（常见于香港 IPLC 等旧节点）；")
        print("  3) 重新执行本体检，全 OK 后再跑采集。")
        return 1

    if soft_fail:
        print(f"提示：以下站点本次不可达（不阻断采集，条目会偏少）：{'、'.join(soft_fail)}")
        print("     此类站点多有反爬，脚本已用浏览器 UA 兜底；若长期失败可忽略或换节点重试。")
    print("网络通道正常，可以开始采集。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
