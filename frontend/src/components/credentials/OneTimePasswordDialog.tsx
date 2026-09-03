import { useState } from 'react'
import { CopyIcon, CheckIcon } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface OneTimePasswordDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  username?: string | null
  password?: string | null
}

export function OneTimePasswordDialog({
  open,
  onOpenChange,
  username,
  password,
}: OneTimePasswordDialogProps) {
  const [copied, setCopied] = useState(false)

  if (!password) return null

  const curlExample = `curl -x http://${username || 'user'}:${password}@<gateway-host>:8899 https://api.ipify.org`

  const handleCopy = () => {
    navigator.clipboard.writeText(password)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Save Gateway Password</DialogTitle>
          <DialogDescription>
            This password is only shown once. Store it securely — you will not be able to see it again.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="flex items-center gap-2">
            <Input readOnly value={password} className="font-mono text-sm" />
            <Button variant="outline" size="icon" onClick={handleCopy}>
              {copied ? <CheckIcon className="size-4 text-green-500" /> : <CopyIcon className="size-4" />}
            </Button>
          </div>
          <div className="rounded bg-muted p-2 text-xs font-mono break-all text-muted-foreground">
            {curlExample}
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
