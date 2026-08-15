🔄 ProxyHub: Hệ thống Quản lý & Xoay Proxy Thông minh
ProxyHub là một ứng dụng full-stack mã nguồn mở giúp quản lý, kiểm tra sức khoẻ (health check) và tự động xoay (rotate) hàng loạt proxy. Hệ thống cung cấp một Dashboard trực quan để quản lý pool proxy và một API Gateway hiệu năng cao để forward traffic.

✨ Tính năng chính
🎯 Gateway xoay động: Sử dụng proxy.py làm Gateway, tự động chọn proxy sống từ pool cho mỗi request.
🩺 Health Check Tự động: Tích hợp Celery chạy nền để định kỳ kiểm tra độ trễ và tỷ lệ thành công của từng proxy.
📊 Dashboard Toàn diện: Giao diện React đẹp mắt để quản lý proxy, xem thống kê, log request theo thời gian thực.
🗂️ Quản lý Pool/Nhóm: Gom nhóm proxy theo quốc gia, ISP, hoặc thẻ (tags) tùy chỉnh.
⚡ Cơ sở dữ liệu Nhẹ: Sử dụng SQLite (đọc/ghi cực nhanh qua WAL mode), không cần cài đặt DB Server phức tạp.
🔒 Xác thực & Bảo mật: Đăng nhập JWT, quản lý API token cho client.
🏗️ Kiến trúc Hệ thống
HTTP/S Request

Unsupported markdown: list
Unsupported markdown: list
Unsupported markdown: list
REST API / WebSocket

CRUD / Logs

Trigger every 5 mins

Test Proxy

Update status / latency

Broker

Client / Scraper

proxy.py Gateway :8899

FastAPI Backend :8000

Target Website

React Dashboard :3000

SQLite DB

Celery Beat

Celery Worker

Redis

🛠️ Công nghệ sử dụng
Thành phần
Công nghệ
Mô tả
Frontend React, Vite, TailwindCSS, ShadcnUI Giao diện quản lý nhanh, hiện đại
Backend API FastAPI, SQLModel, Pydantic REST API hiệu năng cao, tự sinh docs
Gateway proxy.py Forward proxy server with custom plugin
Task Queue Celery, Redis Chạy background job health check
Database SQLite (WAL mode) Lưu trữ proxy, logs, users

📋 Yêu cầu hệ thống (Prerequisites)
Trước khi bắt đầu, đảm bảo máy tính của bạn đã cài đặt:

Python >= 3.10
Node.js >= 18.x
Redis (Dùng làm message broker cho Celery)
🚀 Cài đặt và Chạy thử (Development)

1. Clone repository
   bash

git clone https://github.com/your-username/proxyhub.git
cd proxyhub 2. Cài đặt Backend (FastAPI + Celery)
bash

# Tạo và kích hoạt môi trường ảo

python -m venv venv
source venv/bin/activate # Linux/macOS

# venv\Scripts\activate # Windows

# Cài đặt dependencies

pip install -r requirements.txt

# Tạo file cấu hình

cp .env.example .env
Chạy API Server (Terminal 1):

bash

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
Truy cập API Docs tại: http://localhost:8000/docs

Chạy Celery Worker (Terminal 2):

bash

# Đảm bảo Redis đang chạy ở localhost:6379

celery -A app.worker.celery_app worker --loglevel=info
Chạy Celery Beat Scheduler (Terminal 3):

bash

celery -A app.worker.celery_app beat --loglevel=info 3. Cài đặt Frontend (React)
bash

cd frontend
npm install
cp .env.example .env
Chạy Dashboard (Terminal 4):

bash

npm run dev
Truy cập Dashboard tại: http://localhost:5173

4. Chạy Proxy Gateway (proxy.py)
   Gateway sử dụng một plugin custom để gọi API lấy proxy và forward traffic.

Chạy Gateway (Terminal 5):

bash

