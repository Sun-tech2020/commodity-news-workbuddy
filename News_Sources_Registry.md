# 境外市场动态信息源注册与分工调度中心 (News Sources Registry)

> [!NOTE] 核心定位与多角色协同说明
> 本文档基于公司内部《境外市场动态信息分工》（1015版）与自动化采集流水线深度整合构建，作为**全天候人机协作与智能体定向爬取的唯一定义注册表**。
> 供 `Commodity_News_Capturer.skill` 自动化脚本每日动态读取，并支持业务人员按一 / 二 / 三类直接对智能体下发定向采集指令。
> 
> ### 1. 业务信息源分类体系说明 (一 / 二 / 三类)
> - **一类信息源（当月编译人员负责 · 核心主责库）**：共 25 个网站。由当月编译人员统领负责，涵盖 4 个人工协同巡检源与 21 个已完成自动化抓取策略（17 个策略 A、2 个策略 B、2 个策略 C）适配的核心资讯源与监管机构。**用户指令：`爬取一类网站新闻`**。
> - **二类信息源（协助成员 1 负责 · 外围协同库）**：共 23 个网站。由协作成员 1 负责每日浏览与查漏补缺，覆盖德国 BaFin、香港 SFC、新加坡 MAS 等境外主流监管机构及 TradingView 等专业分析平台。**用户指令：`爬取二类网站新闻`**。
> - **三类信息源（协助成员 2 负责 · 外围协同库）**：共 23 个网站。由协作成员 2 负责每日浏览与查漏补缺，覆盖 Euronext、Cboe、Eurex、JPX、MCX 等境外主要衍生品与现货交易所。**用户指令：`爬取三类网站新闻`**。
> 
> ### 2. 访问策略代号说明 (Access Strategies)
> - **`人工`：人工协同浏览与报送** —— 针对强反爬防火墙阻断（如 Akamai、Datadome 403）或严格订阅硬付费墙站点（金融时报、MarketScreener、商业标准报、NSE/NCDEX），由当月编译人员或团队成员人工登录浏览、发现线索后分享至工作群。
> - **`A`：直接解析与下载（全量采集）** —— 公开源直连、公开聚合源、官方新闻室与 RSS 列表直接解析并全量抓取（CFTC、ESMA、FCA、FIA、ICE、LME、CME、ISDA、DMIST、SEBI、雅虎财经、NewsNow、SEC、IOSCO、纳斯达克、NFA、印度经济时报，共 17 站）。
> - **`B`：抓取标题 + 全网二次搜索（全量采集）** —— 针对重点专业资讯源（英国期货期权世界 FOW Insights、Mondo Visione MV，共 2 站），抓取文章标题后在 Google / Bing / PR Newswire 搜索引擎进行全网二次检索并获取公开全文；若为独家无公开源则跳过。
> - **`C`：穿透通道下载（全量采集）** —— 针对头部商业媒体高防付费墙站点（彭博社、标普全球洞察，共 2 站），通过专有高防穿透下载引擎（BPC/专有无头浏览器）全量抓取。
> - **`-`：待接入 / 协同巡检** —— 当前尚未接入自动化采集脚本的外围协同站点，日常依托人工协同查漏补缺，后续按需扩展自动化脚本。
> 
> ### 3. 每日新闻生成与存证归档标注规范 (Output Naming Standards)
> 每日生成的新闻存证目录及 Markdown 内参日报必须严格在名称末尾通过中文全角括号标注所抓取的信息源类别，以便在 Obsidian 目录树中一目了然：
> - **抓取一类信息源**：`YYYY-MM-DD 新闻（一）` / `YYYY-MM-DD 国际大宗商品与衍生品市场日报（一）.md`
> - **抓取二类信息源**：`YYYY-MM-DD 新闻（二）` / `YYYY-MM-DD 国际大宗商品与衍生品市场日报（二）.md`
> - **抓取三类信息源**：`YYYY-MM-DD 新闻（三）` / `YYYY-MM-DD 国际大宗商品与衍生品市场日报（三）.md`
> - **抓取一类与二类组合**：`YYYY-MM-DD 新闻（一、二）` / `YYYY-MM-DD 国际大宗商品与衍生品市场日报（一、二）.md`
> - **抓取全部/所有信息源**：`YYYY-MM-DD 新闻（所有）` / `YYYY-MM-DD 国际大宗商品与衍生品市场日报（所有）.md`

