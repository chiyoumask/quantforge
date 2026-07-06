import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { X, RefreshCw, Clock, ExternalLink, Globe } from 'lucide-react'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cnSignal } from '@/lib/signals'
import { StockPanel, getDefaultRange } from '@/components/StockPanel'
import { DatePicker } from '@/components/DatePicker'
import { RuleEditor } from '@/components/monitor/RuleEditor'

interface Props {
  symbol: string | null
  name?: string
  onClose: () => void
  /** 触发信息 (来自监控触发记录, 有值时在顶栏下方显示) */
  triggerInfo?: {
    price?: number | null
    changePct?: number | null
    ts?: number
    signals?: string[]
    message?: string
  } | null
}

// ===== 板块标识（与 Screener 列表一致）=====

// 预设快捷范围（只保留半年和1年）
const PRESETS: { label: string; months: number }[] = [
  { label: '半年', months: 6 },
  { label: '1年', months: 12 },
]

function boardTag(symbol: string): { label: string; color: string } | null {
  // symbol 形态: 带交易所后缀(688238.SH)/前缀(SH688238)/或纯数字(688238) 都要兼容。
  // 后端 eastmoney 标准是 "688238.SH" 点号格式 → 先剥掉 .SH/.SZ/.BJ 后缀再剥前缀。
  const code = symbol.replace(/\.(SH|SZ|BJ)$/, '').replace(/^(SH|SZ|BJ)/, '')
  if (/^(300|301)/.test(code)) return { label: '创', color: 'text-[#f97316] bg-[#f97316]/12 border-[#f97316]/25' }
  if (/^688/.test(code))       return { label: '科', color: 'text-purple-400 bg-purple-400/12 border-purple-400/25' }
  if (/^[48]/.test(code))      return { label: '北', color: 'text-cyan-400 bg-cyan-400/12 border-cyan-400/25' }
  return null
}

// 注: 颜色色值与本文件原版保持一致(purple), 不强行对齐共享版 primitives.tsx 的 cyan。
// 这样本次外链功能改动只动一处 bug(不识别 SH 前缀), 不引入跨页颜色差异。

// ===== 外部资料跳转 (个人 VPS 用户在站内缺扩展信息时跳第三方工具) =====
// symbol 形态: SH688238 / SZ000001 / BJ430047。返回 null 表示无法识别该板块/交易所。
type ExternalLink = { label: string; url: string; icon?: 'globe' | 'text' }

function parseSymbol(symbol: string): { exchange: 'SH' | 'SZ' | 'BJ' | null; code: string } {
  // 兼容三种形态 (后端 eastmoney 标准为 "688238.SH" 点号格式, 笔记/搜索可能传 SH688238 或裸 688238):
  //   - 点号后缀: 688238.SH / 000001.SZ / 430047.BJ  (后端 quote/index_records 标准)
  //   - 前缀无点: SH688238 / SZ000001 / BJ430047
  //   - 纯数字  : 688238 / 000001 / 430047  (按首位推断交易所)
  const dot = /^(\d{6})\.(SH|SZ|BJ)$/.exec(symbol)
  if (dot) return { exchange: dot[2] as 'SH' | 'SZ' | 'BJ', code: dot[1] }
  const pref = /^(SH|SZ|BJ)(\d{6})$/.exec(symbol)
  if (pref) return { exchange: pref[1] as 'SH' | 'SZ' | 'BJ', code: pref[2] }
  if (/^\d{6}$/.test(symbol)) {
    const exchange = /^[6]\d{5}$/.test(symbol) ? 'SH' : /^[03]\d{5}$/.test(symbol) ? 'SZ' : /^[48]\d{5}$/.test(symbol) ? 'BJ' : null
    return { exchange, code: symbol }
  }
  return { exchange: null, code: symbol }
}

function buildExternalLinks(symbol: string): ExternalLink[] {
  const { exchange, code } = parseSymbol(symbol)
  if (!exchange || !code) return []
  const exLower = exchange.toLowerCase()
  const exUpper = exchange
  return [
    { label: '百度股市通', url: `https://finance.baidu.com/stock/ab-${code}`, icon: 'globe' },
    { label: '东方财富股吧', url: `https://guba.eastmoney.com/list,${exLower}${code}.html`, icon: 'text' },
    { label: '同花顺', url: `https://stockpage.10jqka.com.cn/${code}/`, icon: 'text' },
    { label: '雪球', url: `https://xueqiu.com/S/${exUpper}${code}`, icon: 'text' },
  ]
}