proxy --plugin-name app.gateway.RotateProxyPlugin \
 --hostname 0.0.0.0 \
 --port 8899
⚙️ Cấu hình (Environment Variables)
Tạo file .env ở thư mục gốc với các biến sau:

env

# Database

DATABASE_URL=sqlite:///./proxyhub.db

# Redis (Cho Celery)

REDIS_URL=redis://localhost:6379/0

# JWT Auth

SECRET_KEY=your_super_secret_key_change_me
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Celery

CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# Gateway

GATEWAY_API_URL=http://localhost:8000/internal/proxies
📁 Cấu trúc thư mục dự án
text

proxyhub/
├── app/ # Backend FastAPI
│ ├── api/ # Các route REST API
│ ├── core/ # Cấu hình, bảo mật, database
│ ├── models/ # SQLModel database schemas
│ ├── schemas/ # Pydantic request/response schemas
│ ├── services/ # Business logic
│ ├── gateway/ # proxy.py Plugin (RotateProxyPlugin)
│ ├── worker.py # Cấu hình Celery
│ └── main.py # FastAPI app entry point
├── frontend/ # React App
│ ├── src/
│ │ ├── components/ # UI Components
│ │ ├── pages/ # Dashboard, Proxies, Settings...
│ │ ├── api/ # Axios clients
│ │ └── App.tsx
│ └── package.json
├── requirements.txt
└── README.md
📖 Cách sử dụng

1. Thêm Proxy vào Pool
   Vào Dashboard -> Proxies -> Import. Hỗ trợ nhập text dạng:

text

http://user:pass@1.2.3.4:8080
socks5://5.6.7.8:1080 2. Cấu hình phần mềm của bạn
Trỏ phần mềm scraping/automation của bạn vào Gateway. ProxyHub sẽ tự động xoay IP cho mỗi request:

bash

curl -x http://localhost:8899 http://httpbin.org/ip
Kết quả trả về sẽ là IP của proxy trong pool, và IP này sẽ thay đổi ở request tiếp theo.

