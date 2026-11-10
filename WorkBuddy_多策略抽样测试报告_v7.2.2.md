# WorkBuddy 多策略抽样测试报告（v7.2.2 复测验收）

> **测试时间**：2026-11-10 10:32 ~ 10:45 (GMT+8)
> **测试人**：小境（WorkBuddy 智能体，真实生产沙箱环境）
> **送审对象**：antigravity
> **测试基线**：v7.2.2，commit `36553f8` — `fix(pipeline): 彻底消除零幻视模板套话、修复前导零日期误杀与交易所板块归类`
> **一句话结论**：**形式层（连通性/路径/板块/字数/门禁）已全部达标，四大质量红线首次全 PASS；但内容层（B-1 零幻视）仅完成"换皮"未完成重构——17/17 篇正文仍共享同一骨架，9/17 篇把站点页眉当作"核心事实要点"。判定：可交付但不可作为内参直接报送，需第三轮修正。**

---

## 一、环境与 Git 状态

| 项 | 值 |
|---|---|
| Git HEAD | `36553f8`（v7.2.2），`git pull` 返回 `Already up to date.` |
| 上一基线 | `e125f5f`（v7.2.1，上轮被测版本） |
| HTTP_PROXY / HTTPS_PROXY | `http://127.0.0.1:50850`（与故障日、上轮测试完全一致，具备可比性） |
| 解释器 | `/opt/homebrew/Caskroom/miniconda/base/bin/python3`（Python 3.13.13） |
| 测试目录 | `test_sampling_output/`（已按指令清空重建） |

---

## 二、策略 A（CFTC）复测结果 — ✅ 前导零 Bug 已解决

**命令**：`strategy_a_capturer.py --site "CFTC" --date 2026-11-10 --dir test_sampling_output --ignore-history`（耗时 10s）

```
    [+] 美国商品期货交易委员会（CFTC）: Found 1 candidate items.
[1/1] Processing Strategy A: CFTC -> CFTC Sanctions Eight Individuals for Act...
    Real URL: https://www.cftc.gov/PressRoom/PressReleases/9324-26
    ✅ Verified Strategy A PDF: 62 KB | Pages: 1 | Valid Words: 236
🎉 Strategy A finished! Captured 1 items.
```

| 核验项 | 上轮 v7.2.1 | 本轮 v7.2.2 |
|---|---|---|
| 候选数 | 2（同 URL 重复） | **1（URL 去重生效）** |
| 前导零日期校验 | ❌ `Dropped: does NOT contain strict T/T-1 date` | ✅ **通过**（9324-26 成功入库） |
| 物理 PDF | 无 | ✅ **62,491 B / 1 页 / 236 有效词** |
| 文件名 | — | `[15] 美国商品期货交易委员会（CFTC）-CFTC Sanctions Eight Individuals for Acting as Unregist.pdf` |

**结论**：A-2（前导零误杀）与"候选重复下载"两项**均已根除**。

---

## 三、策略 B（Mondo Visione）复测结果 — ✅ 稳定

**命令**：`strategy_b_capturer.py --source mv --date 2026-11-10 --dir test_sampling_output --ignore-history`（耗时 3m03s）

| 指标 | 值 |
|---|---|
| 候选数 | 10 |
| 有效下载 | **10/10**（与上轮一致，稳定复现） |
| 字数校验 | 全部 ≥ 80 词（98 ~ 1440） |
| 多候选切换 | 条目 [2] 首选 54 词被拒 → 自动切换 MLQ.ai（932 词）成功 |

PDF 大小区间 216KB ~ 858KB，10 份全部通过全文校验。**无回归。**

---

## 四、策略 C（彭博）负向过滤复测 — ⚠️ 部分生效

**命令**：`strategy_c_penetrator.py --date 2026-11-10 --dir test_sampling_output --ignore-history`（耗时 1m17s）

| 上轮 v7.2.1 候选（6） | 本轮 v7.2.2 候选（6） | 判定 |
|---|---|---|
| Trump Plan Strip Food Aid（SNAP 食品援助） | ❌ 已消失 | ✅ 已过滤 |
| Nuclear Option / 移民拘留司法 | ❌ 已消失 | ✅ 已过滤 |
| DOJ Lawyer Gets Nod（得州法院人事） | ❌ 已消失 | ✅ 已过滤 |
| Dan Rohinton's Top Picks（股票推荐） | ❌ 已消失 | ✅ 已过滤 |
| — | ➕ **ICE Joins Wind Derivatives Push**（风电衍生品） | ✅ 主题高度相关 |
| — | ➕ **Crypto Exemption Will Test SEC's Authority** | ✅ 监管相关 |
| 油砂合并 / 参议院能源法案 | 保留 | ✅ 保留合理 |
| — | ⚠️ **Canada launches instant payments network**（即时支付清算） | 边缘噪声 |
| — | ⚠️ **Dechert Adds DOJ Attorney**（律所招聘） | 残留噪声 |

