/**
 * 龙虎榜页 — 每日龙虎榜明细 (东财 datacenter)。
 * 日期选择 + 表格 (股票/上榜原因/净买入/买入额/卖出额), 点行跳个股分析。
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Loader2, Trophy } from 'lucide-react'
import { api, type DragonTigerRow } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { PageHeader } from '@/components/PageHeader'
import { cn } from '@/lib/cn'

function toSymbol(code: string): string {
  const c = code.trim()
  if (c.startsWith('60') || c.startsWith('68') || c.startsWith('9')) return `${c}.SH`
  if (c.startsWith('00') || c.startsWith('30') || c.startsWith('20')) return `${c}.SZ`
  if (c.startsWith('8') || c.startsWith('43') || c.startsWith('87')) return `${c}.BJ`
  return `${c}.SZ`
}

function fmtAmt(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  const abs = Math.abs(v)
  const sign = v < 0 ? '-' : ''
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)} 亿`
  if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(2)} 万`
  return `${sign}${abs.toFixed(0)}`
}

export function DragonTiger() {
  const navigate = useNavigate()
  const today = new Date().toISOString().slice(0, 10)
  const [date, setDate] = useState(today)

  const { data, isLoading } = useQuery({
    queryKey: QK.dragonTiger(date),
    queryFn: () => api.dragonTiger(date),
    staleTime: 5 * 60_000,
  })
  const rows: DragonTigerRow[] = data?.rows ?? []

  return (
    <>
      <PageHeader title="龙虎榜" subtitle="每日龙虎榜明细 (东财 datacenter)。点行进入个股分析。" />
      <div className="px-8 py-6 space-y-4">
        {/* 日期选择 */}
        <div className="flex items-center gap-3">
          <label className="text-sm text-secondary">交易日</label>
          <input
            type="date"
            value={date}
            max={today}
            onChange={e => setDate(e.target.value)}
            className="h-9 rounded-btn border border-border bg-base px-3 text-sm text-foreground outline-none focus:border-accent/50"
          />
          <span className="text-xs text-muted">共 {rows.length} 条</span>
        </div>

        {/* 表格 */}
        <div className="rounded-card border border-border bg-surface overflow-hidden">
          {isLoading ? (
            <div className="flex items-center justify-center py-16"><Loader2 className="h-5 w-5 animate-spin text-muted" /></div>
          ) : rows.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted">
              <Trophy className="h-8 w-8 mb-2 opacity-40" />
              <span className="text-sm">该日无龙虎榜数据 (可能非交易日或接口暂不可达)</span>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-elevated/40 text-[11px] uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-4 py-2.5 text-left font-medium">代码</th>
                  <th className="px-4 py-2.5 text-left font-medium">名称</th>
                  <th className="px-4 py-2.5 text-left font-medium">上榜原因</th>
                  <th className="px-4 py-2.5 text-right font-medium">买入额</th>
                  <th className="px-4 py-2.5 text-right font-medium">卖出额</th>
                  <th className="px-4 py-2.5 text-right font-medium">净买入</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map((r, i) => {
                  const sym = toSymbol(r.code)
                  const net = r.net_amount ?? 0
                  return (
                    <tr
                      key={`${r.code}-${i}`}
                      onClick={() => navigate(`/stock-analysis?symbol=${encodeURIComponent(sym)}`)}
                      className="cursor-pointer hover:bg-elevated/30"
                    >
                      <td className="px-4 py-2 font-mono text-secondary">{r.code}</td>
                      <td className="px-4 py-2 font-medium text-foreground">{r.name}</td>
                      <td className="px-4 py-2 text-muted text-xs max-w-[280px] truncate" title={r.reason}>{r.reason || '—'}</td>
                      <td className="px-4 py-2 text-right font-mono text-secondary">{fmtAmt(r.buy_amount)}</td>
                      <td className="px-4 py-2 text-right font-mono text-secondary">{fmtAmt(r.sell_amount)}</td>
                      <td className={cn('px-4 py-2 text-right font-mono font-medium', net >= 0 ? 'text-bull' : 'text-bear')}>{fmtAmt(r.net_amount)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  )
}
