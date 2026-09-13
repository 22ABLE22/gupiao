@echo off
chcp 65001 >nul
cd /d "%~dp0backend"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo [ERROR] 未找到虚拟环境，请先安装依赖：
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)
echo 启动沪深股票分析：http://127.0.0.1:8765
"%~dp0.venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8765