export function StockPreviewDialog({ symbol, name, onClose, triggerInfo }: Props) {
  const [showIntraday, setShowIntraday] = useState(false)
  const [dateRange, setDateRange] = useState(getDefaultRange)
  const [showMonitorEditor, setShowMonitorEditor] = useState(false)
  const qc = useQueryClient()

  const watchlist = useQuery({
    queryKey: QK.watchlist,
    queryFn: api.watchlistList,
    enabled: !!symbol,
  })
  const inWatchlist = (watchlist.data?.symbols ?? []).some((s: any) => s.symbol === symbol)

  const toggleWatchlist = useMutation({
    mutationFn: () => inWatchlist ? api.watchlistRemove(symbol!) : api.watchlistAdd(symbol!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.watchlist })
      qc.invalidateQueries({ queryKey: QK.watchlistEnriched() })
    },
  })

  // ESC 关闭
  useEffect(() => {
    if (!symbol) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [symbol, onClose])

  const handleRefresh = () => {
    if (!symbol) return
    qc.invalidateQueries({ queryKey: ['kline', symbol!] })
    if (showIntraday) {
      qc.invalidateQueries({ queryKey: ['kline-minute', symbol!] })
    }
  }

  return (
    <AnimatePresence>
      {symbol && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* 遮罩 */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* 弹窗主体 */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 8 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="relative w-[92vw] max-w-[1100px] max-h-[95vh] rounded-card border border-border bg-base shadow-2xl overflow-hidden flex flex-col"
          >
            {/* 顶栏 */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-border shrink-0">
              <div className="flex items-center gap-2">
                {(() => {
                  const board = symbol ? boardTag(symbol) : null
                  return board ? (
                    <span className={`inline-flex items-center justify-center w-[18px] h-[18px] rounded text-[9px] font-bold leading-none border ${board.color}`}>
                      {board.label}
                    </span>
                  ) : null
                })()}
                <span className="font-mono text-sm font-medium text-foreground">{symbol}</span>
                {name && <span className="text-xs text-muted">{name}</span>}
              </div>

              <div className="flex items-center gap-1.5">
                {/* 日期范围快捷 */}
                {PRESETS.map(p => {
                  const now = new Date()
                  const s = new Date(now)
                  s.setMonth(s.getMonth() - p.months)
                  const expected = s.toISOString().slice(0, 10)
                  const isActive = dateRange.start === expected
                  return (
                    <button
                      key={p.label}
                      onClick={() => {
                        const end = new Date().toISOString().slice(0, 10)
                        const ns = new Date()
                        ns.setMonth(ns.getMonth() - p.months)
                        setDateRange({ start: ns.toISOString().slice(0, 10), end })
                      }}
                      className={`h-6 px-1.5 rounded text-[11px] transition-colors cursor-pointer
                        ${isActive
                          ? 'bg-accent/20 text-accent font-medium border border-accent/30'
                          : 'text-muted hover:text-foreground hover:bg-elevated border border-transparent'
                        }`}
                    >
                      {p.label}
                    </button>
                  )
                })}
                <DatePicker
                  value={dateRange.start}
                  onChange={(v) => setDateRange(prev => ({ ...prev, start: v }))}
                  max={dateRange.end}
                />
                <span className="text-muted/40 text-[10px]">~</span>
                <DatePicker
                  value={dateRange.end}
                  onChange={(v) => setDateRange(prev => ({ ...prev, end: v }))}
                  min={dateRange.start}
                />

                <span className="text-muted/20 mx-0.5">|</span>

                {/* 分时开关 */}
                <button
                  onClick={() => setShowIntraday((v) => !v)}
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs transition-colors ${
                    showIntraday
                      ? 'bg-accent/15 text-accent border border-accent/30'
                      : 'bg-elevated text-secondary border border-border hover:border-accent/30'
                  }`}
                >
                  <Clock className="h-3 w-3" />
                  分时
                </button>

                <span className="text-muted/20 mx-0.5">|</span>

                {/* 刷新 */}
                <button
                  onClick={handleRefresh}
                  className="p-1 rounded-btn text-secondary hover:text-foreground hover:bg-elevated transition-colors"
                  title="刷新"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                </button>

                {/* 关闭 */}
                <button
                  onClick={onClose}
                  className="p-1 rounded-btn text-secondary hover:text-foreground hover:bg-elevated transition-colors"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* 外部资料跳转 — 个人 VPS 用户缺扩展信息时跳第三方工具 */}
            {(() => {
              if (!symbol) return null
              const links = buildExternalLinks(symbol)
              if (links.length === 0) return null
              return (
                <div className="flex items-center gap-1.5 px-5 py-1.5 border-b border-border/40 bg-elevated/10 shrink-0">
                  <span className="text-[10px] uppercase tracking-[0.16em] text-muted mr-1.5">
                    外部资料
                  </span>
                  {links.map((l) => (
                    <a
                      key={l.url}
                      href={l.url}
                      target="_blank"
                      rel="noreferrer"
                      title={`${l.label} (新窗口)`}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] text-secondary/80 hover:text-accent hover:bg-accent/10 transition-colors"
                    >
                      {l.icon === 'globe' && <Globe className="h-3 w-3" />}
                      <span>{l.label}</span>
                      <ExternalLink className="h-2.5 w-2.5 opacity-60" />
                    </a>
                  ))}
                </div>
              )
            })()}

            {/* 触发信息条 (来自监控触发记录) */}
            {triggerInfo && (
              <div className="flex items-center gap-4 border-b border-amber-400/20 bg-amber-400/[0.06] px-5 py-2 shrink-0">
                {/* 左: 触发标记 + 时间 */}
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[10px] font-semibold text-amber-400">⚡ 触发</span>
                  {triggerInfo.ts && (
                    <span className="text-[11px] text-secondary font-mono">
                      {new Date(triggerInfo.ts).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                    </span>
                  )}
                </div>

                {/* 中: 价格 + 涨跌幅 */}
                <div className="flex items-center gap-2 shrink-0">
                  {triggerInfo.price != null && (
                    <span className="text-[11px] font-mono text-foreground/80">{triggerInfo.price.toFixed(2)}</span>
                  )}
                  {triggerInfo.changePct != null && (
                    <span className={`text-[11px] font-mono font-medium ${triggerInfo.changePct >= 0 ? 'text-danger' : 'text-bear'}`}>
                      {triggerInfo.changePct >= 0 ? '+' : ''}{(triggerInfo.changePct * 100).toFixed(2)}%
                    </span>
                  )}
                </div>

                {/* 右: 消息 + 信号标签 */}
                <div className="flex items-center gap-2 flex-wrap min-w-0">
                  {triggerInfo.message && (
                    <span className="text-[11px] text-foreground/70 truncate">{triggerInfo.message}</span>
                  )}
                  {triggerInfo.signals && triggerInfo.signals.length > 0 && (
                    <div className="flex items-center gap-1 flex-wrap">
                      {triggerInfo.signals.map((s, j) => (
                        <span key={j} className="rounded bg-accent/10 px-1.5 py-0.5 text-[9px] text-accent/80">{cnSignal(s)}</span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* K 线内容 */}
            <div className="flex-1 overflow-auto p-4">
              <StockPanel
                symbol={symbol}
                height={420}
                showIntraday={showIntraday}
                onSelectDate={() => { if (!showIntraday) setShowIntraday(true) }}
                dateRange={dateRange}
                onMonitor={() => setShowMonitorEditor(true)}
                inWatchlist={inWatchlist}
                onToggleWatchlist={() => toggleWatchlist.mutate()}
              />
            </div>

            {/* 加监控编辑器弹层 */}
            <AnimatePresence>
              {showMonitorEditor && symbol && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="absolute inset-0 z-20 flex items-start justify-center overflow-auto bg-black/40 p-4"
                  onClick={() => setShowMonitorEditor(false)}
                >
                  <div className="mt-8 w-full max-w-2xl" onClick={e => e.stopPropagation()}>
                    <RuleEditor
                      rule={null}
                      simple
                      preset={{
                        scope: 'symbols',
                        symbols: [symbol],
                        type: 'signal',
                        logic: 'or',
                      }}
                      onClose={() => setShowMonitorEditor(false)}
                      onSaved={() => setShowMonitorEditor(false)}
                    />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )
}
