export function DatasetPreview({ data }) {
  if (!data) return null

  return (
    <div className="terminal-card corner-accent p-6 fade-in">
      <h4 className="text-xs font-semibold tracking-wider uppercase mb-4 font-mono text-dim">
        Dataset Preview
      </h4>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
        {[
          { label: 'Original Rows', value: data.original_rows, color: 'text-foreground' },
          { label: 'Cleaned Rows', value: data.cleaned_rows, color: 'text-emerald-400' },
          { label: 'Ticker Match', value: `${(data.ticker_resolution_rate * 100).toFixed(0)}%`, color: 'text-cyan' },
        ].map((s) => (
          <div
            key={s.label}
            className="p-3 text-center bg-surface border border-border rounded-lg"
          >
            <div className={`text-lg font-bold font-mono ${s.color}`}>
              {s.value}
            </div>
            <div className="text-[0.625rem] tracking-wider uppercase text-dim">
              {s.label}
            </div>
          </div>
        ))}
      </div>
      {data.warnings?.length > 0 && (
        <div className="mb-4 space-y-1">
          {data.warnings.slice(0, 5).map((w, i) => (
            <div key={i} className="text-xs text-amber-400 bg-amber-500/8 px-3 py-1.5 rounded-lg">
              {w}
            </div>
          ))}
        </div>
      )}
      {data.preview?.length > 0 && (
        <div className="overflow-x-auto -mx-2">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border/50">
                {Object.keys(data.preview[0]).map((col) => (
                  <th
                    key={col}
                    className="text-left py-2 px-3 text-dim font-medium capitalize whitespace-nowrap"
                  >
                    {col.replace(/_/g, ' ')}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.preview.map((row, i) => (
                <tr key={i} className="border-b border-border/30 hover:bg-surface/50 transition-colors">
                  {Object.values(row).map((val, j) => (
                    <td key={j} className="py-2 px-3 text-secondary-foreground whitespace-nowrap">
                      {typeof val === 'number' ? val.toLocaleString() : val}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