3. Health Check
   Vào Settings -> Cấu hình URL kiểm tra (vd: http://httpbin.org/ip) và khoảng thời gian (vd: 5 phút).
   Celery worker sẽ tự động test và đánh dấu proxy alive hoặc dead. Gateway chỉ chọn proxy alive.

🧠 Logic xoay Proxy (Gateway Plugin)
Plugin RotateProxyPlugin kế thừa từ HttpProxyBasePlugin của proxy.py. Mỗi khi có request tới:

Plugin gọi tới internal API GET /internal/proxies?strategy=random của FastAPI.
FastAPI query SQLite lấy 1 proxy đang alive, trả về URL.
Plugin thiết lập kết nối upstream tới proxy đó.
Forward traffic client <-> upstream proxy <-> target.
(Để tối ưu hiệu năng, FastAPI có thể cache list proxy alive trong Redis cập nhật mỗi 10s, giúp Gateway không phải query DB liên tục).

🗺️ Lộ trình phát triển (Roadmap)
MVP: CRUD Proxy, Manual Rotate, SQLite
Celery Health Check tự động
Multi-tenant: Gán User/API Key vào Pool riêng biệt
Sticky Session: Giữ nguyên IP cho 1 session_id trong N phút
WebSocket Realtime Logs: Xem log request chạy trên Dashboard
Docker Compose: 1 lệnh docker compose up chạy toàn bộ hệ thống
🤝 Đóng góp
Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

📄 License
Distributed under the MIT License. See LICENSE for more information.

Gửi cho tôi file

Thought Process
Vì tôi là trợ lý AI, tôi không thể gửi trực tiếp tệp tin đính kèm (file vật lý) qua khung chat này. Tuy nhiên, tôi đã đóng gói toàn bộ nội dung README vào khung mã dưới đây.

Bạn chỉ cần copy toàn bộ nội dung trong khung, mở trình soạn thảo (như VS Code, Notepad,...), dán vào và lưu lại với tên README.md ở thư mục gốc của dự án là xong.

🔄 ProxyHub: Hệ thống Quản lý & Xoay Proxy Thông minh
ProxyHub là một ứng dụng full-stack mã nguồn mở giúp quản lý, kiểm tra sức khoẻ (health check) và tự động xoay (rotate) hàng loạt proxy. Hệ thống cung cấp một Dashboard trực quan để quản lý pool proxy và một API Gateway hiệu năng cao để forward traffic.

✨ Tính năng chính
🎯 Gateway xoay động: Sử dụng proxy.py làm Gateway, tự động chọn proxy sống từ pool cho mỗi request.
🩺 Health Check Tự động: Tích hợp Celery chạy nền để định kỳ kiểm tra độ trễ và tỷ lệ thành công của từng proxy.
📊 Dashboard Toàn diện: Giao diện React đẹp mắt để quản lý proxy, xem thống kê, log request theo thời gian thực.
🗂️ Quản lý Pool/Nhóm: Gom nhóm proxy theo quốc gia, ISP, hoặc thẻ (tags) tùy chỉnh.
⚡ Cơ sở dữ liệu Nhẹ: Sử dụng SQLite (đọc/ghi cực nhanh qua WAL mode), không cần cài đặt DB Server phức tạp.
🔒 Xác thực & Bảo mật: Đăng nhập JWT, quản lý API token cho client.
🏗️ Kiến trúc Hệ thống
graph TD Client[Client / Scraper] -->|HTTP/S Request| Gateway[proxy.py Gateway :8899] Gateway -->|1. Query active proxy| API[FastAPI Backend :8000] API -->|2. Return Proxy URL| Gateway Gateway -->|3. Forward Traffic| Target[Target Website] Dashboard[React Dashboard :3000] -->|REST API / WebSocket| API API -->|CRUD / Logs| DB[(SQLite DB)] Scheduler[Celery Beat] -->|Trigger every 5 mins| Worker[Celery Worker] Worker -->|Test Proxy| Target Worker -->|Update status / latency| DB Worker -->|Broker| Redis[(Redis)]
🛠️ Công nghệ sử dụng
Thành phần
Công nghệ
Mô tả
Frontend React, Vite, TailwindCSS, ShadcnUI Giao diện quản lý nhanh, hiện đại
Backend API FastAPI, SQLModel, Pydantic REST API hiệu năng cao, tự sinh docs
Gateway proxy.py Forward proxy server with custom plugin
Task Queue Celery, Redis Chạy background job health check
Database SQLite (WAL mode) Lưu trữ proxy, logs, users

📋 Yêu cầu hệ thống (Prerequisites)
Trước khi bắt đầu, đảm bảo máy tính của bạn đã cài đặt:

Python >= 3.10
Node.js >= 18.x
Redis (Dùng làm message broker cho Celery)
🚀 Cài đặt và Chạy thử (Development)

1. Clone repository
   bash

git clone https://github.com/your-username/proxyhub.git
cd proxyhub 2. Cài đặt Backend (FastAPI + Celery)
bash

# Tạo và kích hoạt môi trường ảo

python -m venv venv
source venv/bin/activate # Linux/macOS

# venv\Scripts\activate # Windows

# Cài đặt dependencies

pip install -r requirements.txt

# Tạo file cấu hình

cp .env.example .env
Chạy API Server (Terminal 1):

bash

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
Truy cập API Docs tại: http://localhost:8000/docs

Chạy Celery Worker (Terminal 2):

bash

# Đảm bảo Redis đang chạy ở localhost:6379

celery -A app.worker.celery_app worker --loglevel=info
Chạy Celery Beat Scheduler (Terminal 3):

bash

celery -A app.worker.celery_app beat --loglevel=info 3. Cài đặt Frontend (React)
bash

cd frontend
npm install
cp .env.example .env
Chạy Dashboard (Terminal 4):

bash

npm run dev
Truy cập Dashboard tại: http://localhost:5173

4. Chạy Proxy Gateway (proxy.py)
   Gateway sử dụng một plugin custom để gọi API lấy proxy và forward traffic.

Chạy Gateway (Terminal 5):

bash

proxy --plugin-name app.gateway.RotateProxyPlugin \
 --hostname 0.0.0.0 \
 --port 8899
⚙️ Cấu hình (Environment Variables)
Tạo file .env ở thư mục gốc với các biến sau:

env

# Database

DATABASE_URL=sqlite:///./proxyhub.db

# Redis (Cho Celery)

REDIS_URL=redis://localhost:6379/0

# JWT Auth

SECRET_KEY=your_super_secret_key_change_me
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Celery

CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# Gateway

GATEWAY_API_URL=http://localhost:8000/internal/proxies
📁 Cấu trúc thư mục dự án
text

proxyhub/
├── app/ # Backend FastAPI
│ ├── api/ # Các route REST API
│ ├── core/ # Cấu hình, bảo mật, database
│ ├── models/ # SQLModel database schemas
│ ├── schemas/ # Pydantic request/response schemas
│ ├── services/ # Business logic
│ ├── gateway/ # proxy.py Plugin (RotateProxyPlugin)
│ ├── worker.py # Cấu hình Celery
│ └── main.py # FastAPI app entry point
├── frontend/ # React App
│ ├── src/
│ │ ├── components/ # UI Components
│ │ ├── pages/ # Dashboard, Proxies, Settings...
│ │ ├── api/ # Axios clients
│ │ └── App.tsx
│ └── package.json
├── requirements.txt
└── README.md
📖 Cách sử dụng

1. Thêm Proxy vào Pool
   Vào Dashboard -> Proxies -> Import. Hỗ trợ nhập text dạng:

text

http://user:pass@1.2.3.4:8080
socks5://5.6.7.8:1080 2. Cấu hình phần mềm của bạn
Trỏ phần mềm scraping/automation của bạn vào Gateway. ProxyHub sẽ tự động xoay IP cho mỗi request:

bash

curl -x http://localhost:8899 http://httpbin.org/ip
Kết quả trả về sẽ là IP của proxy trong pool, và IP này sẽ thay đổi ở request tiếp theo.

3. Health Check
   Vào Settings -> Cấu hình URL kiểm tra (vd: http://httpbin.org/ip) và khoảng thời gian (vd: 5 phút).
   Celery worker sẽ tự động test và đánh dấu proxy alive hoặc dead. Gateway chỉ chọn proxy alive.

🧠 Logic xoay Proxy (Gateway Plugin)
Plugin RotateProxyPlugin kế thừa từ HttpProxyBasePlugin của proxy.py. Mỗi khi có request tới:

Plugin gọi tới internal API GET /internal/proxies?strategy=random của FastAPI.
FastAPI query SQLite lấy 1 proxy đang alive, trả về URL.
Plugin thiết lập kết nối upstream tới proxy đó.
Forward traffic client <-> upstream proxy <-> target.
(Để tối ưu hiệu năng, FastAPI có thể cache list proxy alive trong Redis cập nhật mỗi 10s, giúp Gateway không phải query DB liên tục).

🗺️ Lộ trình phát triển (Roadmap)
MVP: CRUD Proxy, Manual Rotate, SQLite
Celery Health Check tự động
Multi-tenant: Gán User/API Key vào Pool riêng biệt
Sticky Session: Giữ nguyên IP cho 1 session_id trong N phút
WebSocket Realtime Logs: Xem log request chạy trên Dashboard
Docker Compose: 1 lệnh docker compose up chạy toàn bộ hệ thống
🤝 Đóng góp
Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

📄 License
Distributed under the MIT License. See LICENSE for more information.
