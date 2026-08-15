# 🔄 ProxyHub: Hệ thống Quản lý & Xoay Proxy Thông minh

ProxyHub là một ứng dụng full-stack mã nguồn mở giúp quản lý, kiểm tra sức khoẻ (health check) và tự động xoay (rotate) hàng loạt proxy. Hệ thống cung cấp một Dashboard trực quan để quản lý pool proxy và một API Gateway hiệu năng cao để forward traffic.

## ✨ Tính năng chính

- **🎯 Gateway xoay động:** Sử dụng **`proxy.py`** làm Gateway, tự động chọn proxy sống từ pool cho mỗi request.
- **🩺 Health Check Tự động:** Tích hợp **`Celery`** chạy nền để định kỳ kiểm tra độ trễ và tỷ lệ thành công của từng proxy.
- **📊 Dashboard Toàn diện:** Giao diện **`React`** đẹp mắt để quản lý proxy, xem thống kê và log request theo thời gian thực.
- **🗂️ Quản lý Pool/Nhóm:** Gom nhóm proxy theo quốc gia, ISP hoặc thẻ (tags) tùy chỉnh.
- **⚡ Cơ sở dữ liệu Nhẹ:** Sử dụng **`SQLite`** (đọc/ghi cực nhanh qua WAL mode), không cần cài đặt DB Server phức tạp.
- **🔒 Xác thực & Bảo mật:** Đăng nhập JWT, quản lý API token cho client.

## 🏗️ Kiến trúc Hệ thống

```mermaid
flowchart LR
    C[Client / Scraper] -->|HTTP/S Request| G[proxy.py Gateway<br/>:8899]
    G -->|Forward traffic| T[Target Website]
    G -->|Get alive proxy| B[FastAPI Backend<br/>:8000]

    R[React Dashboard<br/>:5173] -->|REST API / WebSocket| B
    B -->|CRUD / Logs| D[(SQLite DB)]

    CB[Celery Beat] -->|Trigger every 5 mins| CW[Celery Worker]
    CW -->|Test Proxy| P[Proxy Pool]
    CW -->|Update status / latency| D
    CW --> BR[(Redis)]
    B --> BR
    CB --> BR
```

### Luồng hoạt động chính

1. Client/Scraper gửi request tới **`proxy.py Gateway :8899`**.
2. Gateway gọi **FastAPI Backend :8000** để lấy một proxy đang hoạt động.
3. Gateway forward traffic tới **Target Website** thông qua proxy được chọn.
4. **React Dashboard :5173** giao tiếp với Backend thông qua REST API/WebSocket.
5. **Celery Beat** định kỳ kích hoạt **Celery Worker** để kiểm tra proxy.
6. Worker cập nhật trạng thái, latency và thông tin health check vào **SQLite**.
7. **Redis** được sử dụng làm broker/backend cho các tác vụ Celery.

## 🛠️ Công nghệ sử dụng

| Thành phần | Công nghệ | Mô tả |
|---|---|---|
| **Frontend** | React, Vite, TailwindCSS, ShadcnUI | Giao diện quản lý nhanh, hiện đại |
| **Backend API** | FastAPI, SQLModel, Pydantic | REST API hiệu năng cao, tự sinh docs |
| **Gateway** | proxy.py | Forward proxy server với custom plugin |
| **Task Queue** | Celery, Redis | Chạy background job health check |
| **Database** | SQLite (WAL mode) | Lưu trữ proxy, logs, users |

## 📋 Yêu cầu hệ thống (Prerequisites)

Trước khi bắt đầu, đảm bảo máy tính của bạn đã cài đặt:

