import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
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
                <Route path="/tenants" element={<TenantsPage />} />
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
