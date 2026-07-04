/**
 * 融资融券面板 — 两市融资/融券余额趋势 (datacenter 为两市汇总, 非个股级)。
 * 数据: GET /api/market/margin
 */
import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import * as echarts from 'echarts'
import { Loader2 } from 'lucide-react'
import { api, type MarginRow } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

function fmtAmt(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)} 亿`
  if (v >= 1e4) return `${(v / 1e4).toFixed(2)} 万`
  return v.toFixed(0)
}

export function MarginPanel({ days = 30 }: { days?: number }) {
  const q = useQuery({
    queryKey: QK.marketMargin(days),
    queryFn: () => api.marketMargin(days),
    staleTime: 5 * 60_000,
  })
  const ref = useRef<HTMLDivElement>(null)
  const rows: MarginRow[] = q.data?.rows ?? []

  useEffect(() => {
    if (!ref.current || rows.length === 0) return
    const chart = echarts.init(ref.current)
    chart.setOption({
      grid: { left: 56, right: 16, top: 24, bottom: 28 },
      legend: { data: ['融资余额', '融券余额'], textStyle: { color: '#A1A1AA', fontSize: 11 }, top: 0 },
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          let s = params[0].axisValue + '<br/>'
          for (const p of params) s += `${p.marker} ${p.seriesName}: <b>${fmtAmt(p.value)}</b><br/>`
          return s
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
      series: [
        { name: '融资余额', type: 'line', smooth: true, symbol: 'none', data: rows.map(r => r.rzye ?? 0), lineStyle: { color: '#3B82F6' }, areaStyle: { color: 'rgba(59,130,246,0.12)' } },
        { name: '融券余额', type: 'line', smooth: true, symbol: 'none', data: rows.map(r => r.rqye ?? 0), lineStyle: { color: '#F59E0B' } },
      ],
    })
    const ro = new ResizeObserver(() => chart.resize())
    ro.observe(ref.current)
    return () => { ro.disconnect(); chart.dispose() }
  }, [rows])

  if (q.isLoading) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="h-5 w-5 animate-spin text-muted" /></div>
  }
  if (rows.length === 0) {
    return <div className="py-12 text-center text-sm text-muted">暂无融资融券数据 (东财 datacenter 未返回, 可能非交易日或接口暂不可达)。</div>
  }

  const latest = rows[rows.length - 1]
  return (
    <div className="space-y-3">
      <div className="rounded-btn bg-elevated/40 px-3 py-2 text-[11px] text-muted">
        注: 东财 datacenter 返回为两市汇总数据 (非个股级)。最新 ({latest.date}): 融资余额 <span className="font-mono text-foreground">{fmtAmt(latest.rzye)}</span> · 融券余额 <span className="font-mono text-foreground">{fmtAmt(latest.rqye)}</span>
      </div>
      <div ref={ref} className="h-[360px] w-full" />
    </div>
  )
}
