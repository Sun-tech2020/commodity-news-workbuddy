#!/usr/bin/env bash
# ==============================================================================
# 国际大宗商品与衍生品市场新闻采编流水线 - macOS / Linux 一键启动器
#
# 职责：自动探测并锁定「已具备全部依赖」的 Python 解释器，再驱动 run_daily.py。
# 解决多解释器共存（托管 Python / conda / 系统 Python）时依赖不在同一环境的痛点。
#
# 用法：
#   ./run.sh                        # 抓取当天
#   ./run.sh --date 2026-10-29      # 抓取指定日期
#   ./run.sh --ignore-history       # 忽略去重历史全量重采
#   PYTHON_BIN=/path/to/python ./run.sh   # 强制指定解释器（跳过探测）
# ==============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 运行 run_daily.py 所必需的模块（与 run_daily.py::check_environment 保持一致）
REQUIRED_MODULES="playwright bs4 feedparser pypdf"

# ------------------------------------------------------------------------------
# 构造候选解释器列表：优先级从高到低
# ------------------------------------------------------------------------------
CANDIDATES=()

# 1) 环境变量强制指定
if [ -n "${PYTHON_BIN:-}" ]; then
    CANDIDATES+=("$PYTHON_BIN")
fi

# 2) PATH 中的默认命令
CANDIDATES+=("python3" "python")

# 3) 常见发行版绝对路径
CANDIDATES+=(
    "$HOME/.workbuddy/binaries/python/versions/3.14.3/bin/python3"
    "$HOME/.workbuddy/binaries/python/versions/3.13.12/bin/python3"
    "/opt/homebrew/Caskroom/miniconda/base/bin/python3"
    "$HOME/miniconda3/bin/python3"
    "$HOME/anaconda3/bin/python3"
    "$HOME/miniforge3/bin/python3"
    "/opt/miniconda3/bin/python3"
    "/usr/local/bin/python3"
    "/usr/bin/python3"
)

# ------------------------------------------------------------------------------
# 探测函数：解释器存在 + 全部必需模块可导入 → 判定可用
# ------------------------------------------------------------------------------
probe() {
    local py="$1"
    command -v "$py" >/dev/null 2>&1 || [ -x "$py" ] || return 1
    "$py" - "$REQUIRED_MODULES" <<'PYEOF' >/dev/null 2>&1
import sys, importlib
for m in sys.argv[1].split():
    importlib.import_module(m)
PYEOF
}

resolve_python() {
    local seen=" "
    local py resolved
    for py in "${CANDIDATES[@]}"; do
        [ -z "$py" ] && continue
        # 去重（避免同一解释器重复探测）
        resolved="$(command -v "$py" 2>/dev/null || echo "$py")"
        case "$seen" in *" $resolved "*) continue;; esac
        seen="$seen$resolved "
        if probe "$py"; then
            echo "$resolved"
            return 0
        fi
    done
    return 1
}

echo "=============================================================="
echo " 正在探测可用的 Python 解释器（需含: ${REQUIRED_MODULES}）"
echo "=============================================================="

PYTHON="$(resolve_python)"

if [ -z "${PYTHON:-}" ]; then
    echo ""
    echo "[错误] 未找到具备全部依赖的 Python 解释器。"
    echo ""
    echo "请手动安装依赖后重试："
    echo "  python3 -m pip install -r \"${SCRIPT_DIR}/requirements.txt\""
    echo "  python3 -m playwright install chromium"
    echo ""
    echo "或使用 PYTHON_BIN 显式指定解释器，例如："
    echo "  PYTHON_BIN=/opt/homebrew/Caskroom/miniconda/base/bin/python3 ./run.sh"
    exit 1
fi

echo " 已锁定解释器: ${PYTHON}"
echo " 版本: $("$PYTHON" --version 2>&1)"
echo "=============================================================="
echo ""

exec "$PYTHON" "${SCRIPT_DIR}/run_daily.py" "$@"
