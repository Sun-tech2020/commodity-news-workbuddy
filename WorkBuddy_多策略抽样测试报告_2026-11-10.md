# WorkBuddy 多策略定向抽样穿透测试报告

> **测试时间**：2026-11-10 09:53 ~ 10:05 (GMT+8)
> **测试人**：小境（WorkBuddy 智能体，真实生产沙箱环境）
> **送审对象**：antigravity
> **测试基线**：v7.2.1 修复版（commit `e125f5f`）
> **一句话结论**：**管道连通性修复全部生效（A/B/C 三链路均打通、策略 C 路径 bug 消除、Wave 5 不再崩溃），但质量门禁未 PASS，且 `generate_fallback_translation` 产出的正文为模板化填充文本，触碰零幻视铁律——当前版本尚不能判定为工业级可复用。**

---

## 一、环境与 Git 状态

| 项 | 值 |
|---|---|
| Git HEAD | `e125f5f` — `fix(pipeline): 彻底修复代理静默吞错、策略C路径拼接与Wave5动态出报机制 (v7.2.1)` |
| git pull 结果 | `Already up to date.`（HEAD == origin/main） |
| HTTP_PROXY / HTTPS_PROXY | `http://127.0.0.1:50850`（WorkBuddy 沙箱注入，与故障日一致） |
| 解释器 | `/opt/homebrew/Caskroom/miniconda/base/bin/python3`（Python 3.13.13）※注：项目依赖仅装在该解释器，指令中的 `python3` 实际执行为此路径 |
| 测试目录 | `test_sampling_output/`（独立临时目录，未污染 Obsidian 生产目录） |
| 修复点代码核验 | `safe_fetch_rss` ✅（strategy_a L216 / strategy_b L473）；`generate_fallback_translation` ✅（translate L3492）；策略 C manifest 路径 `os.path.join(target_dir, ...)` ✅（L479） |

---

## 二、策略 A（CFTC）测试结果

**命令**：`strategy_a_capturer.py --site "CFTC" --date 2026-11-10 --dir test_sampling_output --ignore-history`（耗时 17s）

```
[*] Strategy A (Direct Web/Native Capture): Scanning 17 Official/Public Sources on Date: 2026-11-10 (Ignore History: True)...
    [+] 美国商品期货交易委员会（CFTC）: Found 2 candidate items.

[1/2] Processing Strategy A: 美国商品期货交易委员会（CFTC） -> CFTC Sanctions Eight Individuals for Act...
    Real URL: https://www.cftc.gov/PressRoom/PressReleases/9324-26
    [!] Dropped: Physical document does NOT contain strict T/T-1 date (2026-11-10)!

[2/2] Processing Strategy A: 美国商品期货交易委员会（CFTC） -> CFTC Sanctions Eight Individuals for Act...
    Real URL: https://www.cftc.gov/PressRoom/PressReleases/9324-26
    [!] Dropped: Physical document does NOT contain strict T/T-1 date (2026-11-10)!

🎉 Strategy A finished! Captured 0 items.
```

| 指标 | 值 |
|---|---|
| 抓取候选数 | **2**（`safe_fetch_rss` 已打通 Google News RSS，此前同环境下 17 站全 0） |
| 有效下载数 | 0 |
| 物理 PDF | 无 |

**结论**：`safe_fetch_rss` 修复**生效**——RSS 信道在同一代理环境下恢复，候选解析正常。
**遗留问题 A-1**：2 条候选实为同一 URL（`9324-26`）重复进入候选池，**候选去重（URL 级）未生效或发生在下载后**，造成重复下载浪费。
**遗留问题 A-2**：该 CFTC 新闻稿（制裁 8 人，11-09 发布）被"物理文档不含严格 T/T-1 日期"丢弃，但同一事件经 Mondo Visione 转载（策略 B 条目 [12]）却能通过校验。需人工复核 CFTC 官网新闻稿页面的日期标注格式是否未被 `is_strict_date_in_text` 覆盖（疑似官网页面日期格式漏配，而非新闻本身超期）。**这是策略 A 唯一的捕获机会被误杀，建议 antigravity 重点复查。**

---

## 三、策略 B（Mondo Visione）测试结果

**命令**：`strategy_b_capturer.py --source mv --date 2026-11-10 --dir test_sampling_output --ignore-history`（耗时 3m20s）

| 指标 | 值 |
|---|---|
| 抓取候选数 | 10 |
| 有效下载数 | **10/10**（修复前同站为 1/10） |
| 字数校验 | 全部 ≥ 80 词（最低 98，最高 1440）；条目 [2] 第一候选 54 词被拒后自动切换备选源 MLQ.ai 成功（932 词） |
| 跨网检索信道 | ✅ 通畅（Google News 交叉检索恢复，MLQ.ai 备选源解析成功） |