- [**Python**](https://www.python.org/downloads/) >= 3.10
- [**Node.js**](https://nodejs.org/) >= 18.x
- [**Redis**](https://redis.io/docs/getting-started/installation/) (Dùng làm message broker cho Celery)

## 🚀 Cài đặt và Chạy thử (Development)

### 1. Clone repository

```bash
git clone https://github.com/your-username/proxyhub.git
cd proxyhub
```

### 2. Cài đặt Backend (FastAPI + Celery)

#### Tạo và kích hoạt môi trường ảo

**Linux/macOS:**

```bash
python -m venv venv
source venv/bin/activate
```

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### Cài đặt dependencies

```bash
pip install -r requirements.txt
```

#### Tạo file cấu hình

```bash
cp .env.example .env
```

> Trên Windows có thể copy file bằng `copy .env.example .env` trong Command Prompt.

#### Chạy API Server (Terminal 1)

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Truy cập API Docs tại: **`http://localhost:8000/docs`**

#### Chạy Celery Worker (Terminal 2)

Đảm bảo Redis đang chạy ở `localhost:6379`.

```bash
celery -A app.worker.celery_app worker --loglevel=info
```

#### Chạy Celery Beat Scheduler (Terminal 3)

```bash
celery -A app.worker.celery_app beat --loglevel=info
```

### 3. Cài đặt Frontend (React)

```bash
cd frontend
npm install
cp .env.example .env
```

#### Chạy Dashboard (Terminal 4)

```bash
npm run dev
```

Truy cập Dashboard tại: **`http://localhost:5173`**

### 4. Chạy Proxy Gateway (proxy.py)

Gateway sử dụng một plugin custom để gọi API lấy proxy và forward traffic.

#### Chạy Gateway (Terminal 5)

```bash
proxy --plugin-name app.gateway.RotateProxyPlugin \
    --hostname 0.0.0.0 \
    --port 8899
```

## ⚙️ Cấu hình (Environment Variables)

Tạo file **`.env`** ở thư mục gốc với các biến sau:

```env
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
```

> **Lưu ý bảo mật:** Không commit file `.env` chứa `SECRET_KEY` hoặc thông tin nhạy cảm lên Git repository.

## 📁 Cấu trúc thư mục dự án

```text
proxyhub/
├── app/                    # Backend FastAPI
│   ├── api/                # Các route REST API
│   ├── core/               # Cấu hình, bảo mật, database
│   ├── models/             # SQLModel database schemas
│   ├── schemas/            # Pydantic request/response schemas
│   ├── services/           # Business logic
│   ├── gateway/            # proxy.py Plugin (RotateProxyPlugin)
│   ├── worker.py           # Cấu hình Celery
│   └── main.py             # FastAPI app entry point
├── frontend/               # React App
│   ├── src/
│   │   ├── components/     # UI Components
│   │   ├── pages/          # Dashboard, Proxies, Settings...
│   │   ├── api/            # Axios clients
│   │   └── App.tsx
│   └── package.json
├── requirements.txt
└── README.md
```

## 📖 Cách sử dụng

### 1. Thêm Proxy vào Pool

Vào Dashboard → **`Proxies`** → **`Import`**.

Hỗ trợ nhập text dạng:

```text
http://user:pass@1.2.3.4:8080
socks5://5.6.7.8:1080
```

### 2. Cấu hình phần mềm của bạn

Trỏ phần mềm scraping/automation của bạn vào Gateway. ProxyHub sẽ tự động xoay IP cho mỗi request:

```bash
curl -x http://localhost:8899 http://httpbin.org/ip
```

Kết quả trả về sẽ là IP của proxy trong pool và IP này sẽ thay đổi ở request tiếp theo.

### 3. Health Check

Vào **`Settings`** → cấu hình URL kiểm tra (ví dụ: **`http://httpbin.org/ip`**) và khoảng thời gian (ví dụ: 5 phút).

Celery worker sẽ tự động test và đánh dấu proxy **`alive`** hoặc **`dead`**. Gateway chỉ chọn proxy **`alive`**.

## 🧠 Logic xoay Proxy (Gateway Plugin)

Plugin **`RotateProxyPlugin`** kế thừa từ **`HttpProxyBasePlugin`** của `proxy.py`. Mỗi khi có request tới:

1. Plugin gọi tới internal API **`GET /internal/proxies?strategy=random`** của FastAPI.
2. FastAPI query SQLite để lấy một proxy đang **`alive`** và trả về URL.
3. Plugin thiết lập kết nối upstream tới proxy đó.
4. Traffic được forward theo luồng **client → upstream proxy → target**.

> **Tối ưu hiệu năng:** FastAPI có thể cache danh sách proxy `alive` trong Redis và cập nhật mỗi 10 giây, giúp Gateway không phải query DB liên tục.

## 🗺️ Lộ trình phát triển (Roadmap)

- [ ] MVP: CRUD Proxy, Manual Rotate, SQLite
- [ ] Celery Health Check tự động
- [ ] Multi-tenant: Gán User/API Key vào Pool riêng biệt
- [ ] Sticky Session: Giữ nguyên IP cho một `session_id` trong N phút
- [ ] WebSocket Realtime Logs: Xem log request chạy trên Dashboard
- [ ] Docker Compose: Một lệnh **`docker compose up`** chạy toàn bộ hệ thống

## 🤝 Đóng góp

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

## 📄 License

Distributed under the MIT License. See **`LICENSE`** for more information.
