@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================
echo   ProxyHub - Khoi dong Backend + Frontend + Gateway + Celery
echo ============================================

REM --- Kiem tra .env ---
if not exist .env (
    echo [!] Chua co file .env - tao tu .env.example ...
    copy .env.example .env >nul
    echo [!] Da tao .env. Hay doi SECRET_KEY va INTERNAL_API_KEY truoc khi dung that!
)

REM --- Kiem tra frontend/.env ---
if not exist frontend\.env (
    echo [*] Tao frontend\.env tu frontend\.env.example ...
    copy frontend\.env.example frontend\.env >nul
)

REM --- Kiem tra venv ---
if not exist venv\Scripts\python.exe (
    echo [LOI] Chua co venv. Chay truoc:
    echo     python -m venv venv
    echo     venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

REM --- Kiem tra node_modules ---
if not exist frontend\node_modules (
    echo [*] Chua co frontend\node_modules - chay npm install lan dau, co the mat vai phut ...
    pushd frontend
    call npm install
    popd
)

REM --- Chua co DB Postgres thi nhac tao tai khoan ---
echo [!] Neu database Postgres con trong, tao tai khoan dau tien bang:
echo     venv\Scripts\python -m app.cli create-admin --username admin --email a@b.c --password ^<password^>

REM --- Read GATEWAY_API_URL, GATEWAY_LOG_URL and INTERNAL_API_KEY from .env (CRLF-tolerant) ---
for /f "usebackq delims=" %%v in (`powershell -NoProfile -Command "$l=@(Get-Content .env | Where-Object {$_ -like 'INTERNAL_API_KEY=*'}); if($l){($l[0] -split '=',2)[1]} else {''}"`) do set "INTERNAL_API_KEY=%%v"
for /f "usebackq delims=" %%v in (`powershell -NoProfile -Command "$l=@(Get-Content .env | Where-Object {$_ -like 'GATEWAY_API_URL=*'}); if($l){($l[0] -split '=',2)[1]} else {'http://localhost:8000/internal/proxies'}"`) do set "GATEWAY_API_URL=%%v"
for /f "usebackq delims=" %%v in (`powershell -NoProfile -Command "$l=@(Get-Content .env | Where-Object {$_ -like 'GATEWAY_LOG_URL=*'}); if($l){($l[0] -split '=',2)[1]} else {'http://localhost:8000/internal/logs'}"`) do set "GATEWAY_LOG_URL=%%v"

echo ============================================
echo   Backend : http://localhost:8000  (API docs: /docs)
echo   Frontend: http://localhost:5173
echo   Gateway : 127.0.0.1:8899  (curl -x http://127.0.0.1:8899 http://httpbin.org/ip)
echo   Celery  : worker + beat (health check moi 5 phut)
echo   Tat ca chay trong 1 cua so nay (Ctrl+C de dung het)
echo ============================================

REM --- Chay tat ca tien trinh trong 1 cua so voi concurrently ---
REM Dung "python -m proxy" thay vi proxy.exe: console script khong them cwd vao
REM sys.path nen khong import duoc app.gateway.plugin tu thu muc project.
npx concurrently -c "blue,green,magenta,cyan,yellow" -n "Backend,Frontend,Gateway,Worker,Beat" ^
  "venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000" ^
  "cd frontend && npm run dev" ^
  "venv\Scripts\python.exe -m proxy --plugins app.gateway.plugin.RotateProxyPlugin --hostname 127.0.0.1 --port 8899" ^
  "venv\Scripts\celery.exe -A app.worker.celery_app worker --loglevel=info --pool=threads --concurrency=8" ^
  "venv\Scripts\celery.exe -A app.worker.celery_app beat --loglevel=info"

endlocal
