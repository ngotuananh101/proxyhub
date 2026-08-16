import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { isAuthenticated } from './lib/auth'
import { ThemeProvider } from './lib/theme'
import { AppLayout } from './components/layout/AppLayout'
import { Toaster } from './components/ui/toast'
import { TooltipProvider } from './components/ui/tooltip'
import LoginPage from './pages/LoginPage'
import ProxiesPage from './pages/ProxiesPage'
import ProfilePage from './pages/ProfilePage'

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
                <Route path="/profile" element={<ProfilePage />} />
              </Route>
            </Routes>
          </BrowserRouter>
          <Toaster />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
