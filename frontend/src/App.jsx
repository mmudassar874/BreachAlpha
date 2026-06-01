import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, BarElement, PointElement,
  LineElement, ArcElement, Title, Tooltip, Legend, Filler,
} from 'chart.js'
import { Bar } from 'react-chartjs-2'

ChartJS.register(
  CategoryScale, LinearScale, BarElement, PointElement,
  LineElement, ArcElement, Title, Tooltip, Legend, Filler
)

const API = '/api'

const SEVERITY_COLORS = {
  low: '#10b981', medium: '#f59e0b', high: '#f97316', critical: '#ef4444',
}
const SEVERITY_BG = {
  low: 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/25',
  medium: 'bg-amber-500/15 text-amber-400 border border-amber-500/25',
  high: 'bg-orange-500/15 text-orange-400 border border-orange-500/25',
  critical: 'bg-red-500/15 text-red-400 border border-red-500/25',
}

function cn(...classes) {
  return classes.filter(Boolean).join(' ')
}

function Skeleton({ className }) {
  return <div className={cn('skeleton', className)} />
}

function RiskGauge({ score, prediction }) {
  const color = SEVERITY_COLORS[prediction] || '#64748b'
  const circumference = 2 * Math.PI * 70
  const offset = circumference - (score / 100) * circumference
  return (
    <div className="relative w-44 h-44 mx-auto fade-in" role="img" aria-label={`Risk score: ${score} out of 100, severity: ${prediction}`}>
      <svg className="w-full h-full" style={{ transform: 'rotate(-90deg)' }} viewBox="0 0 160 160">
        <circle cx="80" cy="80" r="70" fill="none" stroke="#1e293b" strokeWidth="10" />
        <circle cx="80" cy="80" r="70" fill="none" stroke={color} strokeWidth="10"
          strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 1s ease-out' }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold" style={{ color }}>{score}</span>
        <span className="text-xs text-slate-500 mt-0.5">/ 100</span>
      </div>
    </div>
  )
}

function ProbabilityBar({ label, probability, color }) {
  return (
    <div className="flex items-center gap-3" role="group" aria-label={`${label}: ${(probability * 100).toFixed(1)}%`}>
      <span className="w-20 text-xs text-slate-400 capitalize">{label}</span>
      <div className="flex-1 h-2.5 bg-slate-700/60 rounded-full overflow-hidden" role="meter" aria-valuenow={Math.round(probability * 100)} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-full rounded-full transition-all duration-500"
          style={{ width: `${probability * 100}%`, backgroundColor: color }} />
      </div>
      <span className="w-12 text-xs text-slate-300 text-right font-mono">{(probability * 100).toFixed(1)}%</span>
    </div>
  )
}

function FeatureCard({ label, value, unit, negative }) {
  const color = negative ? 'text-red-400' : 'text-slate-300'
  return (
    <div className="bg-slate-800/40 border border-slate-700/40 rounded-lg p-3">
      <div className="text-[0.6875rem] text-slate-500 mb-0.5">{label}</div>
      <div className={cn('text-base font-semibold font-mono', color)}>
        {typeof value === 'number' ? value.toFixed(4) : value || 'N/A'}
        {unit && <span className="text-xs text-slate-500 ml-0.5 font-normal">{unit}</span>}
      </div>
    </div>
  )
}

function TabBar({ tabs, active, onChange }) {
  return (
    <div className="flex gap-0.5 bg-slate-800/40 p-0.5 rounded-xl mb-6" role="tablist" aria-label="Analysis sections">
      {tabs.map(tab => (
        <button key={tab.id} role="tab" id={`tab-${tab.id}`} aria-selected={active === tab.id}
          aria-controls={`panel-${tab.id}`}
          onClick={() => onChange(tab.id)}
          onKeyDown={e => {
            const idx = tabs.findIndex(t => t.id === active)
            if (e.key === 'ArrowRight') onChange(tabs[(idx + 1) % tabs.length].id)
            if (e.key === 'ArrowLeft') onChange(tabs[(idx - 1 + tabs.length) % tabs.length].id)
          }}
          className={cn(
            'flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-all',
            active === tab.id
              ? 'bg-blue-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-white hover:bg-slate-700/30'
          )}>
          {tab.label}
        </button>
      ))}
    </div>
  )
}

