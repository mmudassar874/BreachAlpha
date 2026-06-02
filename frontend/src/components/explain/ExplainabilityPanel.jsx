import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'

export function ExplainabilityPanel({ data }) {
  if (!data) return null

  const steps = data.steps || []
  const limitations = data.limitations || []
  const featureContributions = data.feature_contributions || {}

  return (
    <div className="terminal-card corner-accent p-6 fade-in">
      <div className="flex items-center gap-2 mb-5">
        <svg className="w-5 h-5 text-cyan" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
        </svg>
        <h3 className="text-lg font-bold font-mono text-foreground">
          How the Risk Score is Calculated
        </h3>
      </div>

      <div className="rounded-xl p-4 mb-6 bg-cyan-500/5 border border-cyan-500/15">
        <h4 className="text-xs font-semibold tracking-wider uppercase mb-2 text-cyan">
          Methodology
        </h4>
        <p className="text-xs leading-relaxed text-secondary-foreground">
          {data.methodology}
        </p>
      </div>

      <div className="space-y-3">
        {steps.map((step, i) => (
          <div
            key={i}
            className="rounded-xl p-4 bg-surface border border-border hover:border-border-bright transition-all duration-200"
          >
            <div className="flex items-start gap-3">
              <div className="w-7 h-7 rounded flex items-center justify-center shrink-0 mt-0.5 bg-cyan-500/10 border border-cyan-500/20">
                <span className="text-xs font-bold text-cyan">
                  {step.step_number}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <h5 className="text-sm font-semibold mb-1 font-mono text-foreground">
                  {step.name}
                </h5>
                <p className="text-xs mb-2 text-secondary-foreground">
                  {step.description}
                </p>
                <div className="rounded-lg p-3 mb-2 text-xs overflow-x-auto bg-background border border-border font-mono text-cyan">
                  {step.formula}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-2">
                  {Object.entries(step.inputs).map(([key, val]) => (
                    <div key={key} className="text-xs">
                      <span className="text-secondary-foreground">{key}: </span>
                      <span className="text-secondary-foreground">
                        {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                      </span>
                    </div>
                  ))}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-secondary-foreground">Output:</span>
                  <span className="text-sm font-semibold font-mono text-foreground">
                    {typeof step.output === 'number' ? step.output.toFixed(6) : String(step.output)}
                  </span>
                </div>
                <div className="mt-2 text-xs rounded-lg p-2 bg-surface text-secondary-foreground">
                  {step.interpretation}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 rounded-xl p-4 bg-surface border border-border">
        <h4 className="text-xs font-semibold tracking-wider uppercase mb-3 font-mono text-dim">
          Feature Contributions
        </h4>
        <div className="space-y-2">
          {Object.entries(featureContributions)
            .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
            .map(([feat, val]) => (
              <div key={feat} className="flex items-center gap-3">
                <span className="w-36 text-[0.6875rem] truncate shrink-0 text-secondary-foreground">
                  {feat.replace(/_/g, ' ')}
                </span>
                <div className="flex-1 h-1.5 rounded-full overflow-hidden bg-border">
                  <div
                    className="h-full rounded-full transition-all duration-700 ease-out"
                    style={{
                      width: `${Math.min(Math.abs(val) * 500, 100)}%`,
                      backgroundColor: val < 0 ? 'hsl(0 72% 51%)' : 'hsl(142 71% 45%)',
                      marginLeft: val < 0 ? 'auto' : '0',
                    }}
                  />
                </div>
                <span
                  className="w-16 text-[0.6875rem] text-right font-mono shrink-0"
                  style={{ color: val < 0 ? 'hsl(0 72% 51%)' : 'hsl(142 71% 45%)' }}
                >
                  {val > 0 ? '+' : ''}{val.toFixed(4)}
                </span>
              </div>
            ))}
        </div>
      </div>

      <div className="mt-6 rounded-xl p-4 bg-amber-500/5 border border-amber-500/15">
        <h4 className="text-xs font-semibold tracking-wider uppercase mb-2 text-amber-400">
          Limitations
        </h4>
        <ul className="space-y-1">
          {limitations.map((lim, i) => (
            <li key={i} className="text-xs text-secondary-foreground flex items-start gap-2">
              <span className="text-amber-400 mt-0.5 shrink-0">*</span>
              {lim}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
