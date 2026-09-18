@echo off
chcp 65001 >nul
setlocal EnableExtensions
set "PORT=8765"
set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
set "LOG=%ROOT%backend\uvicorn.log"
cd /d "%ROOT%backend"

echo ============================================
echo  沪深股票分析启动中...
echo  目录: %ROOT%
echo ============================================

if not exist "%PY%" (
  echo [ERROR] 未找到虚拟环境:
  echo   %PY%
  echo 请在项目目录执行:
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

if not exist "%ROOT%backend\main.py" (
  echo [ERROR] 未找到 backend\main.py
  pause
  exit /b 1
)

rem 更稳妥的端口检测（避免中文 findstr 正则误判）
set "PORT_BUSY="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R /C:"TCP " ^| findstr /C:":%PORT% "') do set "PORT_BUSY=%%a"

if defined PORT_BUSY (
  echo [提示] 端口 %PORT% 已被 PID %PORT_BUSY% 占用。
  echo        若之前服务还开着，请直接访问:
  echo        http://127.0.0.1:%PORT%/
  echo        若要强制重启，请先结束该进程，再双击本脚本。
  start "" "http://127.0.0.1:%PORT%/"
  pause
  exit /b 0
)

echo [1/3] 启动 uvicorn (日志: %LOG%)
start "gupiao-uvicorn" /min "%PY%" -m uvicorn main:app --host 127.0.0.1 --port %PORT% > "%LOG%" 2>&1

echo [2/3] 等待服务就绪...
set /a WAITED=0
:WAIT_LOOP
timeout /t 1 /nobreak >nul
set /a WAITED+=1
powershell -NoProfile -Command "try { $r=Invoke-WebRequest -Uri 'http://127.0.0.1:8765/api/health' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } } catch { exit 1 }"
if not errorlevel 1 goto READY
if %WAITED% GEQ 20 goto FAILED
goto WAIT_LOOP

:READY
echo [3/3] 启动成功，打开浏览器...
start "" "http://127.0.0.1:%PORT%/"
echo.
echo 服务已在后台运行（最小化窗口 gupiao-uvicorn）。
echo 关闭该窗口或按本窗口任意键不会停止服务。
echo 停止服务：任务管理器结束 gupiao-uvicorn / 或关闭那个最小化窗口。
pause
exit /b 0

:FAILED
echo [ERROR] 20 秒内未能就绪。最近日志:
echo ----------------------------------------
powershell -NoProfile -Command "if (Test-Path '%LOG%') { Get-Content '%LOG%' -Tail 30 } else { Write-Host '无日志文件' }"
echo ----------------------------------------
echo 请把上方报错发给我，或检查是否被杀毒软件拦截。
pause
exit /b 1
