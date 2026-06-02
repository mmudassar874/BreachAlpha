import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { cn, SEVERITY_COLORS, SEVERITY_CLASSES } from '@/lib/utils'

export function BatchResults({ data }) {
  const [expandedRow, setExpandedRow] = useState(null)
  const [sortKey, setSortKey] = useState(null)
  const [sortDir, setSortDir] = useState('asc')

  if (!data) return null

  const toggleSort = (key) => {
    setSortDir((d) => (sortKey === key ? (d === 'asc' ? 'desc' : 'asc') : 'asc'))
    setSortKey(key)
  }

  const sorted = [...(data.results || [])].sort((a, b) => {
    if (!sortKey) return 0
    let av = a[sortKey]
    let bv = b[sortKey]
    if (typeof av === 'string') av = av.toLowerCase()
    if (typeof bv === 'string') bv = bv.toLowerCase()
    if (av == null) return 1
    if (bv == null) return -1
    const cmp = av < bv ? -1 : av > bv ? 1 : 0
    return sortDir === 'desc' ? -cmp : cmp
  })

  const SortIcon = ({ active }) =>
    active ? (
      <svg className="w-3 h-3 inline ml-0.5 text-cyan" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={sortDir === 'asc' ? 'M5 15l7-7 7 7' : 'M19 9l-7 7-7-7'} />
      </svg>
    ) : (
      <svg className="w-3 h-3 inline ml-0.5 text-dim/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
      </svg>
    )

  const Th = ({ sort, children, className }) => (
    <th
      className={`text-left py-2 px-3 text-dim font-medium select-none ${
        sort ? 'cursor-pointer hover:text-foreground transition-colors duration-200' : ''
      } ${className || ''}`}
      onClick={sort ? () => toggleSort(sort) : undefined}
      aria-sort={sortKey === sort ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined}
      tabIndex={sort ? 0 : undefined}
      onKeyDown={sort ? (e) => e.key === 'Enter' && toggleSort(sort) : undefined}
    >
      {children}
      {sort && <SortIcon active={sortKey === sort} />}
    </th>
  )

  const escapeCSV = (val) => {
    let str = String(val ?? '')
    // Sanitize CSV formula injection: prefix formula characters
    const trimmed = str.trimStart()
    if (trimmed.startsWith('=') || trimmed.startsWith('+') || trimmed.startsWith('-') || trimmed.startsWith('@')) {
      str = '\t' + str
    }
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
      return `"${str.replace(/"/g, '""')}"`
    }
    return str
  }

  const exportCSV = () => {
    const headers = [
      'Company', 'Ticker', 'Breach Date', 'Records', 'Risk Score', 'Prediction',
      'Low%', 'Medium%', 'High%', 'Critical%', 'Confidence', 'Status',
    ]
    const rows = data.results.map((r) => [
      r.company, r.ticker, r.breach_date, r.records_affected,
      r.risk_score, r.prediction,
      r.probabilities ? (r.probabilities.low * 100).toFixed(1) : '',
      r.probabilities ? (r.probabilities.medium * 100).toFixed(1) : '',
      r.probabilities ? (r.probabilities.high * 100).toFixed(1) : '',
      r.probabilities ? (r.probabilities.critical * 100).toFixed(1) : '',
      r.confidence, r.status,
    ])
    const csv = [headers, ...rows].map((r) => r.map(escapeCSV).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'breachalpha_results.csv'
    a.click()
  }

  return (
    <div className="terminal-card corner-accent p-6 fade-in">
      <div className="flex items-center justify-between mb-4">
        <h4 className="text-xs font-semibold tracking-wider uppercase font-mono text-dim">
          Batch Results
        </h4>
        <Button variant="secondary" size="sm" onClick={exportCSV} className="text-xs py-1.5 px-3 gap-1.5">
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Export CSV
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        {[
          { label: 'Total', value: data.total, color: 'text-foreground' },
          { label: 'Analyzed', value: data.analyzed, color: 'text-emerald-400' },
          { label: 'Failed', value: data.failed, color: 'text-red-400' },
        ].map((s) => (
          <div key={s.label} className="p-3 text-center bg-surface border border-border rounded-lg">
            <div className={`text-lg font-bold font-mono ${s.color}`}>{s.value}</div>
            <div className="text-[0.625rem] tracking-wider uppercase text-dim">{s.label}</div>
          </div>
        ))}
      </div>

      {data.results.length === 0 ? (
        <div className="py-16 text-center">
          <svg className="w-12 h-12 text-dim mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <h3 className="text-sm font-semibold text-foreground mb-1">No results</h3>
          <p className="text-xs text-secondary-foreground">
            The dataset did not produce any analyzable results. Check the file format and try again.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto -mx-2 max-h-[32rem] overflow-y-auto">
          <table className="w-full text-xs" role="table">
            <thead className="sticky top-0 bg-background z-10">
              <tr className="border-b border-border/50">
                <Th sort="company">Company</Th>
                <Th sort="ticker">Ticker</Th>
                <Th sort="breach_date">Date</Th>
                <Th sort="risk_score" className="text-right">Score</Th>
                <Th>Severity</Th>
                <Th className="min-w-[160px]">Probabilities</Th>
                <Th sort="confidence" className="text-right">Conf</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((r, i) => (
                <tr
                  key={i}
                  role="button"
                  tabIndex={0}
                  aria-expanded={expandedRow === i}
                  onClick={() => setExpandedRow(expandedRow === i ? null : i)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpandedRow(expandedRow === i ? null : i); } }}
                  className="border-b border-border/30 hover:bg-surface/50 cursor-pointer transition-colors duration-200"
                >
                  <td className="py-2 px-3 text-foreground font-medium">{r.company}</td>
                  <td className="py-2 px-3 text-secondary-foreground">{r.ticker}</td>
                  <td className="py-2 px-3 text-secondary-foreground whitespace-nowrap">{r.breach_date}</td>
                  <td
                    className="py-2 px-3 text-right font-mono font-bold"
                    style={{ color: SEVERITY_COLORS[r.prediction] || '#5a6a82' }}
                  >
                    {r.risk_score || '-'}
                  </td>
                  <td className="py-2 px-3">
                    <span
                      className={cn(
                        'text-[0.65rem] px-1.5 py-0.5 rounded-full font-mono',
                        r.prediction && SEVERITY_CLASSES[r.prediction]
                          ? SEVERITY_CLASSES[r.prediction]
                          : 'bg-surface text-secondary-foreground border border-border'
                      )}
                    >
                      {r.prediction?.toUpperCase() || '-'}
                    </span>
                  </td>
                  <td className="py-2 px-3 min-w-[130px]">
                    {r.probabilities && Object.keys(r.probabilities).length > 0 ? (
                      <div
                        className="flex gap-0.5 items-center"
                        aria-label={Object.entries(r.probabilities)
                          .map(([k, v]) => `${k}: ${(v * 100).toFixed(0)}%`)
                          .join(', ')}
                      >
                        {['low', 'medium', 'high', 'critical'].map((sev) => (
                          <div key={sev} className="flex-1" title={`${sev}: ${(r.probabilities[sev] * 100).toFixed(1)}%`}>
                            <div className="h-1.5 bg-border/50 rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full transition-all duration-700 ease-out"
                                style={{
                                  width: `${(r.probabilities[sev] || 0) * 100}%`,
                                  backgroundColor: SEVERITY_COLORS[sev],
                                }}
                              />
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <span className="text-dim/50">-</span>
                    )}
                  </td>
                  <td className="py-2 px-3 text-right text-secondary-foreground">
                    {r.confidence ? `${(r.confidence * 100).toFixed(0)}%` : '-'}
                  </td>
                  <td className="py-2 px-3">
                    {r.status === 'ok' ? (
                      <span className="text-emerald-400 text-[0.65rem] font-medium">OK</span>
                    ) : (
                      <span className="text-red-400 text-[0.65rem]" title={r.error}>
                        {r.status}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.results.length > 0 && (
        <p className="text-[0.65rem] text-dim mt-3">
          Click column headers to sort. Click a row to expand.
        </p>
      )}
    </div>
  )
}
