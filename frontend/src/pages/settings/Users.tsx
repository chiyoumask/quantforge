/**
 * 用户管理面板 — 仅超管可见。
 *
 * 功能:
 *   - 列出全部用户 (用户名/角色/状态/到期/创建时间)
 *   - 创建用户 (用户名/密码/角色/到期)
 *   - 操作: 暂停/恢复、改到期、重置密码、删除
 *   - 到期临近/已到期高亮
 *
 * 后端 /api/users 全部要求 role=admin, 非超管访问返回 403 (Settings.tsx 仅对 admin 显示此 tab)。
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  Loader2, Plus, Trash2, Power, KeyRound, CalendarClock, ShieldCheck, ShieldOff, X, Star, BarChart3,
} from 'lucide-react'
import { api, type UserRecord } from '@/lib/api'
import { PageHeader } from '@/components/PageHeader'
import { cn } from '@/lib/cn'

// 到期状态判定
function expiryKind(expires_at: string | null, effective: string) {
  if (effective === 'expired') return 'expired'
  if (!expires_at) return 'never'
  const d = new Date(expires_at)
  const days = (d.getTime() - Date.now()) / 86400_000
  if (days < 7) return 'soon'
  return 'ok'
}

const EXPIRY_STYLE: Record<string, string> = {
  expired: 'text-danger',
  soon: 'text-warning',
  ok: 'text-secondary',
  never: 'text-muted',
}

function fmtExpiry(expires_at: string | null, effective: string) {
  if (effective === 'expired') return '已过期'
  if (!expires_at) return '永不过期'
  const d = new Date(expires_at)
  const days = Math.floor((d.getTime() - Date.now()) / 86400_000)
  return `${d.toLocaleDateString('zh-CN')} (${days >= 0 ? `剩 ${days} 天` : `过期 ${-days} 天`})`
}

export function SettingsUsersPanel() {
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [actionUser, setActionUser] = useState<UserRecord | null>(null)

  const { data: users, isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: () => api.usersList(),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['users'] })

  const createMut = useMutation({
    mutationFn: (v: { username: string; password: string; role: string; expires_at: string | null }) =>
      api.userCreate(v),
    onSuccess: () => { invalidate(); setShowCreate(false) },
  })

  const updateMut = useMutation({
    mutationFn: ({ u, body }: { u: UserRecord; body: Record<string, unknown> }) =>
      api.userUpdate(u.username, body as any),
    onSuccess: () => { invalidate(); setActionUser(null) },
  })

  const delMut = useMutation({
    mutationFn: (u: UserRecord) => api.userDelete(u.username),
    onSuccess: () => { invalidate(); setActionUser(null) },
  })

  const resetMut = useMutation({
    mutationFn: ({ u, pwd }: { u: UserRecord; pwd: string }) =>
      api.userResetPassword(u.username, pwd),
    onSuccess: () => setActionUser(null),
  })

  return (
    <>
      <PageHeader
        title="用户管理"
        subtitle="创建/删除用户、设定使用周期、暂停或延期。仅超级管理员可见。"
      />

      <div className="px-8 py-6 space-y-4">
        {/* 工具栏 */}
        <div className="flex items-center justify-between">
          <div className="text-sm text-secondary">
            共 {users?.length ?? 0} 个用户
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="inline-flex items-center gap-1.5 rounded-btn bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent/90"
          >
            <Plus className="h-3.5 w-3.5" /> 新建用户
          </button>
        </div>

        {/* 用户表 */}
        <div className="rounded-card border border-border bg-surface overflow-hidden">
          {isLoading ? (
            <div className="flex items-center justify-center py-12 text-muted">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-elevated/40 text-[11px] uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-4 py-2.5 text-left font-medium">用户名</th>
                  <th className="px-4 py-2.5 text-left font-medium">角色</th>
                  <th className="px-4 py-2.5 text-left font-medium">状态</th>
                  <th className="px-4 py-2.5 text-left font-medium">自选上限</th>
                  <th className="px-4 py-2.5 text-left font-medium">到期</th>
                  <th className="px-4 py-2.5 text-left font-medium">创建时间</th>
                  <th className="px-4 py-2.5 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {users?.map(u => {
                  const ek = expiryKind(u.expires_at, u.effective_status)
                  return (
                    <tr key={u.username} className="hover:bg-elevated/30">
                      <td className="px-4 py-2.5 font-medium text-foreground">{u.username}</td>
                      <td className="px-4 py-2.5">
                        {u.role === 'admin' ? (
                          <span className="inline-flex items-center gap-1 text-accent">
                            <ShieldCheck className="h-3.5 w-3.5" /> 管理员
                          </span>
                        ) : u.role === 'vip' ? (
                          <span className="inline-flex items-center gap-1 text-purple-400">
                            <ShieldCheck className="h-3.5 w-3.5" /> VIP
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-secondary">
                            <ShieldOff className="h-3.5 w-3.5" /> 用户
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        <StatusBadge status={u.effective_status} />
                      </td>
                      <td className="px-4 py-2.5 font-mono text-secondary">
                        {u.effective_quotas?.watchlist_limit == null ? '不限' : u.effective_quotas.watchlist_limit}
                        {u.quotas?.watchlist_limit != null && <span className="text-[9px] text-accent ml-1">(自定义)</span>}
                      </td>
                      <td className={cn('px-4 py-2.5', EXPIRY_STYLE[ek])}>
                        {fmtExpiry(u.expires_at, u.effective_status)}
                      </td>
                      <td className="px-4 py-2.5 text-muted">
                        {u.created_at ? new Date(u.created_at).toLocaleDateString('zh-CN') : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <button
                          onClick={() => setActionUser(u)}
                          className="rounded-btn px-2 py-1 text-xs text-secondary hover:bg-elevated hover:text-foreground"
                        >
                          管理
                        </button>
                      </td>
                    </tr>
                  )
                })}
                {!users?.length && (
                  <tr><td colSpan={6} className="px-4 py-8 text-center text-muted">暂无用户</td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* 创建用户对话框 */}
      {showCreate && (
        <CreateUserDialog
          onClose={() => setShowCreate(false)}
          onSubmit={(v) => createMut.mutate(v)}
          pending={createMut.isPending}
          error={createMut.error?.message}
        />
      )}

      {/* 单用户操作面板 */}
      {actionUser && (
        <UserActionDialog
          user={actionUser}
          onClose={() => setActionUser(null)}
          onSuspend={(u) => updateMut.mutate({ u, body: { status: 'suspended' } })}
          onActivate={(u) => updateMut.mutate({ u, body: { status: 'active' } })}
          onExtend={(u, iso) => updateMut.mutate({ u, body: { expires_at: iso } })}
          onUpdateRole={(u, role) => updateMut.mutate({ u, body: { role } })}
          onUpdateWatchlist={(u, limit) => updateMut.mutate({ u, body: { watchlist_limit: limit } })}
          onToggleExtPages={(u, enabled) => updateMut.mutate({ u, body: { ext_pages: enabled } })}
          onReset={(u, pwd) => resetMut.mutate({ u, pwd })}
          onDelete={(u) => delMut.mutate(u)}
          pending={updateMut.isPending || delMut.isPending || resetMut.isPending}
          error={updateMut.error?.message || delMut.error?.message || resetMut.error?.message}
        />
      )}
    </>
  )
}

// ================================================================
// 状态徽章
// ================================================================
function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    active: { label: '正常', cls: 'bg-success/15 text-success' },
    suspended: { label: '已暂停', cls: 'bg-warning/15 text-warning' },
    expired: { label: '已过期', cls: 'bg-danger/15 text-danger' },
  }
  const s = map[status] ?? map.active
  return <span className={cn('inline-block rounded-full px-2 py-0.5 text-[10px] font-medium', s.cls)}>{s.label}</span>
}

