import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { changePassword, getMe, updateMe } from '@/api/auth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { toast } from '@/components/ui/toast'

function errorDetail(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response
    ?.data?.detail
  return detail || fallback
}

function ProfileForm() {
  const queryClient = useQueryClient()
  const { data: user } = useQuery({ queryKey: ['me'], queryFn: getMe })
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (user) {
      setUsername(user.username)
      setEmail(user.email ?? '')
    }
  }, [user])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSaving(true)
    try {
      await updateMe({ username, email: email || null })
      queryClient.invalidateQueries({ queryKey: ['me'] })
      toast.add({ type: 'success', title: 'Profile updated' })
    } catch (err) {
      setError(errorDetail(err, 'Update failed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Account Information</CardTitle>
        <CardDescription>
          Update your username and email.
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit} className="flex flex-col gap-(--card-spacing)">
        <CardContent>
          <FieldGroup className='gap-4'>
            <Field data-invalid={!!error}>
              <FieldLabel htmlFor="profile-username">Username</FieldLabel>
              <Input
                id="profile-username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                aria-invalid={!!error}
                required
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="profile-email">Email</FieldLabel>
              <Input
                id="profile-email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              {error && <FieldDescription>{error}</FieldDescription>}
            </Field>
          </FieldGroup>
        </CardContent>
        <CardFooter className="justify-end">
          <Button type="submit" disabled={saving}>
            {saving && <Spinner data-icon="inline-start" />}
            Save Changes
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}

function PasswordForm() {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match')
      return
    }
    setSaving(true)
    try {
      await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      })
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      toast.add({ type: 'success', title: 'Password changed' })
    } catch (err) {
      setError(errorDetail(err, 'Failed to change password'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Change Password</CardTitle>
        <CardDescription>
          New password must be at least 8 characters.
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit} className="flex flex-col gap-(--card-spacing)">
        <CardContent>
          <FieldGroup className='gap-4'>
            <Field>
              <FieldLabel htmlFor="current-password">Current password</FieldLabel>
              <Input
                id="current-password"
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="new-password">New password</FieldLabel>
              <Input
                id="new-password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                minLength={8}
                required
              />
            </Field>
            <Field data-invalid={!!error}>
              <FieldLabel htmlFor="confirm-password">
                Confirm new password
              </FieldLabel>
              <Input
                id="confirm-password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                aria-invalid={!!error}
                minLength={8}
                required
              />
              {error && <FieldDescription>{error}</FieldDescription>}
            </Field>
          </FieldGroup>
        </CardContent>
        <CardFooter className="justify-end">
          <Button type="submit" disabled={saving}>
            {saving && <Spinner data-icon="inline-start" />}
            Change Password
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}

export default function ProfilePage() {
  const { data: user } = useQuery({ queryKey: ['me'], queryFn: getMe })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Profile</h1>
        <p className="text-sm text-muted-foreground">
          Manage your account information.
        </p>
      </div>

      {user && (
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Signed in as</span>
          <Badge variant="secondary">{user.username}</Badge>
          {user.is_admin && <Badge>Admin</Badge>}
        </div>
      )}

      <div className="grid max-w-3xl gap-6">
        <ProfileForm />
        <PasswordForm />
      </div>
    </div>
  )
}