function SettingsPanel({ config, setConfig, presets, onLoadPresets }) {
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [dataSourceConfig, setDataSourceConfig] = useState({
    primary_source: 'yfinance', alpha_vantage_key: '', enable_fallback: true, cache_ttl_hours: 24,
  })
  const [sourceStatus, setSourceStatus] = useState(null)
  const [testResult, setTestResult] = useState(null)
  const [testTicker, setTestTicker] = useState('MSFT')
  const [saveFeedback, setSaveFeedback] = useState('')

  useEffect(() => { onLoadPresets(); loadSourceStatus() }, [])

  const loadSourceStatus = async () => {
    try {
      const res = await fetch(`${API}/data-sources`)
      if (!res.ok) return
      setSourceStatus(await res.json())
    } catch {}
  }

  const applyPreset = (preset) => { setConfig(preset.config) }

  const testSource = async (sourceName) => {
    setTestResult(null)
    try {
      const res = await fetch(`${API}/data-sources/test/${sourceName}?ticker=${testTicker}`)
      if (!res.ok) {
        let detail = `Server error (${res.status})`
        try { const err = await res.json(); detail = err.detail || detail } catch {}
        setTestResult({ source: sourceName, success: false, error: detail })
        return
      }
      setTestResult(await res.json())
    } catch (e) { setTestResult({ source: sourceName, success: false, error: e.message }) }
  }

  const saveSourceConfig = async () => {
    try {
      const res = await fetch(`${API}/data-sources/configure`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dataSourceConfig),
      })
      setSourceStatus(await res.json())
      setSaveFeedback('Saved!')
      setTimeout(() => setSaveFeedback(''), 2500)
    } catch {}
  }

  return (
    <div className="space-y-6">
      <div className="card p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            </svg>
            Analysis Settings
          </h3>
          <button onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-xs text-slate-400 hover:text-white transition-colors">
            {showAdvanced ? 'Hide' : 'Advanced'}
          </button>
        </div>

        <div className="mb-4">
          <label className="label">Quick Presets</label>
          <div className="grid grid-cols-2 gap-2">
            {presets.map(p => (
              <button key={p.name} onClick={() => applyPreset(p)}
                className="bg-slate-800/50 border border-slate-700/40 rounded-lg px-3 py-2 text-xs text-left hover:border-blue-500/40 transition-colors">
                <div className="text-white font-medium capitalize">{p.name}</div>
                <div className="text-slate-500 mt-0.5">{p.description}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-3">
          <div>
            <label className="label">Market Benchmark</label>
            <select value={config.benchmark} onChange={e => setConfig({...config, benchmark: e.target.value})}
              className="input">
              <option value="^GSPC">S&P 500 (^GSPC)</option>
              <option value="^DJI">Dow Jones (^DJI)</option>
              <option value="^IXIC">NASDAQ (^IXIC)</option>
              <option value="^RUT">Russell 2000 (^RUT)</option>
              <option value="^NSEI">NIFTY 50 (^NSEI)</option>
              <option value="^NSEBANK">NIFTY Bank (^NSEBANK)</option>
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Stock Data Start</label>
              <input type="date" value={config.start_date} onChange={e => setConfig({...config, start_date: e.target.value})} className="input" />
            </div>
            <div>
              <label className="label">Min Records</label>
              <input type="number" value={config.min_records} onChange={e => setConfig({...config, min_records: parseInt(e.target.value) || 0})} className="input" />
            </div>
          </div>
        </div>

        {showAdvanced && (
          <div className="space-y-3 pt-4 mt-4 border-t border-slate-700/40">
            <h4 className="text-xs font-semibold text-slate-300">Event Windows</h4>
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: 'Estimation', key: 'estimation_window', suffix: 'days' },
                { label: 'Pre-Event', key: 'pre_event_window', suffix: 'days' },
                { label: 'Post-Event', key: 'post_event_window', suffix: 'days' },
                { label: 'Recovery Max', key: 'recovery_max_days', suffix: 'days' },
              ].map(({ label, key, suffix }) => (
                <div key={key}>
                  <label className="label">{label}</label>
                  <div className="relative">
                    <input type="number" value={config[key]}
                      onChange={e => setConfig({...config, [key]: parseInt(e.target.value) || 0})}
                      className="input pr-10" />
                    <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[0.65rem] text-slate-500">{suffix}</span>
                  </div>
                </div>
              ))}
            </div>

            <h4 className="text-xs font-semibold text-slate-300 pt-1">CAR Windows</h4>
            <div className="grid grid-cols-4 gap-2">
              {[
                { label: 'Short Start', key: 'car_short_start' }, { label: 'Short End', key: 'car_short_end' },
                { label: 'Long Start', key: 'car_long_start' }, { label: 'Long End', key: 'car_long_end' },
              ].map(({ label, key }) => (
                <div key={key}>
                  <label className="label">{label}</label>
                  <input type="number" value={config[key]}
                    onChange={e => setConfig({...config, [key]: parseInt(e.target.value) || 0})}
                    className="input" />
                </div>
              ))}
            </div>

            <h4 className="text-xs font-semibold text-slate-300 pt-1">Severity Thresholds</h4>
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: 'Critical (<)', key: 'threshold_critical', color: 'red' },
                { label: 'High (<)', key: 'threshold_high', color: 'orange' },
                { label: 'Medium (<)', key: 'threshold_medium', color: 'amber' },
              ].map(({ label, key, color }) => (
                <div key={key}>
                  <label className="label">{label}</label>
                  <input type="number" step="0.01" value={config[key]}
                    onChange={e => setConfig({...config, [key]: parseFloat(e.target.value) || 0})}
                    className="input" />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="card p-6">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <svg className="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
          </svg>
          Data Sources
        </h3>

        {sourceStatus && (
          <div className="mb-4 space-y-1.5" role="list">
            {Object.entries(sourceStatus.sources || {}).map(([name, info]) => (
              <div key={name} role="listitem" className="flex items-center justify-between bg-slate-800/40 rounded-lg px-3 py-2">
                <div className="flex items-center gap-2.5">
                  <div className={cn('status-dot', info.available ? 'bg-emerald-400' : 'bg-slate-500')} />
                  <span className="text-xs text-white font-medium capitalize">{name.replace(/_/g, ' ')}</span>
                  <span className="text-[0.65rem] text-slate-500">priority {info.priority + 1}</span>
                </div>
                {info.reason && <span className="text-[0.65rem] text-amber-400">{info.reason}</span>}
              </div>
            ))}
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label className="label">Primary Source</label>
            <select value={dataSourceConfig.primary_source}
              onChange={e => setDataSourceConfig({...dataSourceConfig, primary_source: e.target.value})}
              className="input">
              <option value="yfinance">yfinance (free, no key)</option>
              <option value="alphavantage">Alpha Vantage (free key)</option>
              <option value="nse_india">NSE India</option>
              <option value="yahoo_scrape">Yahoo Finance Scraping</option>
            </select>
          </div>
          <div>
            <label className="label">Alpha Vantage API Key</label>
            <input type="password" placeholder="Optional API key"
              value={dataSourceConfig.alpha_vantage_key}
              onChange={e => setDataSourceConfig({...dataSourceConfig, alpha_vantage_key: e.target.value})}
              className="input" />
            <p className="text-[0.65rem] text-slate-500 mt-1">Free at <span className="text-blue-400">alphavantage.co</span> (25 calls/day)</p>
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={dataSourceConfig.enable_fallback}
              onChange={e => setDataSourceConfig({...dataSourceConfig, enable_fallback: e.target.checked})}
              className="rounded border-slate-600 bg-slate-800 text-blue-500 focus:ring-blue-500" />
            <span className="text-xs text-slate-400">Enable automatic fallback</span>
          </label>
          <div className="flex items-center gap-3">
            <button onClick={saveSourceConfig} className="btn btn-primary flex-1">
              Save Config
            </button>
            {saveFeedback && <span className="text-xs text-emerald-400 animate-pulse" role="status">{saveFeedback}</span>}
          </div>
        </div>

        <div className="pt-4 mt-4 border-t border-slate-700/40">
          <h4 className="text-xs font-semibold text-slate-300 mb-3">Test a Source</h4>
          <input type="text" placeholder="Ticker (e.g., MSFT, TCS.NS)" value={testTicker}
            onChange={e => setTestTicker(e.target.value)} className="input mb-3" />
          <div className="grid grid-cols-2 gap-2">
            {['auto', 'yfinance', 'alphavantage', 'nse_india', 'yahoo_scrape'].map(src => (
              <button key={src} onClick={() => testSource(src)}
                className={cn(
                  'bg-slate-800/40 border border-slate-700/40 rounded-lg px-3 py-2 text-xs text-white hover:border-blue-500/40 transition-colors capitalize',
                  testResult?.source === src && (testResult.success ? 'border-emerald-500/40' : 'border-red-500/40')
                )}>
                {src === 'auto' ? 'Auto (Fallback Chain)' : src.replace('_', ' ')}
              </button>
            ))}
          </div>
          {testResult && (
            <div role="alert" className={cn('mt-3 p-3 rounded-lg text-xs', testResult.success ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400' : 'bg-red-500/10 border border-red-500/20 text-red-400')}>
              {testResult.success ? (
                <div>
                  <div className="font-semibold mb-0.5">{testResult.source} — {testResult.rows} rows</div>
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
      </div>
    </div>
  )
}

function ScoreForm({ onScore, onExplain, loading }) {
  const [company, setCompany] = useState('')
  const [breachType, setBreachType] = useState('data_leak')
  const [records, setRecords] = useState('1000000')
  const [date, setDate] = useState('2024-01-01')
  const [searchResults, setSearchResults] = useState([])
  const [showSearch, setShowSearch] = useState(false)
  const [searching, setSearching] = useState(false)
  const [breachResults, setBreachResults] = useState([])
  const [breachSearching, setBreachSearching] = useState(false)
  const [showBreaches, setShowBreaches] = useState(false)
  const [validationError, setValidationError] = useState('')
  const [breachError, setBreachError] = useState('')
  const searchCache = useRef({})
  const debounceRef = useRef(null)
  const abortRef = useRef(null)
  const searchRef = useRef(null)
  const [activeIdx, setActiveIdx] = useState(-1)

  const searchTicker = useCallback(async (query) => {
    if (query.length < 2) { setSearchResults([]); setSearching(false); return }
    const cacheKey = query.toLowerCase()
    if (searchCache.current[cacheKey]) {
      setSearchResults(searchCache.current[cacheKey])
      setShowSearch(true)
      setSearching(false)
      return
    }
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setSearching(true)
    try {
      const res = await fetch(`${API}/search?q=${encodeURIComponent(query)}&limit=5`, { signal: controller.signal })
      const data = await res.json()
      const results = data.results || []
      searchCache.current[cacheKey] = results
      setSearchResults(results)
      setShowSearch(results.length > 0)
    } catch (e) { if (e.name !== 'AbortError') setSearchResults([]) }
    if (!controller.signal.aborted) setSearching(false)
  }, [])

  const searchBreaches = async (companyName) => {
    if (!companyName || companyName.length < 2) return
    setBreachSearching(true)
    setShowBreaches(true)
    setBreachError('')
    try {
      const res = await fetch(`${API}/breach-search?q=${encodeURIComponent(companyName)}&limit=5`)
      const data = await res.json()
      setBreachResults(data.incidents || [])
      if (!data.incidents?.length) setBreachError('No breaches found for this company online')
    } catch { setBreachResults([]); setBreachError('Search failed — backend may be offline') }
    setBreachSearching(false)
  }

  const selectBreach = (incident) => {
    if (incident.date) setDate(incident.date)
    if (incident.breach_type) setBreachType(incident.breach_type)
    if (incident.records_affected > 0) setRecords(String(incident.records_affected))
    setShowBreaches(false)
  }

  const handleCompanyChange = (e) => {
    const val = e.target.value
    setCompany(val)
    setValidationError('')
    clearTimeout(debounceRef.current)
    if (val.length < 2) { setSearchResults([]); setSearching(false); return }
    setSearching(true)
    debounceRef.current = setTimeout(() => searchTicker(val), 300)
  }

  const selectResult = (result) => {
    if (abortRef.current) abortRef.current.abort()
    clearTimeout(debounceRef.current)
    setCompany(result.ticker_full || result.symbol)
    setShowSearch(false)
    setSearchResults([])
    setSearching(false)
    setActiveIdx(-1)
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!company.trim()) {
      setValidationError('Enter a company name or ticker')
      return
    }
    setValidationError('')
    onScore({ company, breach_type: breachType, records_affected: parseInt(records) || 0, breach_date: date })
  }

  const handleSearchKeyDown = (e) => {
    if (!searchResults.length) return
    if (e.key === 'ArrowDown') {
      e.preventDefault(); setActiveIdx(i => Math.min(i + 1, searchResults.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault(); setActiveIdx(i => Math.max(i - 1, -1))
    } else if (e.key === 'Enter' && activeIdx >= 0) {
      e.preventDefault(); selectResult(searchResults[activeIdx])
    } else if (e.key === 'Escape') {
      setShowSearch(false); setActiveIdx(-1)
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4">
      <div className="relative">
        <label className="label" htmlFor="company-input">Company / Ticker</label>
        <div className="relative">
          <input id="company-input" type="text" value={company} onChange={handleCompanyChange}
            onFocus={() => searchResults.length > 0 && setShowSearch(true)}
            onBlur={() => setTimeout(() => { setShowSearch(false); setActiveIdx(-1) }, 200)}
            onKeyDown={handleSearchKeyDown}
            placeholder="Search any stock: VEDL, Reliance, MSFT..."
            className={cn('input', validationError && 'input-error')}
            aria-invalid={!!validationError}
            aria-describedby={validationError ? 'company-error' : undefined}
            aria-autocomplete="list" autoComplete="off" required />
          {searching && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2" aria-hidden="true">
              <div className="animate-spin w-3.5 h-3.5 border-2 border-blue-500 border-t-transparent rounded-full" />
            </div>
          )}
        </div>
        {validationError && <p id="company-error" className="text-xs text-red-400 mt-1" role="alert">{validationError}</p>}
        {showSearch && (
          <div ref={searchRef} className="absolute z-50 w-full mt-1 bg-slate-800 border border-slate-600/60 rounded-lg shadow-xl max-h-60 overflow-y-auto" role="listbox" aria-label="Search results">
            {searching && searchResults.length === 0 && (
              <div className="p-2 space-y-1.5">
                {[1, 2, 3].map(i => (
                  <div key={i} className="flex items-center gap-2.5 px-2 py-1.5">
                    <Skeleton className="h-4 w-16 rounded" />
                    <Skeleton className="h-3 flex-1 rounded" />
                  </div>
                ))}
              </div>
            )}
            {!searching && searchResults.length === 0 && company.length >= 2 && (
              <div className="px-3 py-2.5 text-xs text-slate-500 text-center">No results found</div>
            )}
            {searchResults.map((r, i) => (
              <button key={i} type="button" role="option" aria-selected={i === activeIdx} onClick={() => selectResult(r)}
                className={cn('w-full px-3 py-2 text-left transition-colors border-b border-slate-700/30 last:border-0',
                  i === activeIdx ? 'bg-blue-600/20' : 'hover:bg-slate-700/40')}>
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-sm text-white font-medium">{r.ticker_full || r.symbol}</span>
                    <span className="text-xs text-slate-500 ml-2">{r.exchange}</span>
                  </div>
                  {r.price && (
                    <span className="text-xs text-emerald-400 font-mono">
                      {r.currency === 'INR' ? '₹' : '$'}{r.price?.toFixed(2)}
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-400 truncate">{r.name}</div>
              </button>
            ))}
          </div>
        )}
      </div>

      <button type="button" onClick={() => searchBreaches(company)}
        disabled={!company || breachSearching}
        className="btn btn-secondary w-full justify-center">
        {breachSearching ? (
          <><div className="animate-spin w-3 h-3 border-2 border-amber-400 border-t-transparent rounded-full" /> Searching...</>
        ) : (
          <><svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg> Find Breach Data from Internet</>
        )}
      </button>

      {showBreaches && breachResults.length > 0 && (
        <div className="card p-3 space-y-2 fade-in" role="listbox" aria-label="Breach incidents">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400 font-medium">Breach Incidents Found</span>
            <button type="button" onClick={() => setShowBreaches(false)} className="text-xs text-slate-500 hover:text-white" aria-label="Close breach results">✕</button>
          </div>
          {breachResults.map((inc, i) => (
            <button key={i} type="button" onClick={() => selectBreach(inc)} role="option"
              className="w-full text-left bg-slate-800/50 border border-slate-700/30 rounded-lg px-3 py-2 hover:border-amber-500/40 transition-colors">
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-xs text-white font-medium">{inc.date}</span>
                <span className={cn('tag', inc.breach_type === 'ransomware' ? 'bg-red-500/15 text-red-400 border border-red-500/20' : 'bg-amber-500/15 text-amber-400 border border-amber-500/20')}>{inc.breach_type?.replace(/_/g, ' ')}</span>
              </div>
              <p className="text-xs text-slate-400 line-clamp-1">{inc.description}</p>
              {inc.records_affected > 0 && (
                <span className="text-[0.65rem] text-slate-500 mt-0.5 block">{(inc.records_affected / 1_000_000).toFixed(1)}M records</span>
              )}
            </button>
          ))}
          <p className="text-[0.65rem] text-slate-500 text-center">Click an incident to auto-fill</p>
        </div>
      )}
      {showBreaches && breachError && (
        <p className="text-xs text-slate-500 text-center py-1" role="alert">{breachError}</p>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label">Breach Type</label>
          <select value={breachType} onChange={e => setBreachType(e.target.value)} className="input">
            <option value="data_leak">Data Leak</option>
            <option value="ransomware">Ransomware</option>
            <option value="hack">External Hack</option>
            <option value="insider">Insider Threat</option>
            <option value="phishing">Phishing</option>
          </select>
        </div>
        <div>
          <label className="label">Records Affected</label>
          <input type="number" value={records} onChange={e => setRecords(e.target.value)} className="input" min="0" />
        </div>
      </div>
      <div>
        <label className="label">Breach Date</label>
        <input type="date" value={date} onChange={e => setDate(e.target.value)} className="input" />
      </div>
      <button type="submit" disabled={loading} className="btn btn-primary w-full py-2.5">
        {loading ? (
          <><div className="animate-spin w-3.5 h-3.5 border-2 border-white/60 border-t-transparent rounded-full" /> Analyzing...</>
        ) : 'Analyze Risk'}
      </button>
    </form>
  )
}

function FileUpload({ onUpload, onAnalyze, loading }) {
  const [dragActive, setDragActive] = useState(false)
  const [file, setFile] = useState(null)
  const [fileError, setFileError] = useState('')

  const MAX_SIZE = 50 * 1024 * 1024

  const handleDrag = useCallback((e) => {
    e.preventDefault(); e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') setDragActive(true)
    else if (e.type === 'dragleave') setDragActive(false)
  }, [])

  const handleDrop = useCallback((e) => {
    e.preventDefault(); e.stopPropagation()
    setDragActive(false)
    const f = e.dataTransfer.files?.[0]
    if (f) validateAndSet(f)
  }, [])

  const handleChange = (e) => {
    const f = e.target.files?.[0]
    if (f) validateAndSet(f)
  }

  const validateAndSet = (f) => {
    setFileError('')
    const allowed = ['.csv', '.xlsx', '.xls', '.tsv']
    const ext = '.' + f.name.split('.').pop().toLowerCase()
    if (!allowed.includes(ext)) {
      setFileError(`Unsupported format. Use: ${allowed.join(', ')}`)
      return
    }
    if (f.size > MAX_SIZE) {
      setFileError(`File too large (max 50 MB). Got ${(f.size / 1024 / 1024).toFixed(1)} MB`)
      return
    }
    setFile(f)
  }

  return (
    <div className="space-y-3">
      <form onDragEnter={handleDrag} onDragLeave={handleDrag} onDragOver={handleDrag} onDrop={handleDrop}>
        <label className={`flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-xl cursor-pointer transition-colors ${
          dragActive ? 'border-blue-500 bg-blue-500/10' : 'border-slate-600/50 bg-slate-800/20 hover:border-slate-500/50'
        }`} role="button" aria-label="Upload a CSV, XLSX, or TSV file">
          <div className="flex flex-col items-center justify-center pt-2 pb-3">
            <svg className="w-7 h-7 mb-2 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <p className="text-xs text-slate-400"><span className="font-semibold text-blue-400">Click to upload</span> or drag and drop</p>
            <p className="text-xs text-slate-500 mt-0.5">CSV, XLSX, Excel, TSV (max 50 MB)</p>
          </div>
          <input type="file" className="hidden" accept=".csv,.xlsx,.xls,.tsv" onChange={handleChange} />
        </label>
      </form>

      {fileError && <p className="text-xs text-red-400" role="alert">{fileError}</p>}

      {file && (
        <div className="bg-slate-800/40 border border-slate-700/40 rounded-lg p-3 flex items-center justify-between">
          <div className="flex items-center gap-2.5 min-w-0">
            <svg className="w-4 h-4 text-emerald-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-sm text-white truncate">{file.name}</span>
            <span className="text-xs text-slate-500 shrink-0">({(file.size / 1024).toFixed(1)} KB)</span>
          </div>
          <button onClick={() => setFile(null)} className="text-xs text-slate-500 hover:text-red-400 shrink-0 ml-3">Remove</button>
        </div>
      )}

      {file && (
        <div className="flex gap-2">
          <button onClick={() => onUpload(file)} disabled={loading} className="btn btn-secondary flex-1">
            {loading ? 'Previewing...' : 'Preview'}
          </button>
          <button onClick={() => onAnalyze(file)} disabled={loading} className="btn btn-primary flex-1">
            {loading ? 'Analyzing...' : 'Analyze All'}
          </button>
        </div>
      )}
    </div>
  )
}

function DatasetPreview({ data }) {
  if (!data) return null
  return (
    <div className="card p-6 fade-in">
      <h4 className="text-sm font-semibold text-white mb-4">Dataset Preview</h4>
      <div className="grid grid-cols-3 gap-3 mb-4">
        {[
          { label: 'Original Rows', value: data.original_rows, color: 'text-white' },
          { label: 'Cleaned Rows', value: data.cleaned_rows, color: 'text-emerald-400' },
          { label: 'Ticker Match', value: `${(data.ticker_resolution_rate * 100).toFixed(0)}%`, color: 'text-blue-400' },
        ].map(s => (
          <div key={s.label} className="bg-slate-800/40 border border-slate-700/40 rounded-lg p-3 text-center">
            <div className={`text-lg font-bold ${s.color}`}>{s.value}</div>
            <div className="text-[0.6875rem] text-slate-500">{s.label}</div>
          </div>
        ))}
      </div>
      {data.warnings?.length > 0 && (
        <div className="mb-4 space-y-1">
          {data.warnings.slice(0, 5).map((w, i) => (
            <div key={i} className="text-xs text-amber-400 bg-amber-500/8 px-3 py-1.5 rounded-lg">{w}</div>
          ))}
        </div>
      )}
      {data.preview?.length > 0 && (
        <div className="overflow-x-auto -mx-2">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-700/50">
                {Object.keys(data.preview[0]).map(col => (
                  <th key={col} className="text-left py-2 px-3 text-slate-400 font-medium capitalize whitespace-nowrap">{col.replace(/_/g, ' ')}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.preview.map((row, i) => (
                <tr key={i} className="border-b border-slate-800/30 hover:bg-slate-800/20">
                  {Object.values(row).map((val, j) => (
                    <td key={j} className="py-2 px-3 text-slate-300 whitespace-nowrap">{typeof val === 'number' ? val.toLocaleString() : val}</td>
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

function BatchResults({ data }) {
  const [expandedRow, setExpandedRow] = useState(null)
  const [sortKey, setSortKey] = useState(null)
  const [sortDir, setSortDir] = useState('asc')

  if (!data) return null

  const toggleSort = (key) => {
    setSortDir(d => (sortKey === key ? (d === 'asc' ? 'desc' : 'asc') : 'asc'))
    setSortKey(key)
  }

  const sorted = [...(data.results || [])].sort((a, b) => {
    if (!sortKey) return 0
    let av = a[sortKey], bv = b[sortKey]
    if (typeof av === 'string') av = av.toLowerCase()
    if (typeof bv === 'string') bv = bv.toLowerCase()
    if (av == null) return 1; if (bv == null) return -1
    const cmp = av < bv ? -1 : av > bv ? 1 : 0
    return sortDir === 'desc' ? -cmp : cmp
  })

  const SortIcon = ({ active }) => active
    ? <svg className="w-3 h-3 inline ml-0.5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={sortDir === 'asc' ? 'M5 15l7-7 7 7' : 'M19 9l-7 7-7-7'} /></svg>
    : <svg className="w-3 h-3 inline ml-0.5 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" /></svg>

  const Th = ({ sort, children, className }) => (
    <th className={`text-left py-2 px-3 text-slate-400 font-medium select-none ${sort ? 'cursor-pointer hover:text-white transition-colors' : ''} ${className || ''}`}
        onClick={sort ? () => toggleSort(sort) : undefined}
        aria-sort={sortKey === sort ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined}
        tabIndex={sort ? 0 : undefined}
        onKeyDown={sort ? e => e.key === 'Enter' && toggleSort(sort) : undefined}>
      {children}
      {sort && <SortIcon active={sortKey === sort} />}
    </th>
  )

  const exportCSV = () => {
    const headers = ['Company', 'Ticker', 'Breach Date', 'Records', 'Risk Score', 'Prediction', 'Low%', 'Medium%', 'High%', 'Critical%', 'Confidence', 'Status']
    const rows = data.results.map(r => [
      r.company, r.ticker, r.breach_date, r.records_affected,
      r.risk_score, r.prediction,
      r.probabilities ? (r.probabilities.low * 100).toFixed(1) : '',
      r.probabilities ? (r.probabilities.medium * 100).toFixed(1) : '',
      r.probabilities ? (r.probabilities.high * 100).toFixed(1) : '',
      r.probabilities ? (r.probabilities.critical * 100).toFixed(1) : '',
      r.confidence, r.status,
    ])
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'breachalpha_results.csv'; a.click()
  }

  return (
    <div className="card p-6 fade-in">
      <div className="flex items-center justify-between mb-4">
        <h4 className="text-sm font-semibold text-white">Batch Results</h4>
        <button onClick={exportCSV} className="btn btn-secondary text-xs py-1.5 px-3">
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
          Export CSV
        </button>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        {[
          { label: 'Total', value: data.total, color: 'text-white', testId: 'batch-total' },
          { label: 'Analyzed', value: data.analyzed, color: 'text-emerald-400', testId: 'batch-analyzed' },
          { label: 'Failed', value: data.failed, color: 'text-red-400', testId: 'batch-failed' },
        ].map(s => (
          <div key={s.label} className="bg-slate-800/40 border border-slate-700/40 rounded-lg p-3 text-center">
            <div className={`text-lg font-bold ${s.color}`}>{s.value}</div>
            <div className="text-[0.6875rem] text-slate-500">{s.label}</div>
          </div>
        ))}
      </div>

      {data.results.length === 0 ? (
        <div className="empty-state">
          <svg className="w-12 h-12 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <h3>No results</h3>
          <p>The dataset didn't produce any analyzable results. Check the file format and try again.</p>
        </div>
      ) : (
        <div className="overflow-x-auto -mx-2 max-h-[32rem] overflow-y-auto">
          <table className="w-full text-xs" role="table">
            <thead className="sticky top-0 bg-slate-900 z-10">
              <tr className="border-b border-slate-700/50">
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
                <tr key={i} role="button" tabIndex={0} aria-expanded={expandedRow === i}
                  onClick={() => setExpandedRow(expandedRow === i ? null : i)}
                  onKeyDown={e => e.key === 'Enter' && setExpandedRow(expandedRow === i ? null : i)}
                  className="border-b border-slate-800/30 hover:bg-slate-800/20 cursor-pointer transition-colors">
                  <td className="py-2 px-3 text-white font-medium">{r.company}</td>
                  <td className="py-2 px-3 text-slate-400">{r.ticker}</td>
                  <td className="py-2 px-3 text-slate-400 whitespace-nowrap">{r.breach_date}</td>
                  <td className="py-2 px-3 text-right font-mono font-bold" style={{ color: SEVERITY_COLORS[r.prediction] || '#64748b' }}>
                    {r.risk_score || '-'}
                  </td>
                  <td className="py-2 px-3">
                    <span className={cn('tag', SEVERITY_BG[r.prediction] || 'bg-slate-700 text-slate-400 border border-slate-700')}>
                      {r.prediction?.toUpperCase() || '-'}
                    </span>
                  </td>
                  <td className="py-2 px-3 min-w-[130px]">
                    {r.probabilities && Object.keys(r.probabilities).length > 0 ? (
                      <div className="flex gap-0.5 items-center" aria-label={Object.entries(r.probabilities).map(([k, v]) => `${k}: ${(v * 100).toFixed(0)}%`).join(', ')}>
                        {['low', 'medium', 'high', 'critical'].map(sev => (
                          <div key={sev} className="flex-1" title={`${sev}: ${(r.probabilities[sev] * 100).toFixed(1)}%`}>
                            <div className="h-1.5 bg-slate-700/50 rounded-full overflow-hidden">
                              <div className="h-full rounded-full" style={{ width: `${(r.probabilities[sev] || 0) * 100}%`, backgroundColor: SEVERITY_COLORS[sev] }} />
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : <span className="text-slate-600">-</span>}
                  </td>
                  <td className="py-2 px-3 text-right text-slate-400">{r.confidence ? `${(r.confidence * 100).toFixed(0)}%` : '-'}</td>
                  <td className="py-2 px-3">
                    {r.status === 'ok' ? (
                      <span className="text-emerald-400 text-[0.65rem] font-medium">OK</span>
                    ) : (
                      <span className="text-red-400 text-[0.65rem]" title={r.error}>{r.status}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.results.length > 0 && (
        <p className="text-[0.65rem] text-slate-500 mt-3">Click column headers to sort. Click a row to expand.</p>
      )}
    </div>
  )
}

function ExplainabilityPanel({ data }) {
  if (!data) return null
  return (
    <div className="card p-6 fade-in">
      <div className="flex items-center gap-2 mb-5">
        <svg className="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
        </svg>
        <h3 className="text-lg font-bold text-white">How the Risk Score is Calculated</h3>
      </div>

      <div className="bg-blue-500/8 border border-blue-500/20 rounded-xl p-4 mb-6">
        <h4 className="text-sm font-semibold text-blue-400 mb-2">Methodology</h4>
        <p className="text-xs text-slate-300 leading-relaxed">{data.methodology}</p>
      </div>

      <div className="space-y-3">
        {data.steps.map((step, i) => (
          <div key={i} className="bg-slate-800/30 border border-slate-700/40 rounded-xl p-4">
            <div className="flex items-start gap-3">
              <div className="w-7 h-7 rounded-full bg-blue-600/15 border border-blue-500/25 flex items-center justify-center shrink-0 mt-0.5">
                <span className="text-xs font-bold text-blue-400">{step.step_number}</span>
              </div>
              <div className="flex-1 min-w-0">
                <h5 className="text-sm font-semibold text-white mb-1">{step.name}</h5>
                <p className="text-xs text-slate-400 mb-2">{step.description}</p>
                <div className="bg-slate-900/50 rounded-lg p-3 mb-2 font-mono text-xs text-slate-300 overflow-x-auto">{step.formula}</div>
                <div className="grid grid-cols-2 gap-2 mb-2">
                  {Object.entries(step.inputs).map(([key, val]) => (
                    <div key={key} className="text-xs">
                      <span className="text-slate-500">{key}: </span>
                      <span className="text-slate-300">{typeof val === 'object' ? JSON.stringify(val) : String(val)}</span>
                    </div>
                  ))}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-500">Output:</span>
                  <span className="text-sm font-semibold text-white font-mono">{typeof step.output === 'number' ? step.output.toFixed(6) : String(step.output)}</span>
                </div>
                <div className="mt-2 text-xs text-slate-400 bg-slate-800/30 rounded-lg p-2">{step.interpretation}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 bg-slate-800/30 border border-slate-700/40 rounded-xl p-4">
        <h4 className="text-sm font-semibold text-white mb-3">Feature Contributions</h4>
        <div className="space-y-2">
          {Object.entries(data.feature_contributions).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).map(([feat, val]) => (
            <div key={feat} className="flex items-center gap-3">
              <span className="w-36 text-xs text-slate-400 truncate shrink-0">{feat.replace(/_/g, ' ')}</span>
              <div className="flex-1 h-2 bg-slate-700/40 rounded-full overflow-hidden">
                <div className="h-full rounded-full transition-all duration-500" style={{
                  width: `${Math.min(Math.abs(val) * 500, 100)}%`,
                  backgroundColor: val < 0 ? '#ef4444' : '#10b981',
                  marginLeft: val < 0 ? 'auto' : '0',
                }} />
              </div>
              <span className={cn('w-16 text-xs text-right font-mono shrink-0', val < 0 ? 'text-red-400' : 'text-emerald-400')}>
                {val > 0 ? '+' : ''}{val.toFixed(4)}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-6 bg-amber-500/8 border border-amber-500/20 rounded-xl p-4">
        <h4 className="text-sm font-semibold text-amber-400 mb-2">Limitations</h4>
        <ul className="space-y-1">
          {data.limitations.map((lim, i) => (
            <li key={i} className="text-xs text-slate-400 flex items-start gap-2">
              <span className="text-amber-400 mt-0.5 shrink-0">*</span>
              {lim}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function DemoCard({ demo, onClick, onExplain }) {
  return (
    <button onClick={() => onClick(demo)} onMouseDown={e => e.currentTarget.style.transform = 'scale(0.98)'}
      onMouseUp={e => e.currentTarget.style.transform = ''} onMouseLeave={e => e.currentTarget.style.transform = ''}
      className="card-hover card p-4 text-left w-full" style={{ transition: 'transform 0.15s cubic-bezier(0.4, 0, 0.2, 1)' }}>
      <div className="flex items-start justify-between mb-2.5">
        <div className="min-w-0">
          <h3 className="text-white font-semibold text-sm truncate">{demo.company}</h3>
          <span className="text-xs text-slate-500">{demo.ticker}</span>
        </div>
        {demo.risk_score && (
          <span className={cn('tag shrink-0 ml-2', demo.prediction ? SEVERITY_BG[demo.prediction] : 'bg-slate-700/50 text-slate-400 border border-slate-700')}>
            {demo.prediction?.toUpperCase()}
          </span>
        )}
      </div>
      <p className="text-xs text-slate-400 mb-3 line-clamp-2">{demo.description}</p>
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-500">{demo.breach_date}</span>
        <span className="text-slate-400">{(demo.pwn_count / 1_000_000).toFixed(0)}M records</span>
      </div>
      {demo.risk_score && (
        <div className="mt-2.5 pt-2.5 border-t border-slate-700/40 flex items-center justify-between">
          <span className="text-xs text-slate-500">Risk Score</span>
          <div className="flex items-center gap-2.5">
            <span className="text-lg font-bold" style={{ color: SEVERITY_COLORS[demo.prediction] }}>{demo.risk_score}</span>
                      <button onClick={(e) => { e.stopPropagation(); onExplain(demo.ticker || demo.company) }}
                        className="text-xs text-blue-400 hover:text-blue-300 transition-colors" title="Explain this score">Explain</button>
          </div>
        </div>
      )}
    </button>
  )
}

function LLMAnalysisPanel({ batchData }) {
  const [llmStatus, setLlmStatus] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [loading, setLoading] = useState(false)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [askLoading, setAskLoading] = useState(false)
  const questionRef = useRef(null)

  useEffect(() => {
    fetch(`${API}/llm/status`).then(r => r.json()).then(setLlmStatus).catch(() => {})
  }, [])

  const generateAnalysis = async () => {
    setLoading(true)
    try {
      const summary = `Dataset: ${batchData.total} companies, ${batchData.analyzed} analyzed, ${batchData.failed} failed. ` +
        `Results: ${batchData.results.map(r => `${r.company}(${r.ticker}): score=${r.risk_score}, ${r.prediction}`).join('; ')}`
      const res = await fetch(`${API}/llm/analyze-dataset`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dataset_summary: summary, analysis_results: JSON.stringify(batchData.results) }),
      })
      if (!res.ok) throw new Error((await res.json()).detail)
      setAnalysis((await res.json()).analysis)
    } catch (e) { setAnalysis('Error: ' + e.message) }
    setLoading(false)
  }

  const askQuestion = async () => {
    if (!question.trim()) return
    setAskLoading(true)
    try {
      const context = `Dataset has ${batchData.analyzed} analyzed companies. Top: ${
        batchData.results.filter(r => r.status === 'ok').slice(0, 5).map(r => `${r.company}: risk=${r.risk_score}, severity=${r.prediction}`).join('; ')}`
      const res = await fetch(`${API}/llm/ask`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, context }),
      })
      if (!res.ok) throw new Error((await res.json()).detail)
      setAnswer((await res.json()).answer)
    } catch (e) { setAnswer('Error: ' + e.message) }
    setAskLoading(false)
  }

  if (!llmStatus?.available) {
    return (
      <div className="card p-5 mt-6">
        <h3 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
          <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          LLM Analysis
        </h3>
        <p className="text-xs text-slate-400 leading-relaxed">
          Connect <strong className="text-slate-300">LM Studio</strong> with Qwen 3.5 9B at{' '}
          <code className="bg-slate-700/60 px-1.5 py-0.5 rounded text-blue-400">192.168.56.1:1234</code> for AI insights.
        </p>
        <p className="text-xs text-slate-500 mt-1">Start LM Studio and load a model to enable this feature.</p>
      </div>
    )
  }

  return (
    <div className="card p-5 mt-6 fade-in">
      <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
        <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
        LLM Analysis
        <span className="text-[0.65rem] text-emerald-400 font-normal">({llmStatus.default_model || 'connected'})</span>
      </h3>

      <button onClick={generateAnalysis} disabled={loading} className="btn btn-secondary w-full justify-center mb-4">
        {loading ? (
          <><div className="animate-spin w-3 h-3 border-2 border-purple-400 border-t-transparent rounded-full" /> Analyzing...</>
        ) : 'Generate AI Risk Analysis'}
      </button>

      {analysis && (
        <div className="bg-slate-900/50 rounded-lg p-4 mb-4">
          <h4 className="text-xs font-semibold text-slate-300 mb-2">AI Analysis</h4>
          <div className="text-xs text-slate-300 whitespace-pre-wrap leading-relaxed">{analysis}</div>
        </div>
      )}

      <div className="border-t border-slate-700/40 pt-4">
        <h4 className="text-xs font-semibold text-slate-300 mb-2">Ask about this data</h4>
        <div className="flex gap-2">
          <input ref={questionRef} type="text" value={question} onChange={e => setQuestion(e.target.value)}
            placeholder="e.g., Which breach type causes the most damage?"
            className="input flex-1"
            onKeyDown={e => e.key === 'Enter' && askQuestion()} />
          <button onClick={askQuestion} disabled={askLoading || !question.trim()} className="btn btn-primary">
            {askLoading ? '...' : 'Ask'}
          </button>
        </div>
        {answer && (
          <div className="mt-3 bg-slate-900/50 rounded-lg p-3">
            <div className="text-xs text-slate-300 whitespace-pre-wrap">{answer}</div>
          </div>
        )}
      </div>
    </div>
  )
}

function FeaturesChart({ features, error }) {
  if (error) {
    return (
      <div className="h-48 flex flex-col items-center justify-center bg-slate-800/20 rounded-lg border border-slate-700/30" role="alert">
        <svg className="w-8 h-8 text-slate-600 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p className="text-xs text-slate-500">{error}</p>
      </div>
    )
  }

  if (!features || features.abnormal_return_day0 == null) {
    return (
      <div className="h-48 flex items-center justify-center bg-slate-800/20 rounded-lg border border-slate-700/30">
        <p className="text-xs text-slate-500">No chart data available</p>
      </div>
    )
  }

  const data = {
    labels: ['Day 0', 'Day +1', 'Day +5', 'Day +30'],
    datasets: [{
      label: 'Abnormal Return',
      data: [features.abnormal_return_day0, features.abnormal_return_day1,
             features.abnormal_return_day5, features.abnormal_return_day30],
      backgroundColor: [
        features.abnormal_return_day0 < 0 ? 'rgba(239,68,68,0.5)' : 'rgba(16,185,129,0.5)',
        features.abnormal_return_day1 < 0 ? 'rgba(239,68,68,0.5)' : 'rgba(16,185,129,0.5)',
        features.abnormal_return_day5 < 0 ? 'rgba(239,68,68,0.5)' : 'rgba(16,185,129,0.5)',
        features.abnormal_return_day30 < 0 ? 'rgba(239,68,68,0.5)' : 'rgba(16,185,129,0.5)',
      ],
      borderColor: ['#ef4444', '#ef4444', '#10b981', '#10b981'],
      borderWidth: 1, borderRadius: 4,
    }],
  }
  const options = {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: ctx => `${ctx.parsed.y >= 0 ? '+' : ''}${(ctx.parsed.y * 100).toFixed(2)}% abnormal return`,
        },
      },
    },
    scales: {
      x: { grid: { color: '#1e293b' }, ticks: { color: '#64748b' } },
      y: {
        grid: { color: '#1e293b' },
        ticks: { color: '#64748b', callback: v => `${(v * 100).toFixed(1)}%` },
      },
    },
  }
  const arLabel = `Abnormal returns: Day 0 ${(features.abnormal_return_day0 * 100).toFixed(2)}%, Day +1 ${(features.abnormal_return_day1 * 100).toFixed(2)}%, Day +5 ${(features.abnormal_return_day5 * 100).toFixed(2)}%, Day +30 ${(features.abnormal_return_day30 * 100).toFixed(2)}%`
  return <div className="h-48" role="img" aria-label={arLabel}>
    <Bar data={data} options={options} />
  </div>
}

function App() {
  const [activeTab, setActiveTab] = useState('single')
  const [score, setScore] = useState(null)
  const [demos, setDemos] = useState([])
  const [loading, setLoading] = useState(false)
  const [demosLoading, setDemosLoading] = useState(false)
  const [error, setError] = useState(null)
  const [health, setHealth] = useState(null)

  const [uploadData, setUploadData] = useState(null)
  const [batchData, setBatchData] = useState(null)

  const [explainData, setExplainData] = useState(null)
  const [explainLoading, setExplainLoading] = useState(false)

  const [analysisConfig, setAnalysisConfig] = useState({
    estimation_window: 250, pre_event_window: 30, post_event_window: 60,
    recovery_max_days: 90, threshold_critical: -0.15, threshold_high: -0.07,
    threshold_medium: -0.02, car_short_start: -1, car_short_end: 1,
    car_long_start: -5, car_long_end: 30, benchmark: '^GSPC',
    start_date: '2010-01-01', min_records: 1000,
  })
  const [presets, setPresets] = useState([])

  const loadPresets = async () => {
    try { setPresets(await (await fetch(`${API}/config/presets`)).json()) } catch {}
  }

  useEffect(() => {
    fetch(`${API}/health`).then(r => r.json()).then(setHealth)
      .catch(() => setHealth({ status: 'offline', model_loaded: false }))
  }, [])

  const loadDemos = async () => {
    setDemosLoading(true)
    try {
      const res = await fetch(`${API}/demo`)
      setDemos(await res.json())
    } catch { setError('Failed to load demo data. Is the backend running?') }
    setDemosLoading(false)
  }

  const handleScore = async (params) => {
    setLoading(true); setError(null); setScore(null)
    try {
      const res = await fetch(`${API}/score`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      })
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail) }
      setScore(await res.json())
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const handleUpload = async (file) => {
    setLoading(true); setError(null); setUploadData(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch(`${API}/upload`, { method: 'POST', body: form })
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail) }
      setUploadData(await res.json())
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const handleAnalyze = async (file) => {
    setLoading(true); setError(null); setBatchData(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch(`${API}/upload/analyze`, { method: 'POST', body: form })
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail) }
      setBatchData(await res.json())
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const handleAutoExplain = async (ticker) => {
    setExplainLoading(true); setError(null); setExplainData(null)
    try {
      const res = await fetch(`${API}/explain/auto`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company: ticker }),
      })
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail) }
      setExplainData(await res.json())
      setActiveTab('explain')
    } catch (e) { setError(e.message) }
    setExplainLoading(false)
  }

  const handleDemoClick = (demo) => {
    setScore({
      company: demo.company, ticker: demo.ticker,
      risk_score: demo.risk_score, prediction: demo.prediction,
      confidence: demo.confidence, features: null,
    })
  }

  const tabs = [
    { id: 'single', label: 'Single Analysis' },
    { id: 'upload', label: 'Upload Dataset' },
    { id: 'explain', label: 'Explain Score' },
    { id: 'settings', label: 'Settings' },
  ]

  return (
    <div className="min-h-screen" role="application" aria-label="BreachAlpha cyber-financial risk quantifier">
      <header className="border-b border-slate-800/60 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-50" role="banner">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center shadow-sm">
              <svg className="w-4.5 h-4.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <h1 className="text-base font-bold text-white tracking-tight">BreachAlpha</h1>
              <p className="text-[0.65rem] text-slate-500 -mt-0.5">Cyber-Financial Risk Quantifier</p>
            </div>
          </div>
          <div className="flex items-center gap-2" role="status">
            <div className={cn('status-dot', health?.status === 'ok' ? 'bg-emerald-400' : 'bg-slate-500')}
              title={health?.status === 'ok' ? 'Backend connected' : 'Backend offline'} />
            <span className="text-xs text-slate-500">{health?.model_loaded ? 'Model Ready' : 'No Model'}</span>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-7" role="main" aria-live="polite">
        <div className="text-center mb-7">
          <h2 className="text-2xl sm:text-3xl font-bold text-white mb-2 tracking-tight">Quantify Cyber Breach Impact</h2>
          <p className="text-sm text-slate-400 max-w-2xl mx-auto leading-relaxed">
            Analyze how cybersecurity incidents affect stock prices. Upload a dataset or score individual companies using event study methodology.
          </p>
        </div>

        <TabBar tabs={tabs} active={activeTab} onChange={setActiveTab} />

        <div role="tabpanel" id={`panel-${activeTab}`} aria-labelledby={`tab-${activeTab}`}>
          {error && (
            <div className="bg-red-500/10 border border-red-500/25 rounded-xl p-4 text-red-400 text-sm mb-6 flex items-start gap-3" role="alert">
              <svg className="w-4 h-4 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div className="flex-1">
                <p className="font-medium mb-0.5">Analysis Error</p>
                <p className="opacity-80 text-xs">{error}</p>
                <button onClick={() => setError(null)} className="text-xs text-red-300 hover:text-red-200 mt-1 underline">Dismiss</button>
              </div>
            </div>
          )}

          {/* Single Analysis Tab */}
          {activeTab === 'single' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-4 space-y-6">
                <div className="card p-5">
                  <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                    <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    Analyze a Company
                  </h3>
                  <ScoreForm onScore={handleScore} onExplain={handleAutoExplain} loading={loading} />
                </div>

                <div className="card p-5">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                      <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      Famous Breaches
                    </h3>
                    <button onClick={loadDemos} disabled={demosLoading}
                      className="btn-secondary text-xs py-1 px-2.5">
                      {demosLoading ? (
                        <><div className="animate-spin w-2.5 h-2.5 border-2 border-blue-400 border-t-transparent rounded-full" /> Loading</>
                      ) : 'Load Demos'}
                    </button>
                  </div>
                  <div className="space-y-3">
                    {demos.length === 0 && !demosLoading && (
                      <div className="empty-state py-6">
                        <svg className="w-10 h-10 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                        </svg>
                        <h3>No Demos Loaded</h3>
                        <p>Click "Load Demos" to analyze Equifax, Capital One, and Marriott breaches.</p>
                      </div>
                    )}
                    {demos.length === 0 && demosLoading && (
                      <div className="space-y-2.5">
                        {[1, 2, 3].map(i => (
                          <div key={i} className="card p-4">
                            <Skeleton className="h-4 w-24 mb-2" />
                            <Skeleton className="h-3 w-full mb-1" />
                            <Skeleton className="h-3 w-3/4" />
                          </div>
                        ))}
                      </div>
                    )}
                    {demos.map((d, i) => (
                      <DemoCard key={i} demo={d} onClick={handleDemoClick} onExplain={handleAutoExplain} />
                    ))}
                  </div>
                </div>
              </div>

              <div className="lg:col-span-8 space-y-6" aria-live="polite">
                {loading && !score && (
                  <div className="card p-6">
                    <div className="flex items-center gap-4 mb-5">
                      <Skeleton className="h-5 w-32" />
                      <Skeleton className="h-5 w-16 rounded-full" />
                    </div>
                    <div className="flex justify-center mb-5">
                      <Skeleton className="w-36 h-36 rounded-full" />
                    </div>
                    <div className="space-y-2.5">
                      {[1, 2, 3, 4].map(i => (
                        <div key={i} className="flex items-center gap-3">
                          <Skeleton className="h-3 w-16" />
                          <Skeleton className="h-2.5 flex-1" />
                          <Skeleton className="h-3 w-10" />
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {!score && !loading && !error && (
                  <div className="card empty-state py-16">
                    <svg className="w-14 h-14 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                    <h3 className="text-slate-400">No Analysis Yet</h3>
                    <p className="text-slate-500">Enter a company name in the form or load a demo to see the risk analysis.</p>
                  </div>
                )}

                {score && (
                  <>
                    <div className="card p-6 fade-in">
                      <div className="flex items-center justify-between mb-4">
                        <div>
                          <h3 className="text-xl font-bold text-white">{score.company}</h3>
                          <span className="text-sm text-slate-500">{score.ticker}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <button onClick={() => handleAutoExplain(score.ticker || score.company)}
                            disabled={explainLoading}
                            className="btn btn-secondary text-xs py-1 px-2.5">
                            {explainLoading ? (
                              <><div className="animate-spin w-2.5 h-2.5 border-2 border-blue-400 border-t-transparent rounded-full" /> Loading</>
                            ) : (
                              <><svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg> Explain</>
                            )}
                          </button>
                          <span className={cn('tag text-xs', SEVERITY_BG[score.prediction] || 'bg-slate-700/50 text-slate-400 border border-slate-700')}>
                            {score.prediction?.toUpperCase() || 'N/A'}
                          </span>
                        </div>
                      </div>
                      <RiskGauge score={score.risk_score} prediction={score.prediction} />
                    </div>

                    <div className="card p-6 fade-in">
                      <h4 className="text-sm font-semibold text-white mb-4">Severity Probability</h4>
                      <div className="space-y-3">
                        {Object.entries(score.probabilities || {}).map(([label, prob]) => (
                          <ProbabilityBar key={label} label={label} probability={prob} color={SEVERITY_COLORS[label]} />
                        ))}
                      </div>
                      <div className="mt-4 pt-3 border-t border-slate-700/40 flex items-center justify-between text-xs">
                        <span className="text-slate-500">Confidence</span>
                        <span className="text-white font-semibold">{(score.confidence * 100).toFixed(1)}%</span>
                      </div>
                    </div>

                    {score.features && (
                      <div className="card p-6 fade-in">
                        <h4 className="text-sm font-semibold text-white mb-4">Event Study Features</h4>
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 mb-6">
                          <FeatureCard label="AR (Day 0)" value={score.features.abnormal_return_day0} negative />
                          <FeatureCard label="AR (Day +1)" value={score.features.abnormal_return_day1} negative />
                          <FeatureCard label="AR (Day +5)" value={score.features.abnormal_return_day5} negative />
                          <FeatureCard label="AR (Day +30)" value={score.features.abnormal_return_day30} negative />
                          <FeatureCard label="CAR (-1,+1)" value={score.features.car_minus1_plus1} negative />
                          <FeatureCard label="CAR (-5,+30)" value={score.features.car_minus5_plus30} negative />
                          <FeatureCard label="Volatility Spike" value={score.features.volatility_spike} unit="x" />
                          <FeatureCard label="Volume Change" value={score.features.volume_change} unit="x" />
                          <FeatureCard label="Recovery" value={score.features.time_to_recovery ? `${score.features.time_to_recovery}d` : 'N/A'} />
                        </div>
                        <h4 className="text-sm font-semibold text-white mb-3">Abnormal Returns Timeline</h4>
                        <FeaturesChart features={score.features} />
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          )}

          {/* Upload Tab */}
          {activeTab === 'upload' && (
            <div className="max-w-4xl mx-auto space-y-6">
              <div className="card p-6">
                <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                  <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  Upload Breach Dataset
                </h3>
                <p className="text-xs text-slate-400 mb-4 leading-relaxed">
                  Upload a CSV, XLSX, or Excel file with breach data. The system auto-detects columns
                  for company name, breach date, and records affected.
                </p>
                <FileUpload onUpload={handleUpload} onAnalyze={handleAnalyze} loading={loading} />
              </div>
              {loading && !uploadData && !batchData && (
                <div className="card p-6">
                  <div className="space-y-3">
                    <Skeleton className="h-4 w-32 mb-4" />
                    <div className="grid grid-cols-3 gap-3 mb-4">
                      {[1, 2, 3].map(i => <Skeleton key={i} className="h-20 rounded-lg" />)}
                    </div>
                    <Skeleton className="h-40 rounded-lg" />
                  </div>
                </div>
              )}
              {uploadData && <DatasetPreview data={uploadData} />}
              {batchData && <BatchResults data={batchData} />}
              {batchData && batchData.analyzed > 0 && <LLMAnalysisPanel batchData={batchData} />}
            </div>
          )}

          {/* Explain Tab */}
          {activeTab === 'explain' && (
            <div className="max-w-4xl mx-auto">
              {explainLoading && (
                <div className="card p-12 text-center">
                  <div className="animate-spin w-7 h-7 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-4" role="status" aria-label="Loading explanation" />
                  <p className="text-sm text-slate-400">Generating explainability report...</p>
                </div>
              )}
              {!explainData && !explainLoading && (
                <div className="card empty-state py-16">
                  <svg className="w-14 h-14 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                  </svg>
                  <h3>No Explanation Yet</h3>
                  <p>Search a ticker in "Single Analysis" and click "Explain" next to the risk score, or load a demo and click "Explain" on any card.</p>
                </div>
              )}
              {explainData && <ExplainabilityPanel data={explainData} />}
            </div>
          )}

          {/* Settings Tab */}
          {activeTab === 'settings' && (
            <div className="max-w-4xl mx-auto">
              <SettingsPanel config={analysisConfig} setConfig={setAnalysisConfig} presets={presets} onLoadPresets={loadPresets} />
              <div className="card p-5 mt-6">
                <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                  <svg className="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Current Configuration
                </h3>
                <div className="bg-slate-900/50 rounded-lg p-4 font-mono text-xs text-slate-300 overflow-x-auto">
                  <pre>{JSON.stringify(analysisConfig, null, 2)}</pre>
                </div>
                <p className="text-xs text-slate-500 mt-3">These settings apply to all analyses. Use presets for quick config.</p>
              </div>
            </div>
          )}
        </div>
      </main>

      <footer className="border-t border-slate-800/60 mt-12 py-5" role="contentinfo">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 text-center text-[0.65rem] text-slate-600">
          BreachAlpha — Event Study Methodology (MacKinlay, 1997)
        </div>
      </footer>
    </div>
  )
}

export default App