// ================================================================
// 创建用户对话框
// ================================================================
function CreateUserDialog({
  onClose, onSubmit, pending, error,
}: {
  onClose: () => void
  onSubmit: (v: { username: string; password: string; role: string; expires_at: string | null }) => void
  pending: boolean
  error?: string
}) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('user')
  const [expiryMode, setExpiryMode] = useState<'never' | 'days'>('never')
  const [days, setDays] = useState(30)

  const submit = () => {
    let expires_at: string | null = null
    if (expiryMode === 'days') {
      const d = new Date(Date.now() + days * 86400_000)
      expires_at = d.toISOString()
    }
    onSubmit({ username: username.trim(), password, role, expires_at })
  }

  return (
    <DialogShell onClose={onClose} title="新建用户">
      <div className="space-y-3">
        <Field label="用户名">
          <input value={username} onChange={e => setUsername(e.target.value)}
            placeholder="字母数字下划线连字符, 2-32 字符"
            className="h-9 w-full rounded-btn border border-border bg-base px-3 text-sm outline-none focus:border-accent/50" />
        </Field>
        <Field label="密码">
          <input type="password" value={password} onChange={e => setPassword(e.target.value)}
            placeholder="至少 6 位"
            className="h-9 w-full rounded-btn border border-border bg-base px-3 text-sm outline-none focus:border-accent/50" />
        </Field>
        <Field label="角色">
          <select value={role} onChange={e => setRole(e.target.value)}
            className="h-9 w-full rounded-btn border border-border bg-base px-3 text-sm outline-none focus:border-accent/50">
            <option value="user">普通用户 (自选 5 只)</option>
            <option value="vip">VIP 用户 (自选 30 只)</option>
            <option value="admin">管理员 (不限)</option>
          </select>
        </Field>
        <Field label="使用周期">
          <div className="flex items-center gap-3 text-sm">
            <label className="flex items-center gap-1.5">
              <input type="radio" checked={expiryMode === 'never'} onChange={() => setExpiryMode('never')} />
              永不过期
            </label>
            <label className="flex items-center gap-1.5">
              <input type="radio" checked={expiryMode === 'days'} onChange={() => setExpiryMode('days')} />
              <input type="number" min={1} max={3650} value={days}
                onChange={e => setDays(Math.max(1, +e.target.value || 1))}
                disabled={expiryMode !== 'days'}
                className="h-8 w-20 rounded-btn border border-border bg-base px-2 text-sm outline-none focus:border-accent/50" />
              天后到期
            </label>
          </div>
        </Field>
        {error && <p className="text-[11px] text-danger">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="rounded-btn px-3 py-1.5 text-sm text-secondary hover:bg-elevated">取消</button>
          <button onClick={submit} disabled={pending || !username || password.length < 6}
            className="inline-flex items-center gap-1.5 rounded-btn bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50">
            {pending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />} 创建
          </button>
        </div>
      </div>
    </DialogShell>
  )
}

