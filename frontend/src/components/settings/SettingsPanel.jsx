import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'

const API = '/api'

const BENCHMARKS = [
  { value: '^GSPC', label: 'S&P 500 (^GSPC)' },
  { value: '^DJI', label: 'Dow Jones (^DJI)' },
  { value: '^IXIC', label: 'NASDAQ (^IXIC)' },
  { value: '^RUT', label: 'Russell 2000 (^RUT)' },
  { value: '^NSEI', label: 'NIFTY 50 (^NSEI)' },
  { value: '^NSEBANK', label: 'NIFTY Bank (^NSEBANK)' },
]

const EVENT_WINDOWS = [
  { label: 'Estimation', key: 'estimation_window', suffix: 'days' },
  { label: 'Pre-Event', key: 'pre_event_window', suffix: 'days' },
  { label: 'Post-Event', key: 'post_event_window', suffix: 'days' },
  { label: 'Recovery Max', key: 'recovery_max_days', suffix: 'days' },
]

const CAR_WINDOWS = [
  { label: 'Short Start', key: 'car_short_start' },
  { label: 'Short End', key: 'car_short_end' },
  { label: 'Long Start', key: 'car_long_start' },
  { label: 'Long End', key: 'car_long_end' },
]

const THRESHOLDS = [
  { label: 'Critical (<)', key: 'threshold_critical' },
  { label: 'High (<)', key: 'threshold_high' },
  { label: 'Medium (<)', key: 'threshold_medium' },
]

