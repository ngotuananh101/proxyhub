import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { getMe } from './api/auth'
import { isAuthenticated } from './lib/auth'
import { ThemeProvider } from './lib/theme'
import { TenantProvider } from './lib/tenant'
import { AppLayout } from './components/layout/AppLayout'
import { Toaster } from './components/ui/toast'
import { TooltipProvider } from './components/ui/tooltip'
import LoginPage from './pages/LoginPage'
import LogsPage from './pages/LogsPage'
import GatewayCredentialsPage from './pages/GatewayCredentialsPage'
import ProxiesPage from './pages/ProxiesPage'
import ProfilePage from './pages/ProfilePage'
import SettingsPage from './pages/SettingsPage'
import SourcesPage from './pages/SourcesPage'
import TenantsPage from './pages/TenantsPage'

const queryClient = new QueryClient()

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

/**
 * Gates admin-only screens. The sidebar already hides their links, but a typed
 * URL would still render the page and fire its requests, which the API rejects
 * with 403 — leaving a half-loaded screen instead of a clean redirect.
 */
export function AdminRoute({ children }: { children: React.ReactNode }) {
  const { data: user, isPending } = useQuery({ queryKey: ['me'], queryFn: getMe })
  // Wait for the answer: redirecting while `me` is still loading would bounce
  // an admin off the page on every full reload.
  if (isPending) return null
  if (user?.is_admin !== true) {
    return <Navigate to="/" replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <TenantProvider>
            <BrowserRouter>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route
                element={
                  <ProtectedRoute>
                    <AppLayout />
                  </ProtectedRoute>
                }
              >
                <Route path="/" element={<ProxiesPage />} />
                <Route path="/sources" element={<SourcesPage />} />
                <Route path="/logs" element={<LogsPage />} />
                <Route path="/credentials" element={<GatewayCredentialsPage />} />
                <Route
                  path="/tenants"
                  element={
                    <AdminRoute>
                      <TenantsPage />
                    </AdminRoute>
                  }
                />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/profile" element={<ProfilePage />} />
              </Route>
            </Routes>
          </BrowserRouter>
          <Toaster />
        </TenantProvider>
      </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