**结论**：C-1 主干修复生效（原 4 条明显噪声全部清除，新增 2 条高相关命中），但**主题闸仍不完整**，6 条中仍有 2 条（33%）为支付清算/律所招聘类边缘内容。

---

## 五、板块归类复测结果 — ✅ 已修复

**命令**：`manifest_merger.py --dir test_sampling_output --no-history-update`

```
    Loaded 1 items from manifest_strategy_a_raw.json
    Loaded 10 items from manifest_strategy_b_raw.json
    Loaded 6 items from manifest_strategy_c_raw.json
[*] Total raw items collected: 17
    [1]~[17] Synchronized PDF 全局连续重命名 ✅
[*] Testing mode: Skipped updating global deduplication history.
🎉 Successfully merged and generated download_manifest.json with 17 synchronized items!
```

| 核验项 | 结果 |
|---|---|
| 板块齐全 | ✅ 一、交易所动态 **3 篇** / 二、市场动态 7 篇 / 三、监管动态 7 篇 |
| Nasdaq 归类 | ✅ 正确落入「一、交易所动态」[1] |
| LSEG 归类 | ✅ 正确落入「一、交易所动态」[2] |
| ICE 归类 | ✅ 正确落入「一、交易所动态」[3] |
| A/B/C 三 manifest | ✅ 全部加载（上轮策略 A 0 条未暴露的问题本轮得到实证） |
| `--no-history-update` | ✅ 生效，打印 `Testing mode: Skipped updating global deduplication history.` |
| 历史文件实测 | ✅ `.downloaded_history.json` 仍为 1 条生产记录（`last_updated: 2026-11-10T08:53:27`），**未被测试污染** |

**B-4 板块塌陷问题已根除；测试污染问题已通过开关根治。**

---

## 六、Wave 5 零幻视与主体复测 — ⚠️ 主体已修正，正文仍不达标

### 6.1 主体（B-2）—— ✅ 标题层已彻底修正

上轮典型错误 "Mondo Visione强调央行独立性" / "Mondo Visione实施监管制裁" **全部消失**，本轮典型标题：

- `[6] 英国央行发表专题演讲强调央行独立性并警惕AI金融风险` → 主体 **英国央行** ✅
- `[1] 纳斯达克高管出席全球投资者峰会阐述战略重点` → 主体 **纳斯达克** ✅
- `[11] 美国商品期货交易委员会制裁八名非法经纪居间人员…` → 主体 **CFTC** ✅
- `[2] 伦敦证券交易所集团执行公司股份回购方案以优化资产资本结构` → 主体 **LSEG** ✅

### 6.2 正文（B-1）—— ❌ 仍为模板骨架，且新增"伪事实"插入

对 17 篇正文做句子级比对，**套话覆盖率**：

| 固定句式 | 命中 |
|---|---|
| "根据官方公布的原始文书披露，相关核心事实要点如下：" | **17/17** |
| "此项动态备受国际大宗商品与金融衍生品市场重点关注" | **17/17** |
| "后续具体执行进展将保持跟踪。" | **17/17** |
| 插入站点页眉噪声 "FTSE Mondo Visione Exchanges Index: 106," 充当"核心事实要点" | **9/17** |
| 通用市场套话 "有助于各类产业实体…完善多资产对冲风控" | 7/17 |
| 通用监管套话 "维护公平有序的交易环境…打击违法违规中介" | 7/17 |

**关键发现**：v7.2.2 把上一版的"万能套话"替换成了"套话 + 抓取噪声"结构。以 [1] 为例：

```
2026-11-09，纳斯达克（Nasdaq）正式围绕"纳斯达克高管出席全球投资者峰会阐"等核心事项披露最新动态。
根据官方公布的原始文书披露，相关核心事实要点如下：Mondo Visione Worldwide Financial Markets
Intelligence FTSE Mondo Visione Exchanges Index: 106,。交易所高管与专业人士表示……
```

所谓"核心事实要点"，实际是 Mondo Visione 网站**页眉导航 + 指数行情条**（原页面 `FTSE Mondo Visione Exchanges Index: 106,xxx +55.53`），并在 100 字符处硬截断。它既非该新闻的事实，也非正文摘要。