// ================================================================
// 单用户操作对话框
// ================================================================
function UserActionDialog({
  user, onClose, onSuspend, onActivate, onExtend, onReset, onDelete, onUpdateRole, onUpdateWatchlist, onToggleExtPages, pending, error,
}: {
  user: UserRecord
  onClose: () => void
  onSuspend: (u: UserRecord) => void
  onActivate: (u: UserRecord) => void
  onExtend: (u: UserRecord, iso: string) => void
  onReset: (u: UserRecord, pwd: string) => void
  onDelete: (u: UserRecord) => void
  onUpdateRole: (u: UserRecord, role: string) => void
  onUpdateWatchlist: (u: UserRecord, limit: number | 'default') => void
  onToggleExtPages: (u: UserRecord, enabled: boolean) => void
  pending: boolean
  error?: string
}) {
  const [extendDays, setExtendDays] = useState(30)
  const [newPwd, setNewPwd] = useState('')
  const [confirmDel, setConfirmDel] = useState(false)
  const [wlInput, setWlInput] = useState<string>(
    user.quotas?.watchlist_limit != null ? String(user.quotas.watchlist_limit) : ''
  )

  return (
    <DialogShell onClose={onClose} title={`管理 · ${user.username}`}>
      <div className="space-y-4">
        {/* 当前状态 */}
        <div className="flex items-center gap-3 rounded-btn bg-elevated/40 px-3 py-2 text-sm">
          <StatusBadge status={user.effective_status} />
          <span className="text-secondary">
            到期: {fmtExpiry(user.expires_at, user.effective_status)}
          </span>
        </div>

        {error && <p className="text-[11px] text-danger">{error}</p>}

        {/* 暂停/恢复 */}
        <ActionRow icon={Power} label="账号状态">
          {user.effective_status === 'active' ? (
            <button onClick={() => onSuspend(user)} disabled={pending}
              className="rounded-btn bg-warning/15 px-3 py-1.5 text-xs text-warning hover:bg-warning/25 disabled:opacity-50">
              暂停使用
            </button>
          ) : (
            <button onClick={() => onActivate(user)} disabled={pending}
              className="rounded-btn bg-success/15 px-3 py-1.5 text-xs text-success hover:bg-success/25 disabled:opacity-50">
              恢复使用
            </button>
          )}
        </ActionRow>

        {/* 角色升降 (不能改自己/最后一个admin) */}
        <ActionRow icon={ShieldCheck} label="角色">
          <select
            value={user.role}
            onChange={e => onUpdateRole(user, e.target.value)}
            disabled={pending || user.role === 'admin'}
            className="h-8 rounded-btn border border-border bg-base px-2 text-xs outline-none focus:border-accent/50 disabled:opacity-60"
          >
            <option value="user">普通用户 (5)</option>
            <option value="vip">VIP (30)</option>
            <option value="admin">管理员</option>
          </select>
        </ActionRow>

        {/* 自选股配额 */}
        <ActionRow icon={Star} label="自选股上限">
          <div className="flex items-center gap-2">
            <input type="number" min={1} max={1000} value={wlInput}
              onChange={e => setWlInput(e.target.value)}
              placeholder={user.effective_quotas?.watchlist_limit == null ? '不限' : String(user.effective_quotas.watchlist_limit)}
              className="h-8 w-20 rounded-btn border border-border bg-base px-2 text-sm outline-none focus:border-accent/50" />
            <button
              onClick={() => {
                const v = wlInput.trim()
                if (!v) onUpdateWatchlist(user, 'default')
                else onUpdateWatchlist(user, Math.max(1, parseInt(v) || 1))
              }}
              disabled={pending}
              className="rounded-btn bg-accent/15 px-3 py-1.5 text-xs text-accent hover:bg-accent/25 disabled:opacity-50">
              设定
            </button>
            <button onClick={() => onUpdateWatchlist(user, 'default')} disabled={pending}
              className="rounded-btn px-2 py-1.5 text-xs text-muted hover:bg-elevated disabled:opacity-50">
              默认
            </button>
          </div>
        </ActionRow>

        {/* 扩展页面开关 (admin 默认开, 其他默认关; 可逐用户覆盖) */}
        <ActionRow icon={BarChart3} label="扩展页面">
          {(() => {
            const enabled = user.effective_features?.ext_pages ?? false
            const overridden = user.features?.ext_pages != null
            return (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => onToggleExtPages(user, !enabled)}
                  disabled={pending || user.role === 'admin'}
                  className={`rounded-btn px-3 py-1.5 text-xs disabled:opacity-50 ${
                    enabled ? 'bg-accent/15 text-accent hover:bg-accent/25' : 'bg-elevated text-secondary hover:bg-elevated/70'
                  }`}
                >
                  {enabled ? '已开放' : '未开放'}
                </button>
                {overridden && <span className="text-[9px] text-accent">(自定义)</span>}
                {user.role === 'admin' && <span className="text-[9px] text-muted">(管理员默认开放)</span>}
              </div>
            )
          })()}
        </ActionRow>

        {/* 延期 */}
        <ActionRow icon={CalendarClock} label="延长使用周期">
          <div className="flex items-center gap-2">
            <input type="number" min={1} max={3650} value={extendDays}
              onChange={e => setExtendDays(Math.max(1, +e.target.value || 1))}
              className="h-8 w-20 rounded-btn border border-border bg-base px-2 text-sm outline-none focus:border-accent/50" />
            <span className="text-xs text-muted">天</span>
            <button
              onClick={() => {
                const base = user.expires_at ? new Date(user.expires_at) : new Date()
                const start = base.getTime() < Date.now() ? Date.now() : base.getTime()
                onExtend(user, new Date(start + extendDays * 86400_000).toISOString())
              }}
              disabled={pending}
              className="rounded-btn bg-accent/15 px-3 py-1.5 text-xs text-accent hover:bg-accent/25 disabled:opacity-50">
              确认延期
            </button>
          </div>
        </ActionRow>

        {/* 重置密码 */}
        <ActionRow icon={KeyRound} label="重置密码">
          <div className="flex items-center gap-2">
            <input type="password" value={newPwd} onChange={e => setNewPwd(e.target.value)}
              placeholder="新密码 (≥6位)"
              className="h-8 w-40 rounded-btn border border-border bg-base px-2 text-sm outline-none focus:border-accent/50" />
            <button onClick={() => onReset(user, newPwd)} disabled={pending || newPwd.length < 6}
              className="rounded-btn bg-elevated px-3 py-1.5 text-xs text-foreground hover:bg-elevated/70 disabled:opacity-50">
              重置
            </button>
          </div>
        </ActionRow>

        {/* 删除 */}
        <ActionRow icon={Trash2} label="删除账号" danger>
          {confirmDel ? (
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-danger">确认删除?</span>
              <button onClick={() => onDelete(user)} disabled={pending}
                className="rounded-btn bg-danger px-3 py-1.5 text-xs text-white hover:bg-danger/90 disabled:opacity-50">
                删除
              </button>
              <button onClick={() => setConfirmDel(false)}
                className="rounded-btn px-3 py-1.5 text-xs text-secondary hover:bg-elevated">取消</button>
            </div>
          ) : (
            <button onClick={() => setConfirmDel(true)} disabled={pending || user.role === 'admin'}
              className="rounded-btn bg-danger/15 px-3 py-1.5 text-xs text-danger hover:bg-danger/25 disabled:opacity-50"
              title={user.role === 'admin' ? '管理员账号不可在此删除' : ''}>
              删除账号
            </button>
          )}
        </ActionRow>
      </div>
    </DialogShell>
  )
}

// ================================================================
// 小组件
// ================================================================
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-[11px] text-muted">{label}</label>
      {children}
    </div>
  )
}

function ActionRow({ icon: Icon, label, children, danger }: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  children: React.ReactNode
  danger?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className={cn('flex items-center gap-1.5 text-sm', danger ? 'text-danger' : 'text-secondary')}>
        <Icon className="h-3.5 w-3.5" /> {label}
      </div>
      {children}
    </div>
  )
}

function DialogShell({ onClose, title, children }: {
  onClose: () => void
  title: string
  children: React.ReactNode
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.15 }}
        onClick={e => e.stopPropagation()}
        className="w-full max-w-md rounded-card border border-border bg-surface p-5 shadow-2xl"
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-foreground">{title}</h3>
          <button onClick={onClose} className="text-muted hover:text-foreground"><X className="h-4 w-4" /></button>
        </div>
        {children}
      </motion.div>
    </motion.div>
  )
}