---

## 一、一类信息源注册表（当月编译人员负责 · 核心主责库）

> [!TIP] 一类源排序说明
> 表格按照**【人工 → A → B → C】**优先级策略顺序组织。用户指令下达“爬取一类”时，系统将对所有已配置自动化访问策略（A / B / C）的 21 个站点执行全量并发抓取，并在汇报中提示 4 个人工巡检站点的协同线索。

| 序号  | 网站中文名称              | 目标网址 (URL)                                                                                                                  | 访问策略 |
| :-: | :------------------ | :-------------------------------------------------------------------------------------------------------------------------- | :--: |
|  1  | 金融时报                | [ft.com](https://www.ft.com/)                                                                                               |  人工  |
|  2  | MarketScreener      | [marketscreener.com](https://www.marketscreener.com/news/commodities/)                                                      |  人工  |
|  3  | 商业标准报               | [business-standard.com](https://www.business-standard.com/)                                                                 |  人工  |
|  4  | 印度国家证券交易所（NSE）      | [ncdex.com](https://www.ncdex.com/)                                                                                         |  人工  |
|  5  | 美国商品期货交易委员会（CFTC）   | [cftc.gov](https://www.cftc.gov/PressRoom/PressReleases/index.htm)                                                          |  A   |
|  6  | 芝商所（CME）            | [cmegroup.com](https://www.cmegroup.com/media-room/press-releases.html)                                                     |  A   |
|  7  | 洲际交易所（ICE）          | [ice.com](https://www.ice.com/media)                                                                                        |  A   |
|  8  | 伦敦金属交易所（LME）        | [lme.com](https://www.lme.com/en/News)                                                                                      |  A   |
|  9  | 国际期货业协会（FIA）        | [fia.org](https://www.fia.org/fia/newsroom?utm_source=FIAWeb&utm_medium=Top)                                                |  A   |
| 10  | 衍生品市场标准研究所（DMIST）   | [dmist-standards.org](https://dmist-standards.org/)                                                                         |  A   |
| 11  | newsnow             | [newsnow.com](https://www.newsnow.com/us/Business/Commodities)                                                              |  A   |
| 12  | 雅虎财经（Yahoo Finance） | [finance.yahoo.com](https://finance.yahoo.com/markets/commodities/)                                                         |  A   |
| 13  | 纳斯达克（Nasdaq）        | [nasdaq.com](https://www.nasdaq.com/news-and-insights)                                                                      |  A   |
| 14  | 印度证监会（SEBI）         | [sebi.gov.in](https://www.sebi.gov.in)                                                                                      |  A   |
| 15  | 美国证券交易委员会（SEC）      | [sec.gov](https://www.sec.gov/newsroom/press-releases)                                                                      |  A   |
| 16  | 英国金融行为监管局（FSA/FCA）  | [fca.org.uk](https://www.fca.org.uk/news)                                                                                   |  A   |
| 17  | 国际掉期与衍生工具协会（ISDA）   | [isda.org](https://www.isda.org/category/news/)                                                                             |  A   |
| 18  | 美国全国期货协会（NFA）       | [nfa.futures.org](https://www.nfa.futures.org/)                                                                             |  A   |
| 19  | 欧洲证券及市场管理局（ESMA）    | [esma.europa.eu](https://www.esma.europa.eu/press-news/esma-news)                                                           |  A   |
| 20  | 印度经济时报              | [economictimes.indiatimes.com](https://economictimes.indiatimes.com/markets/commodities/news)                               |  A   |
| 21  | 国际证监会组织（IOSCO）      | [iosco.org](https://www.iosco.org/media_room/?subsection=media_releases)                                                    |  A   |
| 22  | 英国期货期权世界（FOW）       | [fow.com](https://www.fow.com/insights)                                                                                     |  B   |
| 23  | Mondo Visione（MV）   | [mondovisione.com](https://mondovisione.com/media-and-resources/news)                                                       |  B   |
| 24  | 彭博社（Bloomberg）      | [bloomberg.com](https://www.bloomberg.com/latest?utm_source=homepage&utm_medium=web&utm_campaign=latest)                    |  C   |
| 25  | 标普全球洞察（S&P Global）  | [spglobal.com](https://www.spglobal.com/energy/en/news-research/latest-news#q=&rows=20&pagenum=1&sort=es_unified_dt%20desc) |  C   |

---

## 二、二类信息源注册表（协助成员 1 负责 · 外围协同库）

> [!TIP] 二类源排序说明
> 表格按照**【人工 → A → B】**优先级策略顺序组织。共 23 个网站（2 个人工协同、19 个策略 A、2 个策略 B）。日常由协助成员 1 负责每日浏览与查漏补缺，发现具有编译价值的信息后分享至工作群，由当月编译人员统一筛选、翻译和整理。



| 序号 | 网站中文名称 | 目标网址 (URL) | 访问策略 |
| :--: | :----------- | :------------- | :------: |
| 1 | 金融新闻 | [fnlondon.com](https://www.fnlondon.com/news?mod=qlinks) | 人工 |
| 2 | 莫斯科交易所（MOEX） | [moex.com](https://www.moex.com/（打不开）) | 人工 |
| 3 | 德国联邦金融监督管理局（BaFin） | [bafin.de](https://www.bafin.de/EN/Homepage/homepage_node.html) | A |
| 4 | 香港证券及期货事务监察委员会（SFC） | [sfc.hk](https://www.sfc.hk/TC/) | A |
| 5 | 马来西亚证券委员会（SC） | [sc.com.my](https://www.sc.com.my/) | A |
| 6 | 澳大利亚证券投资委员会（ASIC） | [asic.gov.au](https://asic.gov.au/) | A |
| 7 | 澳大利亚审慎监管局（APRA） | [apra.gov.au](https://www.apra.gov.au/) | A |
| 8 | 新加坡金融管理局（MAS） | [mas.gov.sg](https://www.mas.gov.sg/) | A |
| 9 | 日本金融服务机构（FSA） | [fsa.go.jp](https://www.fsa.go.jp/en/) | A |
| 10 | 金融稳定理事会（FSB） | [fsb.org](https://www.fsb.org/) | A |
| 11 | 英国央行（BoE） | [bankofengland.co.uk](https://www.bankofengland.co.uk/) | A |
| 12 | 伦敦能源经纪人协会（LEBA） | [leba.org.uk](https://www.leba.org.uk/) | A |
| 13 | 德意志银行（Deutsche Bank） | [db.com](https://www.db.com/index?language_id=1&kid=sl.redirect-en.shortcut) | A |
| 14 | 世界交易所联合会（WFE） | [world-exchanges.org](https://www.world-exchanges.org) | A |
| 15 | 伊斯坦布尔证券交易所（Borsa Istanbul） | [borsaistanbul.com](https://borsaistanbul.com/en) | A |
| 16 | 韩国交易所（KRX） | [global.krx.co.kr](https://global.krx.co.kr/main/main.jsp) | A |
| 17 | 新加坡交易所（SGX） | [sgx.com](https://www.sgx.com/derivatives) | A |
| 18 | 蒙特利尔交易所 | [m-x.ca](https://www.m-x.ca/en) | A |
| 19 | 波斯顿期权交易所（BOX） | [boxoptions.com](https://boxoptions.com/) | A |
| 20 | 香港交易及结算所（HKEX） | [hkex.com.hk](https://www.hkex.com.hk/?sc_lang=en) | A |
| 21 | 台湾期货交易所（TAIFEX） | [taifex.com.tw](https://www.taifex.com.tw/enl/eIndex) | A |
| 22 | TradingView | [tradingview.com](https://www.tradingview.com/news/markets/?category=futures) | B |
| 23 | barchart | [barchart.com](https://www.barchart.com/news/commodities) | B |

---

## 三、三类信息源注册表（协助成员 2 负责 · 外围协同库）

> [!TIP] 三类源排序说明
> 表格按照**【人工 → A】**优先级策略顺序组织。共 23 个网站（5 个人工协同、18 个策略 A）。日常由协助成员 2 负责每日浏览与查漏补缺，重点跟踪美欧、亚太及拉美等全球主要衍生品交易所动态。



| 序号 | 网站中文名称 | 目标网址 (URL) | 访问策略 |
| :--: | :----------- | :------------- | :------: |
| 1 | 约翰内斯堡证券交易所（JSE） | [jse.co.za](https://www.jse.co.za/) | 人工 |
| 2 | 印度国家商品及衍生品交易所（NCDEX） | [ncdex.com](https://ncdex.com/) | 人工 |
| 3 | 印度商品交易所（ICEX） | [icexindia.com](https://www.icexindia.com/) | 人工 |
| 4 | 印度多种商品交易所（MCX） | [mcxindia.com](https://www.mcxindia.com/) | 人工 |
| 5 | 马来西亚衍生品交易所（Malaysia Derivatives） | [bursamalaysia.com](https://www.bursamalaysia.com/) | 人工 |
| 6 | MATba ROFEX | [matbarofex.com.ar](https://www.matbarofex.com.ar/) | A |
| 7 | 澳大利亚证券交易所（ASX） | [asx.com.au](https://www.asx.com.au/) | A |
| 8 | 泛欧交易所（Euronext） | [euronext.com](https://www.euronext.com/en) | A |
| 9 | 泰国期货交易所（TFEX） | [tfex.co.th](https://www.tfex.co.th/en/home) | A |
| 10 | 东京金融交易所（TFX） | [tfx.co.jp](https://www.tfx.co.jp/en/) | A |
| 11 | 迪拜商业交易所（DME） | [dubaimerc.com](https://dubaimerc.com/) | A |
| 12 | 日本交易所集团（JPX） | [jpx.co.jp](https://www.jpx.co.jp/english/) | A |
| 13 | 迈阿密国际证券交易所 | [miaxglobal.com](https://www.miaxglobal.com/) | A |
| 14 | 德意志交易所集团（DBAG） | [dbag.com](https://www.dbag.com/) | A |
| 15 | 欧洲期货交易所（Eurex） | [eurex.com](https://www.eurex.com/ex-en/) | A |
| 16 | 欧洲能源交易所（EEX） | [eex.com](https://www.eex.com/en) | A |
| 17 | Nodal交易所 | [nodalexchange.com](https://www.nodalexchange.com/) | A |
| 18 | 芝加哥期权交易所（Cboe） | [ir.cboe.com](https://ir.cboe.com/) | A |
| 19 | 孟买证券交易所（BSE） | [bseindia.com](https://www.bseindia.com/) | A |
| 20 | 巴西交易所（B3） | [b3.com.br](https://www.b3.com.br/pt_br/para-voce) | A |
| 21 | 北美衍生品交易所（Nadex） | [nadex.com](https://www.nadex.com/) | A |
| 22 | 会员交易所（MEMX） | [memx.com](https://memx.com/) | A |
| 23 | 伦敦证券交易所集团（LSEG） | [lseg.com](https://www.lseg.com/en) | A |

---

## 四、子频道与访问策略分类端点说明 (Sub-Feeds & Access Strategies)

### 1. 人工协同端点（人工浏览与报送）
- **一类源（4 站）**：金融时报（FT）、MarketScreener、商业标准报、印度国家证券交易所（NSE/NCDEX）。因受严格硬付费墙或高防 WAF 机器人盾拦截，由编译人员人工日常浏览、发现线索后分享至工作群。
- **二类源（2 站）**：金融新闻（FN London，道琼斯严格 401 硬付费墙）、莫斯科交易所（MOEX，地缘国家防火墙海外 IP 阻断与打不开）。
- **三类源（5 站）**：约翰内斯堡交易所（JSE，Cloudflare 403 质询盾）、印度 NCDEX / 印度 MCX（Akamai 强盾及境外 IP 403 阻断）、印度 ICEX（已停牌退市）、马来西亚衍生品交易所（Bursa Malaysia，Cloudflare 403 质询）。

### 2. 策略 A 调度端点（直接解析与下载）
- **一类源（17 站）**：CFTC、CME、ICE、LME、FIA、DMIST、NewsNow、雅虎财经、纳斯达克、SEBI、SEC、FCA、ISDA、NFA、ESMA、印度经济时报、IOSCO。
- **二类源（19 站）**：BaFin、SFC、SC、ASIC、APRA、MAS、FSA、FSB、BoE、LEBA、Deutsche Bank、WFE、Borsa Istanbul、KRX、SGX、蒙特利尔交易所、BOX、HKEX、TAIFEX。
- **三类源（18 站）**：MATba ROFEX、ASX、Euronext、TFEX、TFX、DME、JPX、MIAX、DBAG、Eurex、EEX、Nodal、Cboe、BSE、B3、Nadex、MEMX、LSEG。
- **技术规范**：新闻发布厅与官方公告公开透明，直接访问解析、Playwright 原生打印 PDF。

### 3. 策略 B 调度端点（标题扫描 + 全网二次检索）
- **一类源（2 站）**：英国期货期权世界（FOW Insights）、Mondo Visione（MV）。
- **二类源（2 站）**：TradingView（交易分析与通讯社聚合快讯）、barchart（大宗商品行情评论与通讯社供稿）。
- **技术规范**：全量扫描最新文章标题列表；以标题核心词在 Google / Bing / PR Newswire 搜索引擎进行全网二次检索并获取公开全文；联合溯源打印 PDF。

### 4. 策略 C 调度端点（专有高防穿透通道）
- **一类源（2 站）**：彭博社（Bloomberg）、标普全球洞察（S&P Global）。
- **技术规范**：针对头部商业媒体高防付费墙与反爬风控机制，通过专有高防穿透通道（BNN Bloomberg、S&P Direct、googlenewsdecoder 直解）全量抓取。

---

## 五、大宗商品关键词智能过滤规则 (Commodity Filter Rules)

```yaml
commodity_filter:
  energy:
    - "oil"
    - "crude"
    - "brent"
    - "wti"
    - "natural gas"
    - "diesel"
    - "refinery"
    - "pipeline"
  metals:
    - "gold"
    - "silver"
    - "copper"
    - "aluminum"
    - "lithium"
    - "iron ore"
  agriculture:
    - "coffee"
    - "soybean"
    - "corn"
    - "wheat"
    - "sugar"
    - "cocoa"
  macro_and_shipping:
    - "freight"
    - "shipping"
    - "hormuz"
    - "red sea"
    - "inflation"
    - "rates"
```

---

## 六、智能体定向调度与执行规范说明 (Agent Execution Protocol)

- **指令「爬取一类的网站新闻」 / 「执行一类采编」**：
  智能体自动读取【一、一类信息源注册表】，筛选所有具有有效访问策略（`A` / `B` / `C`）的 21 个自动化采集源，依次调度对应的抓取引擎执行全量采集，生成当日一类 Manifest 与物理 PDF 存证；同时在汇报中提示 4 个「人工」站点的协同注意事项。
- **指令「爬取二类的网站新闻」**：
  智能体读取【二、二类信息源注册表】。当前二类站点访问策略标注为 `-`（依托人工协同），智能体将列出二类 23 个监控目标，若用户指定接入某个具体源（如 TradingView 或 HKEX），将针对性配置抓取策略并执行。
- **指令「爬取三类的网站新闻」**：
  智能体读取【三、三类信息源注册表】。当前三类站点访问策略标注为 `-`（依托人工协同），智能体将列出三类 23 个监控目标，协助排查各海外交易所当日重要动态。
