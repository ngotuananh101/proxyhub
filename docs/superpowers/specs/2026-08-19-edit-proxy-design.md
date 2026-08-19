# Edit Proxy — Design Spec

**Date:** 2026-08-19
**Status:** Draft
**Approach:** Hướng A — `EditProxyDialog` riêng biệt

## Summary

Thêm khả năng chỉnh sửa proxy từ bảng Proxies thông qua dialog. User nhấn icon Edit (✏️) trên mỗi row để mở dialog pre-fill dữ liệu hiện tại, sửa xong nhấn Save.

## Scope

- Sửa tất cả fields: scheme, host, port, username, password, status
- UI trigger: icon Edit cạnh icon Delete trên mỗi row
- Backend: mở rộng `ProxyUpdate` schema, thêm validation

## Backend

### Schema — `app/schemas/proxy.py`

Mở rộng `ProxyUpdate` thêm 2 field optional:

```python
class ProxyUpdate(BaseModel):
    scheme: str | None = None
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    status: str | None = None
```

### API — `app/api/proxies.py`

Endpoint `PUT /api/proxies/{proxy_id}` đã tồn tại. Cần bổ sung logic:

1. **Validate `scheme`** nếu có: chỉ chấp nhận `"http"` hoặc `"https"` → 422
2. **Validate `status`** nếu có: chỉ chấp nhận `"alive"`, `"dead"`, `"unknown"` → 422, chuyển thành `ProxyStatus` enum trước khi set
3. **Validate `port`** nếu có: 1–65535 → 422
4. **Unique constraint check**: khi scheme/host/port thay đổi → query DB kiểm tra combo mới có trùng proxy khác không (loại trừ `proxy_id` đang edit) → 409 "Proxy already exists"
5. **Cập nhật `updated_at`** = `datetime.now(timezone.utc)`

## Frontend

### API client — `frontend/src/api/proxies.ts`

Thêm hàm:

```typescript
export async function updateProxy(
  id: number,
  data: {
    scheme?: string
    host?: string
    port?: number
    username?: string | null
    password?: string | null
    status?: string
  },
): Promise<ProxyItem> {
  const res = await client.put(`/api/proxies/${id}`, data)
  return res.data
}
```

### EditProxyDialog — `frontend/src/components/proxies/EditProxyDialog.tsx`

File mới, pattern giống `AddProxyDialog`:

- **Props:** `proxy: ProxyItem | null`, `onOpenChange: (open: boolean) => void`, `onUpdated: () => void`
- **Dialog mở** khi `proxy !== null`
- **Pre-fill** tất cả fields từ `proxy` khi mở (reset state mỗi lần proxy thay đổi)
- **6 fields:**
  - Scheme — Select dropdown (http / https)
  - Host — Input text, required
  - Port — Input number, min=1 max=65535, required
  - Username — Input text, optional
  - Password — Input password, optional
  - Status — Select dropdown (alive / dead / unknown)
- **Submit:** gọi `updateProxy(proxy.id, data)`
- **Success:** toast "Proxy updated", gọi `onUpdated()`, đóng dialog
- **Error 409:** hiển thị "Proxy already exists" ở field Host
- **Error 404:** toast "Proxy not found"
- **Error khác:** hiển thị message từ server hoặc fallback "Failed to update proxy"
- **Loading:** disable nút Save, hiển thị Spinner

### ProxyTable — `frontend/src/components/proxies/ProxyTable.tsx`

- Thêm prop: `onEdit: (proxy: ProxyItem) => void`
- Thêm icon `PencilIcon` (lucide-react) cạnh icon `Trash2Icon` trên mỗi row
- Click icon → gọi `onEdit(proxy)`

### ProxiesPage — `frontend/src/pages/ProxiesPage.tsx`

- State mới: `const [editingProxy, setEditingProxy] = useState<ProxyItem | null>(null)`
- Truyền `onEdit={setEditingProxy}` xuống `ProxyTable`
- Render `<EditProxyDialog proxy={editingProxy} onOpenChange={() => setEditingProxy(null)} onUpdated={invalidate} />`

## Error Handling

| Lỗi | Hành vi |
|------|---------|
| 409 Conflict | Hiển thị "Proxy already exists" tại field Host trong dialog |
| 404 Not Found | Toast "Proxy not found", đóng dialog |
| 422 Validation | Hiển thị message lỗi từ server |
| Network/Other | Fallback "Failed to update proxy" |

## Out of Scope

- Không refactor `AddProxyDialog` (giữ nguyên)
- Không thêm test file mới
- Không thêm route/page riêng cho proxy detail