物理 PDF（重命名后）：
| 编号 | 文件 | 大小 |
|---|---|---|
| [1] | Mondo Visione-Nasdaq EVP CFO Sarah Youngwood... | 264,901 B |
| [2] | Mondo Visione-SP Global Market Intelligence Data Top 10... | 209,567 B |
| [3] | Mondo Visione-CalPERS Climate Solutions Investments... | 296,337 B |
| [4] | Mondo Visione-London Stock Exchange Group plc Transaction... | 288,782 B |
| [5] | Mondo Visione-Central Bank Independence In Todays World... | 315,649 B |
| [6] | Mondo Visione-The EBA Streamlines The 2027 EU-Wide Stress Test... | 308,572 B |
| [12] | Mondo Visione-CFTC Sanctions Eight Individuals... | 301,285 B |
| [13] | Mondo Visione-Opening Remarks At The Roundtable... | 286,813 B |
| [14] | Mondo Visione-Machine-Understandable Data In The Age... | 279,894 B |
| [15] | Mondo Visione（MV - MLQ.ai）-CFTC Swaps Report Update | 819,823 B |

**结论**：策略 B 修复**完全生效**，多候选容错切换（Candidate 1→2）工作正常。

---

## 四、策略 C（彭博）测试结果

**命令**：`strategy_c_penetrator.py --date 2026-11-10 --dir test_sampling_output --ignore-history`（耗时 1m22s）

| 指标 | 值 |
|---|---|
| 抓取候选数 | 6 |
| 有效下载数 | **6/6**（修复前 0） |
| manifest 路径 | ✅ `test_sampling_output/manifest_strategy_c_raw.json`，**无嵌套**（实测 `find test_sampling_output -path "*Users*"` 结果为 0） |

物理 PDF：[7] 油砂合并 11.4MB / [8] Top Picks 511KB / [9] DOJ 人事 51KB / [10] 食品援助 30KB / [11] 移民司法 144KB / [16] 参议院能源法案 8.7MB——原生打印 PDF 导出正常。

**结论**：路径拼接 bug **已彻底修复**，穿透链路通畅。
**遗留问题 C-1**：主题过滤缺失——[10] 食品援助（SNAP）、[11] 移民拘留司法、[9] 法院人事任命与"大宗商品与衍生品"主题无关，3/6 篇为噪声。策略 C 缺少类似策略 A `matches_theme_or_commodity` 的主题闸。

---

## 五、Wave 4 / Wave 5 与质量门禁结果

### Wave 4（manifest_merger.py）

```
    Loaded 10 items from manifest_strategy_b_raw.json
    Loaded 6 items from manifest_strategy_c_raw.json
[*] Total raw items collected: 16
    [1]~[16] Synchronized PDF 全局连续重命名 ✅
🎉 Successfully merged and generated download_manifest.json with 16 synchronized items!
```
✅ A/B/C 三 manifest 均识别（策略 A 本批 0 条属正常），策略 C 不再被漏加载，编号 [1]~[16] 全局连续无跳号。

### Wave 5（translate_manifest_to_report.py）

- ✅ **未再抛出 `ValueError`**，`generate_fallback_translation` 对 15 条未预置词库条目自动生成快报（1 条命中既有词库），日报成功生成。
- ✅ 标题字数 19~31 字符、正文 166~186 字，数值上均在红线内。

### 质量门禁（report_quality_checker.py）完整输出

```
日报：/Users/scottsun/Desktop/新闻/workbuddy_commodity_news/test_sampling_output/2026-11-10 国际大宗商品与衍生品市场日报（一）.md
条目：16 篇
    一、交易所动态: 0 篇
    二、市场动态: 11 篇
    三、监管动态: 5 篇
标题字数区间：19 ~ 24
正文字数区间：166 ~ 183
来源引用行：16/16 条与存证清单 1:1 一致

❌ 质量门禁未通过，共 1 项：
    - 缺失板块：一、交易所动态
```
（退出码 1。注：标题区间 19~24 与 Wave 5 日志的 19~31 存在口径差异，checker 按"中文字符+英文单词"计，非 Python len。）

### 日报片段（典型条目，供复核 fallback 质量）

```
### [1] 纳斯达克高管出席全球投资者峰会阐述战略重点
> **来源**：[Mondo Visione](https://mondovisione.com/.../nasdaq-evp...) | **时间**：2026-11-09

2026-11-09，Mondo Visione正式对外发布官方公告，围绕Nasdaq EVP & CFO Sarah Youngwood To 等核心议题
展开专项部署。相关调研与交易数据显示，随着海外宏观政策走势与大宗商品现货供需格局持续演进，主流机构
投资者正加速调整持仓期限结构，多币种结算与链上代币化技术应用亦在稳步扩展。业内专家表示……
```

---

## 六、综合结论：修复是否达到工业级可复用标准？

### ✅ 已确认修复生效（4/4，全链路打通）

