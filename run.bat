@echo off
rem =============================================================================
rem  国际大宗商品与衍生品市场新闻采编流水线 - Windows 一键启动器
rem
rem  职责：自动探测并锁定「已具备全部依赖」的 Python 解释器，再驱动 run_daily.py。
rem  解决多解释器共存（官方 Python / conda / Anaconda）时依赖不在同一环境的痛点。
rem
rem  用法：
rem    run.bat                       抓取当天
rem    run.bat --date 2026-10-29     抓取指定日期
rem    run.bat --ignore-history      忽略去重历史全量重采
rem    set PYTHON_BIN=C:\path\to\python.exe && run.bat    强制指定解释器
rem =============================================================================

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "PYFOUND="

rem ---- 候选解释器列表（按优先级排列）---------------------------------------
for %%P in (
    "%PYTHON_BIN%"
    "python"
    "python3"
    "%USERPROFILE%\miniconda3\python.exe"
    "%USERPROFILE%\anaconda3\python.exe"
    "%USERPROFILE%\miniforge3\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "C:\ProgramData\miniconda3\python.exe"
    "C:\ProgramData\Anaconda3\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
) do (
    if "!PYFOUND!"=="" call :probe "%%~P"
)

echo ==============================================================
echo  正在探测可用的 Python 解释器（需含: playwright bs4 feedparser pypdf）
echo ==============================================================

if "!PYFOUND!"=="" (
    echo.
    echo [错误] 未找到具备全部依赖的 Python 解释器。
    echo.
    echo 请手动安装依赖后重试：
    echo   python -m pip install -r "%SCRIPT_DIR%requirements.txt"
    echo   python -m playwright install chromium
    echo.
    echo 或使用 PYTHON_BIN 显式指定解释器，例如：
    echo   set PYTHON_BIN=C:\Users\you\miniconda3\python.exe
    echo   run.bat
    endlocal
    exit /b 1
)

echo  已锁定解释器: !PYFOUND!
for /f "tokens=*" %%v in ('"!PYFOUND!" --version 2^>^&1') do echo  版本: %%v
echo ==============================================================
echo.

"!PYFOUND!" "%SCRIPT_DIR%run_daily.py" %*

endlocal
exit /b %ERRORLEVEL%

rem ---- 子过程：校验单个解释器是否可用 --------------------------------------
:probe
set "PY=%~1"
if "!PY!"=="" exit /b 1

rem 解释器必须可执行（在 PATH 中，或是有效的绝对路径）
where "!PY!" >nul 2>nul
if errorlevel 1 (
    if not exist "!PY!" exit /b 1
)

rem 校验全部必需模块可导入
"!PY!" -c "import playwright,bs4,feedparser,pypdf" >nul 2>&1
if errorlevel 1 exit /b 1

set "PYFOUND=!PY!"
exit /b 0
