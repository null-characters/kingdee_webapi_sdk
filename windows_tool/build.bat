@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo  金蝶成本核算工具 - Windows 打包脚本
echo  （会把 Python 和依赖一起打进单个 exe，用户机器无需装环境）
echo ============================================================
echo.

echo [1/4] 检查 Python ...
python --version
if errorlevel 1 (
    echo.
    echo  [错误] 没有找到 python 命令。
    echo  请先安装 Python 3.11 或更高版本，安装时务必勾选
    echo  "Add python.exe to PATH"，装完重开本窗口再运行本脚本。
    echo.
    pause
    exit /b 1
)

echo.
echo [2/4] 安装依赖库（requests）...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo  [错误] 依赖安装失败，请检查网络或换用国内镜像：
    echo         python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
    pause
    exit /b 1
)

echo.
echo [3/4] 安装打包工具 PyInstaller ...
python -m pip install pyinstaller
if errorlevel 1 (
    echo  [错误] PyInstaller 安装失败。
    pause
    exit /b 1
)

echo.
echo [4/4] 开始打包（第一次会比较慢，请耐心等）...
python -m PyInstaller --noconfirm --clean --onefile --noconsole ^
    --name "KingdeeCostTool" ^
    --paths ".." ^
    --collect-submodules kingdee_sdk ^
    app.py
if errorlevel 1 (
    echo  [错误] 打包失败，请把上面的报错内容发给管理员。
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  打包完成！
echo  产物：%~dp0dist\KingdeeCostTool.exe
echo  把这个 exe 拷给财务同事即可（可以改名成中文，比如 金蝶成本核算工具.exe）。
echo  提示：exe 需要在公司内网运行，才能访问金蝶服务器。
echo ============================================================
pause