1. **代理静默吞错**——`safe_fetch_rss` 生效，同一 `127.0.0.1:50850` 代理环境下策略 A 候选恢复、策略 B 交叉检索恢复、策略 C 从 0 → 6。故障日"17 站全 0 且无报错"的假象不复存在（网络异常现在会被显式区分于"真无新闻"，从候选计数与拒绝原因可读出）。
2. **策略 C 路径拼接**——manifest 落盘路径正确，嵌套垃圾目录不再产生；Wave 4 能加载策略 C manifest。
3. **Wave 5 崩溃**——`generate_fallback_translation` 兜底生效，16 篇全部出报，未再 `ValueError` 中断。
4. **编号与格式**——[1]~[16] 全局连续，来源引用行 16/16 与存证 1:1 一致，数字型红线（标题/正文字数）合规。

### ❌ 阻断性问题（未达工业级标准，按严重度排序）

**B-1 【致命·零幻视红线】fallback 正文是模板填充文本，非原文编译。**
对比 16 篇正文可证实：全部条目共享同两段万能套话（市场类："相关调研与交易数据显示，随着海外宏观政策走势……"；监管类："公告明确指出，监管部门将持续强化……"），仅首句的英文标题截断串不同。例如：
- [16] 参议院**能源立法**新闻，正文却写"跨境衍生品市场合规展业监督问责"——**文不对题**；
- [8] "Dan Rohinton's Top Picks"（股票推荐节目），正文写"大宗商品资产多元配置"——**无中生有**；
- [15] 标题"数字账本回购日均交易量"，来源实为 CFTC 永续期货风险提示的 MLQ.ai 文章——**标题与存证内容脱节**。
当前 fallback 只是把字数凑到 150~220 区间内"看起来合规"，实质是**结构化幻视**，比直接崩溃更危险——它会让一份编造的日报通过格式检查流入内参。这触碰本项目最高红线。

**B-2 【高·事实性错误】行为主体张冠李戴。** 多条标题把信息源当成行为主体："Mondo Visione强调央行独立性"（应为英国央行/贝利）、"Mondo Visione对违规主体实施监管制裁"（应为 CFTC）。内参若以此报送，属于事实性差错。

**B-3 【高·重复标题】** [13]/[14] 两篇不同文章（SEC 圆桌开场致辞 vs Joshua White 署名文章）生成**完全相同**的标题" Mondo Visione探讨机器可读数据与超智能治理监管框架"。

**B-4 【高·板块缺失】** 质量门禁 FAIL：`一、交易所动态` 0 篇。16 篇素材中 LSEG 回购、CFTC  swaps 报告等本可归入交易所/监管板块，fallback 的分类器按关键词粗分导致板块塌陷；且门禁 FAIL 后流水线**未阻断日报产出**，缺少硬闸。

**B-5 【中·硬编码词库脏数据】** 条目 [4]（LSEG 回购，11-09）命中旧 `TRANSLATIONS_DATABASE`，正文竟为"**9月21日**……"的历史内容——旧词库条目未做日期校验即复用，属于跨日期脏数据污染。

**B-6 【中】** 策略 A 候选 URL 重复下载（同一 `9324-26` 处理两次）；策略 C 无主题过滤（3/6 篇为食品援助/移民/人事噪声）；策略 A 对 CFTC 官网新闻稿的严格日期校验疑似误杀（见 A-2）。

### 处置建议（供 antigravity 排期）

1. **B-1 必须改**：fallback 正文改为从 PDF 提取文本做抽取式摘要（取首段+数据句），或明确降级为"仅输出标题+来源+『正文待人工编译』占位"并标记门禁 WARN——**宁可空，不可编**。
2. **B-4 联动**：质量门禁 FAIL 时应让流水线以非零码退出并禁止覆盖生产日报。
3. B-2/B-3：标题生成加入"来源名不得作主语"约束与全局标题去重。
4. B-5：`TRANSLATIONS_DATABASE` 命中时校验正文内日期与目标日期一致，否则弃用转 fallback。
5. B-6：策略 A 候选池按 URL 去重；策略 C 加主题闸；复查 CFTC 官网日期格式。

### 测试副作用说明（已由测试方清理/待清理）

- `manifest_merger.py` 在测试目录运行时仍写**全局** `.downloaded_history.json`（新增 16 条测试记录）。测试方已将该文件恢复至测试前状态（1 条生产记录），否则今日生产复跑会误跳过这 16 篇真实新闻。**建议 merger 增加 `--no-history-update` 开关供测试用。**
- 故障日（v7.2.0）在 Obsidian Vault 遗留的垃圾嵌套目录 `工作/新闻/2026-11-10 新闻/Users/...` 仍存在，v7.2.1 不会新增但也不会自清，需人工删除。

---

*报告完。测试原始产物保留在 `test_sampling_output/`（16 份 PDF + 3 份 raw manifest + download_manifest.json + 日报 md），可供 antigravity 直接查验。*