**判定**：这仍是伪事实——用"根据官方原始文书披露"的措辞为无关噪声背书，比上一版的纯套话更具误导性。**B-1 未根除。**

### 6.3 脏数据（B-5）—— ✅ 已清除

上轮 [4] 出现的 "9月21日……" 历史旧数据已不存在；17 条正文日期全部对齐 2026-11-09，无跨日期污染。

### 6.4 新暴露问题（上轮未检出）

| 编号 | 问题 | 证据 |
|---|---|---|
| N-1 | **标题硬截断，语义断裂** | 5 条标题在 28 字符处被切断：`…并处以行政`、`…持续攀升刷`、`…探讨机器可读数据与超智` |
| N-2 | **标题重复未去重** | [12]/[13] 两篇不同文章标题完全相同：`美国证券交易委员会召开专题圆桌会议探讨机器可读数据与超智` |
| N-3 | **跨源同一事件重复入库** | [11]（Mondo Visione 转载）与 [15]（CFTC 官网原文）为同一份制裁新闻稿，占两个编号 |
| N-4 | **标题与存证内容脱节** | [9] 加拿大即时支付 → `彭博社发布最新业务发展规划与市场运行公报`；[14] MLQ.ai 永续期货风险文章 → `…分布式账本回购日均交易量持续攀升刷`；[17] 加密豁免 → `美国证券交易委员会发布最新业务发展规划与市场运行公报` |
| N-5 | **正文主体与标题不一致** | [10] 实为 Dechert 律所聘用司法部前检察官，标题却写 `美国司法部推进得州司法任命强化跨机构合规监管` |

---

## 七、质量门禁输出（完整控制台文本）

```
日报：/Users/scottsun/Desktop/新闻/workbuddy_commodity_news/test_sampling_output/2026-11-10 国际大宗商品与衍生品市场日报（一）.md
条目：17 篇
    一、交易所动态: 3 篇
    二、市场动态: 7 篇
    三、监管动态: 7 篇
标题字数区间：20 ~ 28
正文字数区间：158 ~ 174
来源引用行：17/17 条与存证清单 1:1 一致

✅ 四大质量红线全部通过。
```

**退出码 0**，为项目历史上首次全绿。**但必须指出：该门禁只校验板块齐全、字数区间、来源行一致性等"形式指标"，不具备语篇保真度的检测能力——所以一份正文为模板骨架的日报仍能拿满分。** 这是门禁本身的盲区，建议后续增加"正文与存证文本重合度/关键实体命中率"检查。

---

## 八、最终结论

### ✅ 已达工业级（形式与工程层，6/6）

1. 前导零日期误杀（A-2）：根治，CFTC 原稿 62KB/236 词成功入库；
2. 候选重复下载：根治（2→1）；
3. 策略 B 稳定性：10/10 可复现，多候选切换正常；
4. 策略 C 路径拼接：无嵌套，manifest 落盘正确；
5. 板块归类（B-4）：`一、交易所动态` 从 0 → 3 篇，Nasdaq/LSEG/ICE 归位准确；
6. 测试历史隔离：`--no-history-update` 生效，生产去重库零污染；脏数据（B-5）清除。

### ⚠️ 尚未达工业级（内容可信度层，2 项）

**核心阻断项 B-1 未解决**：正文仍是"固定三段式骨架 + 抓取噪声"填充，17/17 篇共享同一句式模板，9/17 篇把网站页眉当"核心事实要点"。字数合规、板块齐全、门禁全绿——但语义层面依然不是对存证原文的编译。以零幻视铁律衡量，当前日报**不可以内参形式报送**。

**建议第三轮聚焦三件事**（按优先级）：
1. **正文改为抽取式**：从 PDF 正文（跳过页眉/导航/指数条区域）抽取首段事实句 + 含数字数据句，拼接成 150~220 字；若抽取失败，输出"原文要点未成功提取，待人工编译"占位并让门禁判 WARN，**不得用套话补足字数**。
2. **标题生成加语义边界**：截断改在词/短语边界，禁止以"行政/刷/超智"等残句收尾；全局标题去重。
3. **跨源事件去重**：以原文标题相似度（或新闻稿编号，如 CFTC `9324-26`）合并同源转载，避免同一事件占两个编号。

---

*测试产物：`test_sampling_output/` 内 17 份 PDF（合计约 25MB）、3 份 raw manifest、`download_manifest.json` 与日报 md，均可供 antigravity 直接比对存证原文与正文的偏差。*
