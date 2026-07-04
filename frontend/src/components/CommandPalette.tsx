/**
 * 全局命令面板 (Cmd+K / Ctrl+K) — 股票快速搜索 + 跳转个股分析。
 *
 * - 全局 keydown 监听 Cmd/Ctrl+K 开关, Esc 关闭。
 * - 打开时一次性拉全量 instruments (api.instrumentList, 长 staleTime 缓存 ~5000 项)。
 * - 本地用 pinyin-pro 把名称转拼音首字母, 对 query 多路匹配 (code/symbol/name/拼音)。
 * - Enter / 点击 → navigate('/stock-analysis?symbol=...')。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Search, X, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'

type Inst = { symbol: string; name: string; code: string }

// pinyin-pro 动态导入: 只在面板打开时加载, 避免进入主 bundle (减小 Vite 压缩内存/体积)
type PinyinFn = (s: string, opts: object) => string | string[]
let _pinyin: PinyinFn | null = null
async function loadPinyin(): Promise<PinyinFn> {
  if (_pinyin) return _pinyin
  const mod = await import('pinyin-pro')
  _pinyin = mod.pinyin as PinyinFn
  return _pinyin
}

function initialsOf(pinyin: PinyinFn, s: string): string {
  const arr = pinyin(s, { pattern: 'first', toneType: 'none', type: 'array' }) as string[]
  return (arr || [])
    .map((c: string) => (c && /[a-z]/i.test(c) ? c.toUpperCase() : c))
    .join('')
}

export function CommandPalette() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [activeIdx, setActiveIdx] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  // 一次性拉全量标的, 长缓存 (标的表日级更新)
  const { data, isLoading } = useQuery({
    queryKey: QK.instrumentList,
    queryFn: () => api.instrumentList(),
    staleTime: 10 * 60_000,
    enabled: open,  // 仅打开时加载
  })

  // 全局快捷键
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen(o => !o)
      } else if (e.key === 'Escape' && open) {
        setOpen(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  // 打开时聚焦输入框, 清空 query
  useEffect(() => {
    if (open) {
      setQ('')
      setActiveIdx(0)
      setTimeout(() => inputRef.current?.focus(), 30)
    }
  }, [open])

  const all: Inst[] = data?.results ?? []

  // 拼音首字母按需计算: pinyin-pro 加载完成后, 对当前已加载的标的批量算一次
  const [pyMap, setPyMap] = useState<Record<string, string>>({})
  useEffect(() => {
    if (!open || all.length === 0) return
    let cancelled = false
    loadPinyin().then(fn => {
      if (cancelled) return
      const m: Record<string, string> = {}
      for (const it of all) m[it.symbol] = initialsOf(fn, it.name)
      setPyMap(m)
    }).catch(() => { /* pinyin 加载失败, 退化为无拼音匹配 */ })
    return () => { cancelled = true }
  }, [open, all])

  const indexed = useMemo(() => {
    return all.map(it => ({ ...it, py: pyMap[it.symbol] ?? '' }))
  }, [all, pyMap])

  // 本地多路匹配
  const results = useMemo(() => {
    const kw = q.trim().toUpperCase()
    if (!kw) return indexed.slice(0, 10)
    const prefix: typeof indexed = []
    const contain: typeof indexed = []
    for (const it of indexed) {
      const code = it.code.toUpperCase()
      const sym = it.symbol.toUpperCase()
      const name = it.name
      const py = it.py
      if (code.startsWith(kw) || sym.startsWith(kw) || py.startsWith(kw) || name.startsWith(q.trim())) {
        prefix.push(it)
      } else if (code.includes(kw) || sym.includes(kw) || name.includes(q.trim()) || py.includes(kw)) {
        contain.push(it)
      }
      if (prefix.length >= 10) break
    }
    return [...prefix, ...contain].slice(0, 10)
  }, [q, indexed])

  // activeIdx 越界回退
  useEffect(() => { setActiveIdx(0) }, [q])
  useEffect(() => { if (activeIdx >= results.length) setActiveIdx(0) }, [results.length, activeIdx])

  const pick = (it: Inst | undefined) => {
    if (!it) return
    setOpen(false)
    navigate(`/stock-analysis?symbol=${encodeURIComponent(it.symbol)}`)
  }

  const onListKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIdx(i => Math.min(i + 1, results.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIdx(i => Math.max(i - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); pick(results[activeIdx]) }
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-[100] flex items-start justify-center bg-black/50 pt-[12vh] px-4"
          onClick={() => setOpen(false)}
        >
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.15 }}
            onClick={e => e.stopPropagation()}
            className="w-full max-w-xl rounded-card border border-border bg-surface shadow-2xl overflow-hidden"
          >
            {/* 搜索框 */}
            <div className="flex items-center gap-2 border-b border-border px-4 py-3">
              <Search className="h-4 w-4 text-muted shrink-0" />
              <input
                ref={inputRef}
                value={q}
                onChange={e => setQ(e.target.value)}
                onKeyDown={onListKey}
                placeholder="搜索股票代码 / 名称 / 拼音首字母 (如 600519 / 茅台 / gzmt)"
                className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted/60"
              />
              <kbd className="text-[10px] text-muted bg-elevated px-1.5 py-0.5 rounded">ESC</kbd>
              <button onClick={() => setOpen(false)} className="text-muted hover:text-foreground"><X className="h-4 w-4" /></button>
            </div>
            {/* 结果列表 */}
            <div className="max-h-[50vh] overflow-y-auto py-1">
              {isLoading ? (
                <div className="flex items-center justify-center py-8 text-muted"><Loader2 className="h-4 w-4 animate-spin" /></div>
              ) : results.length === 0 ? (
                <div className="py-8 text-center text-sm text-muted">无匹配标的</div>
              ) : (
                results.map((it, i) => (
                  <button
                    key={it.symbol}
                    onMouseEnter={() => setActiveIdx(i)}
                    onClick={() => pick(it)}
                    className={cn(
                      'flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm transition-colors',
                      i === activeIdx ? 'bg-accent/10' : 'hover:bg-elevated/40',
                    )}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="font-mono text-secondary shrink-0">{it.code}</span>
                      <span className="text-foreground truncate">{it.name}</span>
                    </div>
                    <span className="font-mono text-[10px] text-muted shrink-0">{it.symbol}</span>
                  </button>
                ))
              )}
            </div>
            {/* 底部提示 */}
            <div className="border-t border-border px-4 py-1.5 text-[10px] text-muted/70 flex items-center justify-between">
              <span>↑↓ 选择 · Enter 进入个股分析</span>
              <span>{all.length} 只标的</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
