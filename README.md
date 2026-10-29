# 国际大宗商品与衍生品市场每日新闻自动化采编系统

本系统面向研究部提供高确定性、工业级的一键新闻采集、底层高保真 PDF 物理留痕与专业内参日报自动化编制能力。支持在 **WorkBuddy 智能体桌面端** 或普通终端环境中运行，原生兼容 **macOS** 与 **Windows** 双系统。

---

## 一、首次使用：极简环境配置（仅需配置一次）

### 1. 基础 Python 环境准备
建议安装 Python 3.10 或更高版本。
打开终端（Mac 的 `Terminal` 或 Windows 的 `PowerShell` / `CMD`），进入当前脚本解压目录，运行：
```bash
# 1. 一键安装依赖包
pip install -r requirements.txt

# 2. 安装无头浏览器驱动（用于网页打印高保真 PDF 物理存证）
playwright install chromium
```

### 2. 配置你的 Obsidian 路径
打开当前目录下的 `config.json` 文件：
```json
{
  "obsidian_news_dir": "",
  "custom_user_agent": "CommodityNewsScraper/2.0 (commodity_news_agent@internal.com)"
}
```
* **如果你使用默认路径**：如果你的 Obsidian 新闻目录正是位于个人文档下的 `Documents/Obsidian Vault/工作/新闻`，则保持 `"obsidian_news_dir": ""` 留空即可，系统会自动识别用户主目录。
* **自定义路径示例**：
  * **Mac 系统**：`"obsidian_news_dir": "/Users/你的用户名/Documents/Obsidian Vault/工作/新闻"`
  * **Windows 系统**：`"obsidian_news_dir": "D:/Obsidian Vault/工作/新闻"` 或 `"C:\\Users\\你的用户名\\Documents\\Obsidian Vault\\工作\\新闻"`

---

## 二、日常使用方式（二选一）

### 推荐方式：在 WorkBuddy 智能体中对话运行（最简最智能）
1. 在 WorkBuddy 客户端中，将当前 `workbuddy_commodity_news` 文件夹作为工作区/项目打开；
2. 直接在 WorkBuddy 聊天框中对智能体发送：
   > **“爬取今日新闻”** 或 **“生成今日日报”**
3. WorkBuddy 智能体将自动：
   * 在后台驱动执行各波次抓取与 PDF 物理存证；
   * 自动阅读抓取到的英文 PDF 存证；
   * 依据内置的公文级金标准（标题 15~35 字符、正文 150~220 字、三大板块严格分类），直接编译生成规范的三段式市场日报；
   * 自动落盘写入你的 Obsidian 目标文件夹中。

---

### 备用方式：在本地终端一键运行（用于底层数据采编）
打开终端进入本目录，直接运行：
```bash
# 运行当天新闻抓取与物理存证
python run_daily.py

# 如需补跑或测试特定历史日期（如 2026-10-28）
python run_daily.py --date 2026-10-28
```
运行完成后，所有 50+ 篇真实高保真 PDF 文件与 `download_manifest.json` 将全部整齐落盘在当日的 Obsidian 目录下。

---

## 三、目录与文件结构一览

```text
workbuddy_commodity_news/
├── config.json                     # 统一配置文件（设置 Obsidian 路径）
├── config_loader.py                # 跨平台（Mac/Win）路径与环境加载模块
├── run_daily.py                    # 极简一键运行入口（含依赖预检）
├── requirements.txt                # Python 依赖清单
├── WORKBUDDY_INSTRUCTIONS.md       # WorkBuddy 智能体执行提示词与三段式内参规范
├── strategy_a_capturer.py          # 策略 A: FOW 抓取 + 全网二次检索
├── strategy_b_capturer.py          # 策略 B: Mondo Visione + 14 家官方机构
├── strategy_c_penetrator.py        # 策略 C: 彭博社/标普全球专有高防穿透
├── manifest_merger.py              # 存证去重汇总、三大板块重排序与 [1]~[N] 重命名
├── targeted_refetcher.py           # 靶向重搜换源工具
├── full_text_verifier.py           # 物理存证完整性与文本真实性校验
└── README.md                       # 本使用说明
```

---

## 四、常见问题与注意事项

1. **Windows 路径反斜杠报错？**
   在 `config.json` 中配置 Windows 路径时，建议使用正斜杠 `/`（例如 `"D:/Obsidian/新闻"`），或者使用双反斜杠 `\\`，避免单反斜杠转义报错。
2. **需要重新全量抓取时怎么办？**
   本系统自带去重历史记录机制（`.downloaded_history.json`），同一篇新闻不会重复下载。若因调试需要强制重新全量抓取，可在命令后加上参数 `--ignore-history`：
   ```bash
   python run_daily.py --ignore-history
   ```
3. **遇到网络超时或部分网站拦截？**
   系统内置分波梯队重试机制与专有无墙穿透信道，偶尔个别网站出现单篇波动不影响全局大盘产出，系统会在最终日志中清晰列出抓取统计。

