@echo off
chcp 65001 >nul
setlocal
set "PORT=8765"
cd /d "%~dp0backend"

if not exist "%~dp0.venv\Scripts\python.exe" (
  echo [ERROR] 未找到虚拟环境，请先安装依赖：
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

rem 端口占用检测：给出明确提示，避免 uvicorn 报错一闪而过
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo [提示] 端口 %PORT% 已被占用，服务可能已在运行。
  echo        浏览器直接打开 http://127.0.0.1:%PORT% 即可；
  echo        若需重启，请先结束占用该端口的 python.exe。
  start "" "http://127.0.0.1:%PORT%"
  pause
  exit /b 0
)

echo 启动沪深股票分析：http://127.0.0.1:%PORT%
rem 延迟 2 秒等服务起来后自动打开浏览器
start "" /b cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:%PORT%"
"%~dp0.venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port %PORT%
echo.
echo [已停止] 若上方有报错信息，请查看后排查。
pause
endlocal
