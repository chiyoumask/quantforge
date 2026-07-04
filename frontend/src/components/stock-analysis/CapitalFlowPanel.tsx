/**
 * 个股资金流向面板 — 主力净流入日柱状图 + 当日超大/大/中/小单分布。
 * 数据: GET /api/market/capital-flow/{symbol}
 */
import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import * as echarts from 'echarts'
import { Loader2 } from 'lucide-react'
import { api, type CapitalFlowRow } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'

function fmtAmt(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  const abs = Math.abs(v)
  const sign = v < 0 ? '-' : ''
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)} 亿`
  if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(2)} 万`
  return `${sign}${abs.toFixed(0)}`
}

export function CapitalFlowPanel({ symbol, days = 30 }: { symbol: string; days?: number }) {
  const q = useQuery({
    queryKey: QK.capitalFlow(symbol, days),
    queryFn: () => api.capitalFlow(symbol, days),
    enabled: !!symbol,
    staleTime: 60_000,
  })
  const ref = useRef<HTMLDivElement>(null)

  const rows: CapitalFlowRow[] = q.data?.rows ?? []
  const latest = rows[rows.length - 1]

  useEffect(() => {
    if (!ref.current || rows.length === 0) return
    const chart = echarts.init(ref.current)
    chart.setOption({
      grid: { left: 56, right: 16, top: 20, bottom: 28 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: any) => {
          const p = params[0]
          const v = p.value as number
          return `${p.axisValue}<br/>主力净流入: <b style="color:${v >= 0 ? '#F23645' : '#00B578'}">${fmtAmt(v)}</b>`
        },
      },
      xAxis: {
        type: 'category',
        data: rows.map(r => r.date.slice(5)),
        axisLabel: { color: '#A1A1AA', fontSize: 10, interval: Math.floor(rows.length / 6) },
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#A1A1AA', fontSize: 10, formatter: (v: number) => fmtAmt(v) },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } },
      },
      series: [{
        type: 'bar',
        data: rows.map(r => r.main ?? 0),
        // A 股惯例: 红涨绿跌; 净流入>0 红, <0 绿
        itemStyle: { color: (p: any) => (p.value >= 0 ? '#F23645' : '#00B578') },
        barWidth: '60%',
      }],
    })
    const ro = new ResizeObserver(() => chart.resize())
    ro.observe(ref.current)
    return () => { ro.disconnect(); chart.dispose() }
  }, [rows])

  if (q.isLoading) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="h-5 w-5 animate-spin text-muted" /></div>
  }
  if (rows.length === 0) {
    return <div className="py-12 text-center text-sm text-muted">暂无资金流向数据 (东财 datacenter 未返回, 可能非交易日或接口暂不可达)。</div>
  }

  const sumMain = rows.reduce((s, r) => s + (r.main ?? 0), 0)
  const units: { label: string; v: number | null; cls: string }[] = [
    { label: '超大单', v: latest?.super_large ?? null, cls: 'text-bull' },
    { label: '大单', v: latest?.large ?? null, cls: 'text-bull' },
    { label: '中单', v: latest?.medium ?? null, cls: 'text-muted' },
    { label: '小单', v: latest?.small ?? null, cls: 'text-bear' },
  ]

  return (
    <div className="space-y-3">
      {/* 当日分布 */}
      <div className="grid grid-cols-5 gap-2">
        <div className="rounded-btn bg-elevated/40 px-3 py-2">
          <div className="text-[10px] text-muted">主力净流入</div>
          <div className={cn('text-sm font-mono font-bold', (latest?.main ?? 0) >= 0 ? 'text-bull' : 'text-bear')}>
            {fmtAmt(latest?.main ?? null)}
          </div>
        </div>
        {units.map(u => (
          <div key={u.label} className="rounded-btn bg-elevated/40 px-3 py-2">
            <div className="text-[10px] text-muted">{u.label}</div>
            <div className={cn('text-sm font-mono', u.cls)}>{fmtAmt(u.v)}</div>
          </div>
        ))}
      </div>
      {/* 区间累计 */}
      <div className="text-[11px] text-muted">
        近 {rows.length} 日主力累计净流入 <span className={cn('font-mono font-medium', sumMain >= 0 ? 'text-bull' : 'text-bear')}>{fmtAmt(sumMain)}</span>
      </div>
      {/* 柱状图 */}
      <div ref={ref} className="h-[360px] w-full" />
    </div>
  )
}
