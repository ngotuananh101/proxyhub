# Multi-tenant Frontend Integration Design Spec

**Date:** 2026-08-29
**Status:** Draft
**Scope:** Frontend UI for Multi-tenant Phase 1 (Tenant switcher on header, tenant management on `/tenants`, X-Tenant-Id request interceptor, React context).

---

## 1. Summary

Connect the frontend application to the newly created backend multi-tenant foundation. The frontend enables active tenant switching via a dropdown in `AppHeader`, automatically injects the active tenant ID as an `X-Tenant-Id` header into all outgoing API requests, and provides a dedicated `/tenants` admin management page with dialogs to create tenants and manage tenant memberships.

---

## 2. Architecture & State Management

### 2.1 Storage & Interceptor
- Active tenant ID is persisted in `localStorage` under key `selected_tenant_id`.
- Axios request interceptor in `src/api/client.ts` reads `selected_tenant_id` and sets `X-Tenant-Id: <id>` on every API request.
- When `selected_tenant_id` is updated or cleared, all active TanStack Query queries are invalidated (`queryClient.invalidateQueries()`) to instantly refresh all data tables (Proxies, Stats, Logs, Sources) without full page reload.

### 2.2 Tenant Context (`src/lib/tenant.tsx`)
- Provides React context with:
  - `activeTenant: TenantItem | null`
  - `availableTenants: TenantItem[]`
  - `setActiveTenant: (tenant: TenantItem) => void`
  - `isLoadingTenants: boolean`
  - `refreshTenants: () => Promise<void>`
- On initial authentication or app mount:
  - Fetches the user's available tenants via `GET /api/tenants` (for admins) or user memberships.
  - If a stored `selected_tenant_id` exists and matches an available tenant, activates it.
  - Otherwise, defaults to the first available tenant (typically the `default` tenant).

---

## 3. UI Components & Layout

### 3.1 Tenant Switcher (`src/components/layout/TenantSwitcher.tsx`)
- Placed in `AppHeader` between breadcrumb placeholder and `ThemeToggle`.
- Renders a compact trigger button using the `base-sera` style:
  - Icon: `Building2` or `Layers`.
  - Label: Active tenant name (e.g. `Default`, `Acme Corp`).
  - Chevron indicator: `ChevronsUpDown`.
- Dropdown menu:
  - Lists all available tenants with name, slug badge, and `Check` icon on the active one.
  - Selecting a tenant calls `setActiveTenant(tenant)` and triggers a toast notification: `"Switched to tenant: [Name]"`.
  - For admin users: includes a bottom action item `"+ Manage Tenants"` directing to `/tenants`.

### 3.2 Tenant Management Page (`src/pages/TenantsPage.tsx`)
- Route: `/tenants`, wrapped in admin protection (redirects non-admins).
- Sidebar: `AppSidebar` adds a navigation item `Tenants` (`Building2` icon) visible only to super admins (`user?.is_admin === true`).
- Layout:
  - Page header with title, subtitle, and `"+ Create Tenant"` button.
  - Table of tenants displaying columns:
    - **Name**: display name
    - **Slug**: monospace badge (`font-mono text-xs`)
    - **Created At**: formatted with user's configured timezone
    - **Actions**:
      - `Switch to`: switches active tenant directly to this tenant
      - `Members`: opens the `ManageMembersDialog`

### 3.3 Create Tenant Dialog (`src/components/tenants/CreateTenantDialog.tsx`)
- Form inputs:
  - `Name`: string, required
  - `Slug`: string, optional (auto-suggests kebab-case from Name if left blank)
- Submits `POST /api/tenants`.
- On success: closes dialog, invalidates `['tenants']` queries, shows success toast.

### 3.4 Manage Members Dialog (`src/components/tenants/ManageMembersDialog.tsx`)
- Header shows tenant name.
- Top section: Form to add member:
  - `User ID`: number input
  - `Role`: dropdown with options `member` and `admin`
  - `Add Member` button (calls `POST /api/tenants/{tenant_id}/members`)
- Bottom section: Table of current members:
  - Columns: `User ID`, `Role` (badge), `Action` (`Delete` button calling `DELETE /api/tenants/{tenant_id}/members/{user_id}`).

---

## 4. API Layer (`src/api/tenants.ts`)

Defines TypeScript interfaces and API methods:

```typescript
export interface TenantItem {
  id: number
  name: string
  slug: string
  created_at: string
}

export interface TenantCreateInput {
  name: string
  slug?: string
}

export interface TenantMembershipItem {
  id: number
  tenant_id: number
  user_id: number
  role: 'admin' | 'member'
}

export interface MembershipCreateInput {
  user_id: number
  role: string
}

export async function listTenants(): Promise<TenantItem[]>
export async function createTenant(input: TenantCreateInput): Promise<TenantItem>
export async function listMembers(tenantId: number): Promise<TenantMembershipItem[]>
export async function addMember(tenantId: number, input: MembershipCreateInput): Promise<TenantMembershipItem>
export async function removeMember(tenantId: number, userId: number): Promise<void>
```

---

## 5. Testing Plan

1. **Unit tests for API & Client**:
   - `src/api/client.ts`: verify `X-Tenant-Id` header is injected when `localStorage` has `selected_tenant_id`.
   - `src/api/tenants.ts`: verify API endpoints mapping.
2. **Component unit tests (`vitest` + `@testing-library/react`)**:
   - `TenantSwitcher`: renders active tenant, dropdown list, clicking tenant calls callback.
   - `TenantsPage`: renders tenants table, renders empty state, opens dialogs.
   - `CreateTenantDialog`: form submission, slug generation.
   - `ManageMembersDialog`: member list render, add member, delete member.
3. **Build verification**:
   - `npx tsc -b` & `npm run build` must pass with 0 errors.