export function SettingsPanel({ config, setConfig, presets, onLoadPresets }) {
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [dataSourceConfig, setDataSourceConfig] = useState({
    primary_source: 'yfinance',
    alpha_vantage_key: '',
    enable_fallback: true,
    cache_ttl_hours: 24,
  })
  const [sourceStatus, setSourceStatus] = useState(null)
  const [testResult, setTestResult] = useState(null)
  const [testTicker, setTestTicker] = useState('MSFT')
  const [saveFeedback, setSaveFeedback] = useState('')

  useEffect(() => {
    onLoadPresets()
    loadSourceStatus()
  }, [])

  const loadSourceStatus = async () => {
    try {
      const res = await fetch(`${API}/data-sources`)
      if (!res.ok) return
      setSourceStatus(await res.json())
    } catch (e) { console.error('Failed to load source status:', e) }
  }

  const applyPreset = (preset) => setConfig(preset.config)

  const testSource = async (sourceName) => {
    setTestResult(null)
    try {
      const res = await fetch(`${API}/data-sources/test/${encodeURIComponent(sourceName)}?ticker=${encodeURIComponent(testTicker)}`)
      if (!res.ok) {
        let detail = `Server error (${res.status})`
        try {
          const err = await res.json()
          detail = err.detail || detail
        } catch {}
        setTestResult({ source: sourceName, success: false, error: detail })
        return
      }
      setTestResult(await res.json())
    } catch (e) {
      setTestResult({ source: sourceName, success: false, error: e.message })
    }
  }

  const saveSourceConfig = async () => {
    try {
      const res = await fetch(`${API}/data-sources/configure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dataSourceConfig),
      })
      setSourceStatus(await res.json())
      setSaveFeedback('Saved!')
      setTimeout(() => setSaveFeedback(''), 2500)
    } catch (e) { console.error('Failed to save source config:', e) }
  }

  return (
    <div className="space-y-6">
      <Card className="terminal-card corner-accent fade-in stagger-1">
        <CardHeader className="flex flex-row items-center justify-between pb-4">
          <CardTitle className="text-sm font-semibold text-foreground flex items-center gap-2 font-sans">
            <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            </svg>
            Analysis Settings
          </CardTitle>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-xs text-secondary-foreground hover:text-foreground"
          >
            {showAdvanced ? 'Hide' : 'Advanced'}
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium text-foreground mb-1.5 block font-sans">
              Quick Presets
            </label>
            {presets.length === 0 ? (
              <p className="text-xs text-secondary-foreground py-2">No presets available.</p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {presets.map((p) => (
                  <button
                    key={p.name}
                    onClick={() => applyPreset(p)}
                    className="bg-surface border border-border rounded-lg px-3 py-2 text-xs text-left hover:border-cyan-500/40 transition-all duration-200 hover:bg-surface-raised"
                  >
                    <div className="text-foreground font-medium capitalize">{p.name}</div>
                    <div className="text-secondary-foreground mt-0.5">{p.description}</div>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="space-y-3">
            <div>
              <label className="text-sm font-medium text-foreground mb-1.5 block font-sans">
                Market Benchmark
              </label>
              <Select value={config.benchmark} onValueChange={(v) => setConfig({ ...config, benchmark: v })}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {BENCHMARKS.map((b) => (
                    <SelectItem key={b.value} value={b.value}>
                      {b.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-sm font-medium text-foreground mb-1.5 block font-sans">
                  Stock Data Start
                </label>
                <Input
                  type="date"
                  value={config.start_date}
                  onChange={(e) => setConfig({ ...config, start_date: e.target.value })}
                />
              </div>
              <div>
                <label className="text-sm font-medium text-foreground mb-1.5 block font-sans">
                  Min Records
                </label>
                <Input
                  type="number"
                  value={config.min_records}
                  onChange={(e) => setConfig({ ...config, min_records: parseInt(e.target.value) || 0 })}
                />
              </div>
            </div>
          </div>

          {showAdvanced && (
            <div className="space-y-3 pt-4 mt-4 border-t border-border">
              <h4 className="text-xs font-semibold text-dim">Event Windows</h4>
              <div className="grid grid-cols-2 gap-3">
                {EVENT_WINDOWS.map(({ label, key, suffix }) => (
                  <div key={key}>
                    <label className="text-sm font-medium text-foreground mb-1.5 block font-sans">
                      {label}
                    </label>
                    <div className="relative">
                      <Input
                        type="number"
                        value={config[key]}
                        onChange={(e) => setConfig({ ...config, [key]: parseInt(e.target.value) || 0 })}
                        className="pr-10"
                      />
                      <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[0.65rem] text-dim">
                        {suffix}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              <h4 className="text-xs font-semibold text-dim pt-1">CAR Windows</h4>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {CAR_WINDOWS.map(({ label, key }) => (
                  <div key={key}>
                    <label className="text-sm font-medium text-foreground mb-1.5 block font-sans">
                      {label}
                    </label>
                    <Input
                      type="number"
                      value={config[key]}
                      onChange={(e) => setConfig({ ...config, [key]: parseInt(e.target.value) || 0 })}
                    />
                  </div>
                ))}
              </div>

              <h4 className="text-xs font-semibold text-dim pt-1">
                Severity Thresholds
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {THRESHOLDS.map(({ label, key }) => (
                  <div key={key}>
                    <label className="text-sm font-medium text-foreground mb-1.5 block font-sans">
                      {label}
                    </label>
                    <Input
                      type="number"
                      step="0.01"
                      value={config[key]}
                      onChange={(e) => setConfig({ ...config, [key]: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="terminal-card corner-accent fade-in stagger-2">
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2 font-sans">
            <svg className="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
            </svg>
            Data Sources
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {sourceStatus && (
            <div className="mb-4 space-y-1.5" role="list">
              {Object.entries(sourceStatus.sources || {}).map(([name, info]) => (
                <div
                  key={name}
                  role="listitem"
                  className="flex items-center justify-between bg-surface rounded-lg px-3 py-2 border border-border"
                >
                  <div className="flex items-center gap-2.5">
                    <div className={cn('status-dot w-2 h-2 rounded-full', info.available ? 'bg-emerald-400' : 'bg-dim/50')} />
                    <span className="text-xs text-foreground font-medium capitalize">
                      {name.replace(/_/g, ' ')}
                    </span>
                    <span className="text-[0.65rem] text-secondary-foreground">
                      priority {info.priority + 1}
                    </span>
                  </div>
                  {info.reason && (
                    <span className="text-[0.65rem] text-amber-400">{info.reason}</span>
                  )}
                </div>
              ))}
            </div>
          )}

          <div className="space-y-3">
            <div>
              <label className="text-sm font-medium text-foreground mb-1.5 block font-sans">
                Primary Source
              </label>
              <Select
                value={dataSourceConfig.primary_source}
                onValueChange={(v) => setDataSourceConfig({ ...dataSourceConfig, primary_source: v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="yfinance">yfinance (free, no key)</SelectItem>
                  <SelectItem value="alphavantage">Alpha Vantage (free key)</SelectItem>
                  <SelectItem value="nse_india">NSE India</SelectItem>
                  <SelectItem value="yahoo_scrape">Yahoo Finance Scraping</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium text-foreground mb-1.5 block font-sans">
                Alpha Vantage API Key
              </label>
              <Input
                type="password"
                placeholder="Optional API key"
                value={dataSourceConfig.alpha_vantage_key}
                onChange={(e) =>
                  setDataSourceConfig({ ...dataSourceConfig, alpha_vantage_key: e.target.value })
                }
              />
              <p className="text-[0.65rem] text-secondary-foreground mt-1">
                Free at <span className="text-cyan">alphavantage.co</span> (25 calls/day)
              </p>
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <Switch
                checked={dataSourceConfig.enable_fallback}
                onCheckedChange={(v) => setDataSourceConfig({ ...dataSourceConfig, enable_fallback: v })}
              />
              <span className="text-xs text-secondary-foreground">Enable automatic fallback</span>
            </label>
            <div className="flex items-center gap-3">
              <Button onClick={saveSourceConfig} className="flex-1">
                Save Config
              </Button>
              {saveFeedback && (
                <span className="text-xs text-emerald-400 animate-pulse" role="status">
                  {saveFeedback}
                </span>
              )}
            </div>
          </div>

          <div className="pt-4 mt-4 border-t border-border">
            <h4 className="text-xs font-semibold text-dim mb-3">Test a Source</h4>
            <Input
              type="text"
              placeholder="Ticker (e.g., MSFT, TCS.NS)"
              value={testTicker}
              onChange={(e) => setTestTicker(e.target.value)}
              className="mb-3"
            />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {['auto', 'yfinance', 'alphavantage', 'nse_india', 'yahoo_scrape'].map((src) => (
                <button
                  key={src}
                  onClick={() => testSource(src)}
                  className={cn(
                    'bg-surface border border-border rounded-lg px-3 py-2 text-xs text-foreground hover:border-cyan-500/40 transition-all duration-200 capitalize',
                    testResult?.source === src &&
                      (testResult.success ? 'border-emerald-500/40' : 'border-red-500/40')
                  )}
                >
                  {src === 'auto' ? 'Auto (Fallback Chain)' : src.replace('_', ' ')}
                </button>
              ))}
            </div>
            {testResult && (
              <div
                role="alert"
                className={cn(
                  'mt-3 p-3 rounded-lg text-xs fade-in',
                  testResult.success
                    ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400'
                    : 'bg-red-500/10 border border-red-500/20 text-red-400'
                )}
              >
                {testResult.success ? (
                  <div>
                    <div className="font-semibold mb-0.5">
                      {testResult.source} — {testResult.rows} rows
                    </div>
                    <div>{testResult.elapsed_seconds}s elapsed</div>
                  </div>
                ) : (
                  <div>
                    <div className="font-semibold mb-0.5">{testResult.source} — Failed</div>
                    <div className="opacity-80">{testResult.error}</div>
                  </div>
                )}
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
