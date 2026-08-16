import { Separator } from '@/components/ui/separator'

export function AppFooter() {
  return (
    <footer className="shrink-0 border-t bg-background px-6 py-3">
      <div className="flex flex-col items-center justify-between gap-2 text-xs text-muted-foreground sm:flex-row">
        <p className="font-medium text-foreground">ProxyHub</p>
        <div className="flex items-center gap-2">
          <span>Proxy management &amp; rotation system</span>
          <Separator orientation="vertical" className="h-3" />
          <span>API :8000</span>
          <Separator orientation="vertical" className="h-3" />
          <span>Gateway :8899</span>
          <Separator orientation="vertical" className="h-3" />
          <span>v0.1.0 · MIT License</span>
        </div>
      </div>
    </footer>
  )
}
