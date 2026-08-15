# 🔄 ProxyHub: Hệ thống Quản lý & Xoay Proxy Thông minh

> ⚠️ **Trạng thái:** Dự án đang trong giai đoạn phát triển ban đầu (WIP) — hiện mới có tài liệu thiết kế, code sẽ được bổ sung dần theo [Roadmap](#-lộ-trình-phát-triển-roadmap).

ProxyHub là một ứng dụng full-stack mã nguồn mở giúp quản lý, kiểm tra sức khoẻ (health check) và tự động xoay (rotate) hàng loạt proxy. Hệ thống cung cấp một Dashboard trực quan để quản lý pool proxy và một API Gateway hiệu năng cao để forward traffic.

## 📸 Screenshots

> _(Sẽ bổ sung khi Dashboard hoàn thiện)_

## 📑 Mục lục

- [✨ Tính năng chính](#-tính-năng-chính)
- [🏗️ Kiến trúc Hệ thống](#️-kiến-trúc-hệ-thống)
- [🛠️ Công nghệ sử dụng](#️-công-nghệ-sử-dụng)
- [📋 Yêu cầu hệ thống](#-yêu-cầu-hệ-thống-prerequisites)
- [🚀 Cài đặt và Chạy thử](#-cài-đặt-và-chạy-thử-development)
- [⚙️ Cấu hình](#️-cấu-hình-environment-variables)
- [👤 Tạo tài khoản đầu tiên](#-tạo-tài-khoản-đầu-tiên)
- [📖 Cách sử dụng](#-cách-sử-dụng)
- [🧠 Logic xoay Proxy](#-logic-xoay-proxy-gateway-plugin)
- [🔒 Lưu ý bảo mật](#-lưu-ý-bảo-mật)
- [🩹 Troubleshooting](#-troubleshooting)
- [🗺️ Roadmap](#️-lộ-trình-phát-triển-roadmap)
- [🤝 Đóng góp](#-đóng-góp)
- [📄 License](#-license)

## ✨ Tính năng chính

Các tính năng mục tiêu của dự án:

- **🎯 Gateway xoay động:** Sử dụng **`proxy.py`** làm Gateway, tự động chọn proxy sống từ pool cho mỗi request.
- **🩺 Health Check Tự động:** Tích hợp **`Celery`** chạy nền để định kỳ kiểm tra độ trễ và tỷ lệ thành công của từng proxy.
- **📊 Dashboard Toàn diện:** Giao diện **`React`** để quản lý proxy, xem thống kê và log request theo thời gian thực.
- **🗂️ Quản lý Pool/Nhóm:** Gom nhóm proxy theo quốc gia, ISP hoặc thẻ (tags) tùy chỉnh.
- **⚡ Cơ sở dữ liệu Nhẹ:** Sử dụng **`SQLite`** (đọc/ghi qua WAL mode), không cần cài đặt DB Server phức tạp.
- **🔒 Xác thực & Bảo mật:** Đăng nhập JWT, quản lý API token cho client.

> Tiến độ thực tế của từng tính năng được theo dõi tại phần [Roadmap](#️-lộ-trình-phát-triển-roadmap).

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

### Bảng cổng dịch vụ (Ports)

| Dịch vụ              | Cổng  | Ghi chú                                    |
| -------------------- | ----- | ------------------------------------------ |
| FastAPI Backend      | 8000  | REST API + Swagger docs tại `/docs`        |
| React Dashboard      | 5173  | Vite dev server                            |
| proxy.py Gateway     | 8899  | Cổng proxy để client trỏ vào               |
| Redis                | 6379  | Broker/backend cho Celery                  |

### Luồng hoạt động chính

1. Client/Scraper gửi request tới **`proxy.py Gateway :8899`**.
2. Gateway gọi **FastAPI Backend :8000** để lấy một proxy đang hoạt động.
3. Gateway forward traffic tới **Target Website** thông qua proxy được chọn.
4. **React Dashboard :5173** giao tiếp với Backend thông qua REST API/WebSocket.
5. **Celery Beat** định kỳ kích hoạt **Celery Worker** để kiểm tra proxy.
6. Worker cập nhật trạng thái, latency và thông tin health check vào **SQLite**.
7. **Redis** được sử dụng làm broker/backend cho các tác vụ Celery.

## 🛠️ Công nghệ sử dụng

| Thành phần      | Công nghệ                          | Mô tả                                  |
| --------------- | ---------------------------------- | -------------------------------------- |
| **Frontend**    | React, Vite, TailwindCSS, ShadcnUI | Giao diện quản lý nhanh, hiện đại      |
| **Backend API** | FastAPI, SQLModel, Pydantic        | REST API hiệu năng cao, tự sinh docs   |
| **Gateway**     | proxy.py                           | Forward proxy server với custom plugin |
| **Task Queue**  | Celery, Redis                      | Chạy background job health check       |
| **Database**    | SQLite (WAL mode)                  | Lưu trữ proxy, logs, users             |

## 📋 Yêu cầu hệ thống (Prerequisites)

Trước khi bắt đầu, đảm bảo máy tính của bạn đã cài đặt:

- [**Python**](https://www.python.org/downloads/) >= 3.10
- [**Node.js**](https://nodejs.org/) >= 18.x
- [**Redis**](https://redis.io/docs/getting-started/installation/) (Dùng làm message broker cho Celery)

> ⚠️ **Lưu ý cho Windows:** Celery **không hỗ trợ chính thức trên Windows**. Khi chạy worker/beat trên Windows, cần dùng pool thay thế (`--pool=solo` hoặc `--pool=gevent`) — xem hướng dẫn ở bước chạy Celery bên dưới. Cách ổn định nhất là chạy qua **WSL2** hoặc **Docker**.

## 🚀 Cài đặt và Chạy thử (Development)

> 🚧 Vì dự án đang ở giai đoạn WIP, một số file được tham chiếu dưới đây (`requirements.txt`, `.env.example`, `app/`, `frontend/`) sẽ xuất hiện dần trong repo. Nếu lệnh nào báo thiếu file, nghĩa là phần đó chưa được implement.

### 1. Clone repository

```bash
git clone https://github.com/ngotuananh101/proxyhub.git
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

> Trên Windows có thể dùng `copy .env.example .env` trong Command Prompt. Nội dung các biến môi trường xem tại phần [Cấu hình](#️-cấu-hình-environment-variables).

#### Chạy API Server (Terminal 1)

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Truy cập API Docs tại: **`http://localhost:8000/docs`**

> Khi develop chỉ nên bind `127.0.0.1`. Chỉ dùng `0.0.0.0` khi bạn hiểu rõ rủi ro và đã cấu hình firewall — xem phần [Lưu ý bảo mật](#-lưu-ý-bảo-mật).

#### Chạy Celery Worker (Terminal 2)

Đảm bảo Redis đang chạy ở `localhost:6379`.

**Linux/macOS:**

```bash
celery -A app.worker.celery_app worker --loglevel=info
```

**Windows** (Celery không hỗ trợ chính thức, cần chỉ định pool):

```bash
celery -A app.worker.celery_app worker --loglevel=info --pool=solo
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

File `.env` của frontend cần tối thiểu biến trỏ về Backend:

```env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
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
    --hostname 127.0.0.1 \
    --port 8899
```

## ⚙️ Cấu hình (Environment Variables)

File **`.env`** ở thư mục gốc gồm các biến sau:

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
# Key nội bộ để Gateway xác thực khi gọi internal API của Backend
INTERNAL_API_KEY=change_me_internal_key
```

> **Lưu ý bảo mật:** Không commit file `.env` chứa `SECRET_KEY` hoặc thông tin nhạy cảm lên Git repository.

## 👤 Tạo tài khoản đầu tiên

Dashboard yêu cầu đăng nhập JWT. Sau khi chạy Backend lần đầu, tạo tài khoản admin qua CLI:

```bash
python -m app.cli create-admin --username admin --email admin@example.com --password <password-cua-ban>
```

Sau đó đăng nhập tại **`http://localhost:5173`**.

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

Vào **`Settings`** → cấu hình URL kiểm tra và khoảng thời gian (ví dụ: 5 phút).

> `httpbin.org` đôi khi chậm/không ổn định. Có thể dùng endpoint thay thế nhẹ hơn như `http://api.ipify.org` hoặc một URL tĩnh do bạn tự host.

Celery worker sẽ tự động test và đánh dấu proxy **`alive`** hoặc **`dead`**. Gateway chỉ chọn proxy **`alive`**.

## 🧠 Logic xoay Proxy (Gateway Plugin)

Plugin **`RotateProxyPlugin`** kế thừa từ **`HttpProxyBasePlugin`** của `proxy.py`. Mỗi khi có request tới:

1. Plugin gọi tới internal API **`GET /internal/proxies?strategy=random`** của FastAPI (kèm header `X-Internal-Key`).
2. FastAPI query SQLite để lấy một proxy đang **`alive`** và trả về URL.
3. Plugin thiết lập kết nối upstream tới proxy đó.
4. Traffic được forward theo luồng **client → upstream proxy → target**.

> **Tối ưu hiệu năng:** FastAPI có thể cache danh sách proxy `alive` trong Redis và cập nhật mỗi 10 giây, giúp Gateway không phải query DB liên tục.

## 🔒 Lưu ý bảo mật

- **Bind localhost khi dev:** Backend và Gateway mặc định chỉ nên lắng nghe `127.0.0.1`. Chỉ expose `0.0.0.0` khi deploy sau reverse proxy/firewall.
- **Internal API phải có key:** Endpoint `/internal/proxies` trả về URL proxy **kèm credential (user:pass)**, nên bắt buộc xác thực bằng `INTERNAL_API_KEY` (header `X-Internal-Key`). Không expose endpoint này ra internet.
- **Đổi `SECRET_KEY`:** Luôn tạo `SECRET_KEY` ngẫu nhiên, không dùng giá trị mặc định trong `.env.example`.
- **Không commit `.env`:** Đảm bảo `.env` nằm trong `.gitignore`.

## 🩹 Troubleshooting

| Vấn đề                                        | Nguyên nhân / Cách xử lý                                                                                                     |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Celery worker crash trên Windows              | Celery không hỗ trợ Windows với pool mặc định. Chạy thêm `--pool=solo` (hoặc `--pool=gevent`), tốt nhất dùng WSL2/Docker.    |
| `ConnectionError: redis://localhost:6379`     | Redis chưa chạy. Khởi động Redis (`redis-server`) hoặc kiểm tra lại `REDIS_URL`.                                             |
| Port 8899/8000 đã được sử dụng                | Trùng port với ứng dụng khác. Đổi port bằng flag `--port` hoặc kiểm tra process đang chiếm port.                             |
| `database is locked` (SQLite)                 | FastAPI và Celery worker ghi đồng thời. Đảm bảo đã bật **WAL mode** và set `busy_timeout` (mặc định trong cấu hình DB).      |
| Gateway trả lỗi nhưng Dashboard vẫn hiện proxy alive | Health check chưa chạy kịp chu kỳ. Kiểm tra log Celery Beat/Worker, hoặc trigger health check thủ công từ Dashboard.  |

## 🗺️ Lộ trình phát triển (Roadmap)

- [ ] MVP: CRUD Proxy, Manual Rotate, SQLite
- [ ] Celery Health Check tự động
- [ ] Multi-tenant: Gán User/API Key vào Pool riêng biệt
- [ ] Sticky Session: Giữ nguyên IP cho một `session_id` trong N phút
- [ ] WebSocket Realtime Logs: Xem log request chạy trên Dashboard
- [ ] Docker Compose: Một lệnh **`docker compose up`** chạy toàn bộ hệ thống

## 🤝 Đóng góp

Mọi pull request đều được chào đón! Với các thay đổi lớn, hãy mở issue trước để thảo luận về hướng thay đổi.

## 📄 License

Phân phối theo giấy phép MIT. Xem file **`LICENSE`** để biết thêm chi tiết.
