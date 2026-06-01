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
  low: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
  medium: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  high: 'bg-orange-500/20 text-orange-400 border border-orange-500/30',
  critical: 'bg-red-500/20 text-red-400 border border-red-500/30',
}

// ── Reusable Components ─────────────────────────────────────────────────

function RiskGauge({ score, prediction }) {
  const color = SEVERITY_COLORS[prediction] || '#64748b'
  const circumference = 2 * Math.PI * 70
  const offset = circumference - (score / 100) * circumference
  return (
    <div className="relative w-48 h-48 mx-auto">
      <svg className="w-full h-full" style={{ transform: 'rotate(-90deg)' }} viewBox="0 0 160 160">
        <circle cx="80" cy="80" r="70" fill="none" stroke="#1e293b" strokeWidth="12" />
        <circle cx="80" cy="80" r="70" fill="none" stroke={color} strokeWidth="12"
          strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 1s ease-out' }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold" style={{ color }}>{score}</span>
        <span className="text-xs text-slate-400 mt-1">/ 100</span>
      </div>
    </div>
  )
}

function ProbabilityBar({ label, probability, color }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-20 text-xs text-slate-400 capitalize">{label}</span>
      <div className="flex-1 h-2 bg-slate-700 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-500"
          style={{ width: `${probability * 100}%`, backgroundColor: color }} />
      </div>
      <span className="w-12 text-xs text-slate-300 text-right">{(probability * 100).toFixed(1)}%</span>
    </div>
  )
}

function FeatureCard({ label, value, unit, negative }) {
  const color = negative ? 'text-red-400' : 'text-slate-400'
  return (
    <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-3">
      <div className="text-xs text-slate-500 mb-1">{label}</div>
      <div className={`text-lg font-semibold ${color}`}>
        {typeof value === 'number' ? value.toFixed(4) : value || 'N/A'}
        {unit && <span className="text-xs text-slate-500 ml-1">{unit}</span>}
      </div>
    </div>
  )
}

function TabBar({ tabs, active, onChange }) {
  return (
    <div className="flex gap-1 bg-slate-800/60 p-1 rounded-xl mb-6">
      {tabs.map(tab => (
        <button key={tab.id} onClick={() => onChange(tab.id)}
          className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
            active === tab.id
              ? 'bg-blue-600 text-white'
              : 'text-slate-400 hover:text-white hover:bg-slate-700/50'
          }`}>
          {tab.label}
        </button>
      ))}
    </div>
  )
}

// ── Settings Panel ───────────────────────────────────────────────────────

function SettingsPanel({ config, setConfig, presets, onLoadPresets }) {
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

  useEffect(() => { onLoadPresets(); loadSourceStatus() }, [])

  const loadSourceStatus = async () => {
    try {
      const res = await fetch(`${API}/data-sources`)
      if (!res.ok) return
      const data = await res.json()
      setSourceStatus(data)
    } catch {}
  }

  const applyPreset = (preset) => {
    setConfig(preset.config)
  }

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
    } catch (e) {
      setTestResult({ source: sourceName, success: false, error: e.message })
    }
  }

  const saveSourceConfig = async () => {
    try {
      const res = await fetch(`${API}/data-sources/configure`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dataSourceConfig),
      })
      setSourceStatus(await res.json())
    } catch {}
  }

  return (
    <div className="space-y-6">
      {/* Analysis Settings */}
      <div className="bg-slate-800/40 border border-slate-700/50 rounded-2xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            Analysis Settings
          </h3>
          <button onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-xs text-slate-400 hover:text-white">
            {showAdvanced ? 'Hide' : 'Advanced'}
          </button>
        </div>

        {/* Presets */}
        <div className="mb-4">
          <label className="block text-xs text-slate-400 mb-2">Quick Presets</label>
          <div className="grid grid-cols-2 gap-2">
            {presets.map(p => (
              <button key={p.name} onClick={() => applyPreset(p)}
                className="bg-slate-800/60 border border-slate-700/50 rounded-lg px-3 py-2 text-xs text-left hover:border-blue-500/50 transition-colors">
                <div className="text-white font-medium capitalize">{p.name}</div>
                <div className="text-slate-500 mt-0.5">{p.description}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Quick Settings */}
        <div className="space-y-3 mb-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Market Benchmark</label>
            <select value={config.benchmark} onChange={e => setConfig({...config, benchmark: e.target.value})}
              className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500">
              <option value="^GSPC">S&P 500 (^GSPC)</option>
              <option value="^DJI">Dow Jones (^DJI)</option>
              <option value="^IXIC">NASDAQ (^IXIC)</option>
              <option value="^RUT">Russell 2000 (^RUT)</option>
              <option value="^NSEI">NIFTY 50 (^NSEI)</option>
              <option value="^NSEBANK">NIFTY Bank (^NSEBANK)</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Stock Data Start Date</label>
            <input type="date" value={config.start_date} onChange={e => setConfig({...config, start_date: e.target.value})}
              className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Min Records Affected</label>
            <input type="number" value={config.min_records} onChange={e => setConfig({...config, min_records: parseInt(e.target.value)})}
              className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500" />
          </div>
        </div>

        {/* Advanced Settings */}
        {showAdvanced && (
          <div className="space-y-3 pt-4 border-t border-slate-700/50">
            <h4 className="text-xs font-semibold text-slate-300">Event Windows</h4>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-500 mb-1">Estimation Window (days)</label>
                <input type="number" value={config.estimation_window}
                  onChange={e => setConfig({...config, estimation_window: parseInt(e.target.value)})}
                  className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500" />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Pre-Event Window (days)</label>
                <input type="number" value={config.pre_event_window}
                  onChange={e => setConfig({...config, pre_event_window: parseInt(e.target.value)})}
                  className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500" />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Post-Event Window (days)</label>
                <input type="number" value={config.post_event_window}
                  onChange={e => setConfig({...config, post_event_window: parseInt(e.target.value)})}
                  className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500" />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Recovery Max (days)</label>
                <input type="number" value={config.recovery_max_days}
                  onChange={e => setConfig({...config, recovery_max_days: parseInt(e.target.value)})}
                  className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500" />
              </div>
            </div>

            <h4 className="text-xs font-semibold text-slate-300 pt-2">CAR Windows</h4>
            <div className="grid grid-cols-4 gap-2">
              {[
                { label: 'Short Start', key: 'car_short_start' },
                { label: 'Short End', key: 'car_short_end' },
                { label: 'Long Start', key: 'car_long_start' },
                { label: 'Long End', key: 'car_long_end' },
              ].map(({ label, key }) => (
                <div key={key}>
                  <label className="block text-xs text-slate-500 mb-1">{label}</label>
                  <input type="number" value={config[key]}
                    onChange={e => setConfig({...config, [key]: parseInt(e.target.value)})}
                    className="w-full bg-slate-800 border border-slate-600 rounded-lg px-2 py-2 text-xs text-white focus:outline-none focus:border-blue-500" />
                </div>
              ))}
            </div>

            <h4 className="text-xs font-semibold text-slate-300 pt-2">Severity Thresholds (CAR)</h4>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-xs text-slate-500 mb-1">Critical (&lt;)</label>
                <input type="number" step="0.01" value={config.threshold_critical}
                  onChange={e => setConfig({...config, threshold_critical: parseFloat(e.target.value)})}
                  className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-red-500" />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">High (&lt;)</label>
                <input type="number" step="0.01" value={config.threshold_high}
                  onChange={e => setConfig({...config, threshold_high: parseFloat(e.target.value)})}
                  className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-orange-500" />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Medium (&lt;)</label>
                <input type="number" step="0.01" value={config.threshold_medium}
                  onChange={e => setConfig({...config, threshold_medium: parseFloat(e.target.value)})}
                  className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-amber-500" />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Data Sources Panel */}
      <div className="bg-slate-800/40 border border-slate-700/50 rounded-2xl p-6">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <svg className="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
          </svg>
          Data Sources
        </h3>

        <p className="text-xs text-slate-400 mb-4">
          Configure where stock data is fetched from. Multiple sources provide automatic fallback.
        </p>

        {/* Source Status */}
        {sourceStatus && (
          <div className="mb-4 space-y-2">
            {Object.entries(sourceStatus.sources || {}).map(([name, info]) => (
              <div key={name} className="flex items-center justify-between bg-slate-800/60 rounded-lg px-3 py-2">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${info.available ? 'bg-emerald-400' : 'bg-slate-500'}`} />
                  <span className="text-xs text-white font-medium capitalize">{name.replace('_', ' ')}</span>
                  <span className="text-xs text-slate-500">Priority: {info.priority + 1}</span>
                </div>
                {info.reason && <span className="text-xs text-amber-400">{info.reason}</span>}
              </div>
            ))}
          </div>
        )}

        {/* Configure */}
        <div className="space-y-3 mb-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Primary Source</label>
            <select value={dataSourceConfig.primary_source}
              onChange={e => setDataSourceConfig({...dataSourceConfig, primary_source: e.target.value})}
              className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500">
              <option value="yfinance">yfinance (free, no key needed)</option>
              <option value="alphavantage">Alpha Vantage (free API key)</option>
              <option value="nse_india">NSE India (Indian stocks)</option>
              <option value="yahoo_scrape">Yahoo Finance Scraping</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Alpha Vantage API Key (optional)</label>
            <input type="password" placeholder="Enter API key for Alpha Vantage"
              value={dataSourceConfig.alpha_vantage_key}
              onChange={e => setDataSourceConfig({...dataSourceConfig, alpha_vantage_key: e.target.value})}
              className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500" />
            <p className="text-xs text-slate-500 mt-1">Free at <span className="text-blue-400">alphavantage.co</span> (25 calls/day)</p>
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" id="fallback" checked={dataSourceConfig.enable_fallback}
              onChange={e => setDataSourceConfig({...dataSourceConfig, enable_fallback: e.target.checked})}
              className="rounded border-slate-600 bg-slate-800 text-blue-500 focus:ring-blue-500" />
            <label htmlFor="fallback" className="text-xs text-slate-400">Enable automatic fallback to other sources</label>
          </div>
          <button onClick={saveSourceConfig}
            className="w-full bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium py-2 rounded-lg transition-colors">
            Save Data Source Config
          </button>
        </div>

        {/* Test Source */}
        <div className="pt-4 border-t border-slate-700/50">
          <h4 className="text-xs font-semibold text-slate-300 mb-3">Test a Source</h4>
          <div className="flex gap-2 mb-3">
            <input type="text" placeholder="Ticker (e.g., MSFT, TCS.NS)" value={testTicker}
              onChange={e => setTestTicker(e.target.value)}
              className="flex-1 bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            {['auto', 'yfinance', 'alphavantage', 'nse_india', 'yahoo_scrape'].map(src => (
              <button key={src} onClick={() => testSource(src)}
                className="bg-slate-800/60 border border-slate-700/50 rounded-lg px-3 py-2 text-xs text-white hover:border-blue-500/50 transition-colors capitalize">
                {src === 'auto' ? 'Test Auto (Fallback Chain)' : `Test ${src.replace('_', ' ')}`}
              </button>
            ))}
          </div>
          {testResult && (
            <div className={`mt-3 p-3 rounded-lg text-xs ${testResult.success ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400' : 'bg-red-500/10 border border-red-500/30 text-red-400'}`}>
              {testResult.success ? (
                <div>
                  <div className="font-semibold">{testResult.source} — Success</div>
                  <div>{testResult.rows} rows, {testResult.elapsed_seconds}s</div>
                  <div>Latest: ${testResult.latest_close?.toFixed(2)} ({testResult.date_range?.[0]} to {testResult.date_range?.[1]})</div>
                </div>
              ) : (
                <div>
                  <div className="font-semibold">{testResult.source} — Failed</div>
                  <div>{testResult.error}</div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Score Form ──────────────────────────────────────────────────────────

function ScoreForm({ onScore, loading }) {
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
  const searchCache = useRef({})
  const debounceRef = useRef(null)

  const searchTicker = useCallback(async (query) => {
    if (query.length < 2) { setSearchResults([]); return }

    const cacheKey = query.toLowerCase()
    if (searchCache.current[cacheKey]) {
      setSearchResults(searchCache.current[cacheKey])
      setShowSearch(true)
      return
    }

    setSearching(true)
    try {
      const res = await fetch(`${API}/search?q=${encodeURIComponent(query)}&limit=5`)
      const data = await res.json()
      const results = data.results || []
      searchCache.current[cacheKey] = results
      setSearchResults(results)
      setShowSearch(results.length > 0)
    } catch { setSearchResults([]) }
    setSearching(false)
  }, [])

  const searchBreaches = async (companyName) => {
    if (!companyName || companyName.length < 2) return
    setBreachSearching(true)
    setShowBreaches(true)
    try {
      const res = await fetch(`${API}/breach-search?q=${encodeURIComponent(companyName)}&limit=5`)
      const data = await res.json()
      setBreachResults(data.incidents || [])
    } catch { setBreachResults([]) }
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
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => searchTicker(val), 250)
  }

  const selectResult = (result) => {
    setCompany(result.ticker_full || result.symbol)
    setShowSearch(false)
    setSearchResults([])
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    onScore({ company, breach_type: breachType, records_affected: parseInt(records), breach_date: date })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="relative">
        <label className="block text-xs text-slate-400 mb-1">Company / Ticker</label>
        <div className="relative">
          <input type="text" value={company} onChange={handleCompanyChange}
            onFocus={() => searchResults.length > 0 && setShowSearch(true)}
            onBlur={() => setTimeout(() => setShowSearch(false), 200)}
            placeholder="Search any stock: VEDL, Reliance, MSFT..."
            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            required />
          {searching && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <div className="animate-spin w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full" />
            </div>
          )}
        </div>
        {showSearch && searchResults.length > 0 && (
          <div className="absolute z-50 w-full mt-1 bg-slate-800 border border-slate-600 rounded-lg shadow-xl max-h-60 overflow-y-auto">
            {searchResults.map((r, i) => (
              <button key={i} type="button" onClick={() => selectResult(r)}
                className="w-full px-3 py-2 text-left hover:bg-slate-700 transition-colors border-b border-slate-700/50 last:border-0">
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

      {/* Breach Search Button */}
      <button type="button" onClick={() => searchBreaches(company)}
        disabled={!company || breachSearching}
        className="w-full bg-amber-600/20 border border-amber-500/30 hover:bg-amber-600/30 disabled:bg-slate-800 disabled:border-slate-700 text-amber-400 disabled:text-slate-500 text-xs font-medium py-2 rounded-lg transition-colors flex items-center justify-center gap-2">
        {breachSearching ? (
          <><div className="animate-spin w-3 h-3 border-2 border-amber-400 border-t-transparent rounded-full" /> Searching breaches...</>
        ) : (
          <><svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg> Find Breach Data from Internet</>
        )}
      </button>

      {/* Breach Search Results */}
      {showBreaches && breachResults.length > 0 && (
        <div className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400 font-medium">Found Breach Incidents</span>
            <button type="button" onClick={() => setShowBreaches(false)} className="text-xs text-slate-500 hover:text-white">✕</button>
          </div>
          {breachResults.map((inc, i) => (
            <button key={i} type="button" onClick={() => selectBreach(inc)}
              className="w-full text-left bg-slate-800/80 border border-slate-700/30 rounded-lg px-3 py-2 hover:border-amber-500/50 transition-colors">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-white font-medium">{inc.date}</span>
                <span className="text-xs text-amber-400 capitalize">{inc.breach_type?.replace('_', ' ')}</span>
              </div>
              <p className="text-xs text-slate-400 line-clamp-1">{inc.description}</p>
              {inc.records_affected > 0 && (
                <span className="text-xs text-slate-500">{(inc.records_affected / 1_000_000).toFixed(1)}M records</span>
              )}
            </button>
          ))}
          <p className="text-xs text-slate-500 text-center">Click an incident to auto-fill date, type, and records</p>
        </div>
      )}
      {showBreaches && breachResults.length === 0 && !breachSearching && (
        <div className="text-xs text-slate-500 text-center py-2">No breach incidents found</div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-slate-400 mb-1">Breach Type</label>
          <select value={breachType} onChange={e => setBreachType(e.target.value)}
            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500">
            <option value="data_leak">Data Leak</option>
            <option value="ransomware">Ransomware</option>
            <option value="hack">External Hack</option>
            <option value="insider">Insider Threat</option>
            <option value="phishing">Phishing</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Records Affected</label>
          <input type="number" value={records} onChange={e => setRecords(e.target.value)}
            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500" />
        </div>
      </div>
      <div>
        <label className="block text-xs text-slate-400 mb-1">Breach Date</label>
        <input type="date" value={date} onChange={e => setDate(e.target.value)}
          className="w-full bg-slate-800 border border-slate-600 rounded-lg px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500" />
      </div>
      <button type="submit" disabled={loading}
        className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 text-white font-medium py-2.5 rounded-lg transition-colors text-sm">
        {loading ? 'Analyzing...' : 'Analyze Risk'}
      </button>
    </form>
  )
}

// ── File Upload ─────────────────────────────────────────────────────────

function FileUpload({ onUpload, onAnalyze, loading }) {
  const [dragActive, setDragActive] = useState(false)
  const [file, setFile] = useState(null)

  const handleDrag = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') setDragActive(true)
    else if (e.type === 'dragleave') setDragActive(false)
  }, [])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    if (e.dataTransfer.files?.[0]) {
      setFile(e.dataTransfer.files[0])
    }
  }, [])

  const handleChange = (e) => {
    if (e.target.files?.[0]) setFile(e.target.files[0])
  }

  return (
    <div className="space-y-3">
      <form onDragEnter={handleDrag} onDragLeave={handleDrag} onDragOver={handleDrag} onDrop={handleDrop}>
        <label className={`flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-xl cursor-pointer transition-colors ${
          dragActive ? 'border-blue-500 bg-blue-500/10' : 'border-slate-600 bg-slate-800/30 hover:border-slate-500'
        }`}>
          <div className="flex flex-col items-center justify-center pt-2 pb-3">
            <svg className="w-8 h-8 mb-2 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <p className="text-xs text-slate-400">
              <span className="font-semibold text-blue-400">Click to upload</span> or drag and drop
            </p>
            <p className="text-xs text-slate-500 mt-1">CSV, XLSX, Excel, TSV</p>
          </div>
          <input type="file" className="hidden" accept=".csv,.xlsx,.xls,.tsv" onChange={handleChange} />
        </label>
      </form>

      {file && (
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-sm text-white">{file.name}</span>
            <span className="text-xs text-slate-500">({(file.size / 1024).toFixed(1)} KB)</span>
          </div>
          <button onClick={() => setFile(null)} className="text-xs text-slate-500 hover:text-red-400">Remove</button>
        </div>
      )}

      {file && (
        <div className="flex gap-2">
          <button onClick={() => onUpload(file)} disabled={loading}
            className="flex-1 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 text-white text-sm py-2 rounded-lg transition-colors">
            {loading ? 'Previewing...' : 'Preview'}
          </button>
          <button onClick={() => onAnalyze(file)} disabled={loading}
            className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 text-white text-sm py-2 rounded-lg transition-colors">
            {loading ? 'Analyzing...' : 'Analyze All'}
          </button>
        </div>
      )}
    </div>
  )
}

// ── Dataset Preview ─────────────────────────────────────────────────────

function DatasetPreview({ data }) {
  if (!data) return null
  return (
    <div className="bg-slate-800/40 border border-slate-700/50 rounded-2xl p-6">
      <h4 className="text-sm font-semibold text-white mb-3">Dataset Preview</h4>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-slate-800/50 rounded-lg p-3 text-center">
          <div className="text-lg font-bold text-white">{data.original_rows}</div>
          <div className="text-xs text-slate-500">Original Rows</div>
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3 text-center">
          <div className="text-lg font-bold text-emerald-400">{data.cleaned_rows}</div>
          <div className="text-xs text-slate-500">Cleaned Rows</div>
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3 text-center">
          <div className="text-lg font-bold text-blue-400">{(data.ticker_resolution_rate * 100).toFixed(0)}%</div>
          <div className="text-xs text-slate-500">Ticker Match</div>
        </div>
      </div>

      {data.warnings?.length > 0 && (
        <div className="mb-4 space-y-1">
          {data.warnings.slice(0, 5).map((w, i) => (
            <div key={i} className="text-xs text-amber-400 bg-amber-500/10 px-3 py-1.5 rounded-lg">{w}</div>
          ))}
        </div>
      )}

      {data.preview?.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-700">
                {Object.keys(data.preview[0]).map(col => (
                  <th key={col} className="text-left py-2 px-3 text-slate-400 font-medium capitalize">
                    {col.replace(/_/g, ' ')}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.preview.map((row, i) => (
                <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                  {Object.values(row).map((val, j) => (
                    <td key={j} className="py-2 px-3 text-slate-300">
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

// ── Batch Results ───────────────────────────────────────────────────────

function BatchResults({ data }) {
  const [expandedRow, setExpandedRow] = useState(null)

  if (!data) return null

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
    <div className="bg-slate-800/40 border border-slate-700/50 rounded-2xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h4 className="text-sm font-semibold text-white">Batch Analysis Results</h4>
        <button onClick={exportCSV}
          className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1">
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Export CSV
        </button>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-slate-800/50 rounded-lg p-3 text-center">
          <div className="text-lg font-bold text-white">{data.total}</div>
          <div className="text-xs text-slate-500">Total</div>
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3 text-center">
          <div className="text-lg font-bold text-emerald-400">{data.analyzed}</div>
          <div className="text-xs text-slate-500">Analyzed</div>
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3 text-center">
          <div className="text-lg font-bold text-red-400">{data.failed}</div>
          <div className="text-xs text-slate-500">Failed</div>
        </div>
      </div>

      <div className="overflow-x-auto max-h-[32rem] overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-slate-800 z-10">
            <tr className="border-b border-slate-700">
              <th className="text-left py-2 px-3 text-slate-400">Company</th>
              <th className="text-left py-2 px-3 text-slate-400">Ticker</th>
              <th className="text-left py-2 px-3 text-slate-400">Date</th>
              <th className="text-right py-2 px-3 text-slate-400">Score</th>
              <th className="text-left py-2 px-3 text-slate-400">Severity</th>
              <th className="text-left py-2 px-3 text-slate-400 min-w-[180px]">Probability Breakdown</th>
              <th className="text-right py-2 px-3 text-slate-400">Conf</th>
              <th className="text-left py-2 px-3 text-slate-400">Status</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((r, i) => (
              <>
                <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/30 cursor-pointer"
                  onClick={() => setExpandedRow(expandedRow === i ? null : i)}>
                  <td className="py-2 px-3 text-white font-medium">{r.company}</td>
                  <td className="py-2 px-3 text-slate-400">{r.ticker}</td>
                  <td className="py-2 px-3 text-slate-400">{r.breach_date}</td>
                  <td className="py-2 px-3 text-right font-mono font-bold"
                    style={{ color: SEVERITY_COLORS[r.prediction] || '#64748b' }}>
                    {r.risk_score || '-'}
                  </td>
                  <td className="py-2 px-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${SEVERITY_BG[r.prediction] || 'bg-slate-700 text-slate-400 border border-slate-700'}`}>
                      {r.prediction?.toUpperCase() || '-'}
                    </span>
                  </td>
                  <td className="py-2 px-3">
                    {r.probabilities && Object.keys(r.probabilities).length > 0 ? (
                      <div className="flex gap-1 items-center">
                        {['low', 'medium', 'high', 'critical'].map(sev => (
                          <div key={sev} className="flex-1" title={`${sev}: ${(r.probabilities[sev] * 100).toFixed(1)}%`}>
                            <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                              <div className="h-full rounded-full" style={{
                                width: `${(r.probabilities[sev] || 0) * 100}%`,
                                backgroundColor: SEVERITY_COLORS[sev],
                              }} />
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : <span className="text-slate-600">-</span>}
                  </td>
                  <td className="py-2 px-3 text-right text-slate-400">
                    {r.confidence ? `${(r.confidence * 100).toFixed(0)}%` : '-'}
                  </td>
                  <td className="py-2 px-3">
                    {r.status === 'ok' ? (
                      <span className="text-emerald-400">OK</span>
                    ) : (
                      <span className="text-red-400" title={r.error}>{r.status}</span>
                    )}
                  </td>
                </tr>
                {expandedRow === i && r.probabilities && (
                  <tr key={`${i}-detail`} className="border-b border-slate-800/50 bg-slate-900/50">
                    <td colSpan={8} className="px-4 py-3">
                      <div className="grid grid-cols-4 gap-4">
                        {['low', 'medium', 'high', 'critical'].map(sev => (
                          <div key={sev} className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: SEVERITY_COLORS[sev] }} />
                            <span className="text-xs text-slate-400 capitalize w-16">{sev}</span>
                            <div className="flex-1 h-2 bg-slate-700 rounded-full overflow-hidden">
                              <div className="h-full rounded-full transition-all" style={{
                                width: `${(r.probabilities[sev] || 0) * 100}%`,
                                backgroundColor: SEVERITY_COLORS[sev],
                              }} />
                            </div>
                            <span className="text-xs text-white font-mono w-12 text-right">
                              {((r.probabilities[sev] || 0) * 100).toFixed(1)}%
                            </span>
                          </div>
                        ))}
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500 mt-3">Click a row to expand probability breakdown</p>
    </div>
  )
}

// ── Explainability Panel ────────────────────────────────────────────────

function ExplainabilityPanel({ data }) {
  if (!data) return null

  return (
    <div className="bg-slate-800/40 border border-slate-700/50 rounded-2xl p-6">
      <div className="flex items-center gap-2 mb-4">
        <svg className="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
        </svg>
        <h3 className="text-lg font-bold text-white">How the Risk Score is Calculated</h3>
      </div>

      <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4 mb-6">
        <h4 className="text-sm font-semibold text-blue-400 mb-2">Methodology</h4>
        <p className="text-xs text-slate-300 leading-relaxed">{data.methodology}</p>
      </div>

      <div className="space-y-4">
        {data.steps.map((step, i) => (
          <div key={i} className="bg-slate-800/60 border border-slate-700/50 rounded-xl p-4">
            <div className="flex items-start gap-3">
              <div className="w-7 h-7 rounded-full bg-blue-600/20 border border-blue-500/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                <span className="text-xs font-bold text-blue-400">{step.step_number}</span>
              </div>
              <div className="flex-1 min-w-0">
                <h5 className="text-sm font-semibold text-white mb-1">{step.name}</h5>
                <p className="text-xs text-slate-400 mb-2">{step.description}</p>

                <div className="bg-slate-900/50 rounded-lg p-3 mb-2 font-mono text-xs text-slate-300">
                  {step.formula}
                </div>

                <div className="grid grid-cols-2 gap-2 mb-2">
                  {Object.entries(step.inputs).map(([key, val]) => (
                    <div key={key} className="text-xs">
                      <span className="text-slate-500">{key}: </span>
                      <span className="text-slate-300">
                        {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                      </span>
                    </div>
                  ))}
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-500">Output:</span>
                  <span className="text-sm font-semibold text-white">
                    {typeof step.output === 'number' ? step.output.toFixed(6) : String(step.output)}
                  </span>
                </div>

                <div className="mt-2 text-xs text-slate-400 bg-slate-800/50 rounded-lg p-2">
                  {step.interpretation}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Feature Contributions */}
      <div className="mt-6 bg-slate-800/60 border border-slate-700/50 rounded-xl p-4">
        <h4 className="text-sm font-semibold text-white mb-3">Feature Contributions to Risk Score</h4>
        <div className="space-y-2">
          {Object.entries(data.feature_contributions).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).map(([feat, val]) => (
            <div key={feat} className="flex items-center gap-3">
              <span className="w-40 text-xs text-slate-400 truncate">{feat.replace(/_/g, ' ')}</span>
              <div className="flex-1 h-2 bg-slate-700 rounded-full overflow-hidden">
                <div className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${Math.min(Math.abs(val) * 500, 100)}%`,
                    backgroundColor: val < 0 ? '#ef4444' : '#10b981',
                    marginLeft: val < 0 ? 'auto' : '0',
                  }} />
              </div>
              <span className={`w-16 text-xs text-right font-mono ${val < 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                {val > 0 ? '+' : ''}{val.toFixed(4)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Limitations */}
      <div className="mt-6 bg-amber-500/10 border border-amber-500/30 rounded-xl p-4">
        <h4 className="text-sm font-semibold text-amber-400 mb-2">Limitations & Caveats</h4>
        <ul className="space-y-1">
          {data.limitations.map((lim, i) => (
            <li key={i} className="text-xs text-slate-400 flex items-start gap-2">
              <span className="text-amber-400 mt-0.5">*</span>
              {lim}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

// ── Demo Card ───────────────────────────────────────────────────────────

function DemoCard({ demo, onClick, onExplain }) {
  const severityClass = demo.prediction ? SEVERITY_BG[demo.prediction] : 'bg-slate-700/50 text-slate-400 border border-slate-700'
  return (
    <button onClick={() => onClick(demo)}
      className="card-hover bg-slate-800/60 border border-slate-700/50 rounded-xl p-5 text-left w-full">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="text-white font-semibold">{demo.company}</h3>
          <span className="text-xs text-slate-500">{demo.ticker}</span>
        </div>
        {demo.risk_score && (
          <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${severityClass}`}>
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
        <div className="mt-3 pt-3 border-t border-slate-700/50 flex items-center justify-between">
          <span className="text-xs text-slate-500">Risk Score</span>
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold" style={{ color: SEVERITY_COLORS[demo.prediction] }}>
              {demo.risk_score}
            </span>
            <button onClick={(e) => { e.stopPropagation(); onExplain(demo) }}
              className="text-xs text-blue-400 hover:text-blue-300" title="Explain this score">
              Explain
            </button>
          </div>
        </div>
      )}
    </button>
  )
}

// ── Features Chart ──────────────────────────────────────────────────────

function LLMAnalysisPanel({ batchData }) {
  const [llmStatus, setLlmStatus] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [loading, setLoading] = useState(false)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [askLoading, setAskLoading] = useState(false)

  useEffect(() => {
    fetch(`${API}/llm/status`).then(r => r.json()).then(setLlmStatus).catch(() => {})
  }, [])

  const generateAnalysis = async () => {
    setLoading(true)
    try {
      const summary = `Dataset: ${batchData.total} companies, ${batchData.analyzed} analyzed, ${batchData.failed} failed. ` +
        `Results: ${batchData.results.map(r => `${r.company}(${r.ticker}): score=${r.risk_score}, ${r.prediction}`).join('; ')}`

      const res = await fetch(`${API}/llm/analyze-dataset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dataset_summary: summary, analysis_results: JSON.stringify(batchData.results) }),
      })
      if (!res.ok) throw new Error((await res.json()).detail)
      const data = await res.json()
      setAnalysis(data.analysis)
    } catch (e) { setAnalysis('Error: ' + e.message) }
    setLoading(false)
  }

  const askQuestion = async () => {
    if (!question.trim()) return
    setAskLoading(true)
    try {
      const context = `Dataset has ${batchData.analyzed} analyzed companies. Top results: ${
        batchData.results.filter(r => r.status === 'ok').slice(0, 5).map(
          r => `${r.company}: risk=${r.risk_score}, severity=${r.prediction}`
        ).join('; ')}`
      const res = await fetch(`${API}/llm/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, context }),
      })
      if (!res.ok) throw new Error((await res.json()).detail)
      const data = await res.json()
      setAnswer(data.answer)
    } catch (e) { setAnswer('Error: ' + e.message) }
    setAskLoading(false)
  }

  if (!llmStatus?.available) {
    return (
      <div className="bg-slate-800/40 border border-slate-700/50 rounded-2xl p-6 mt-6">
        <h3 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
          <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          LLM Analysis
        </h3>
        <p className="text-xs text-slate-400">
          Connect LM Studio (Qwen 3.5 9B) at <code className="bg-slate-700 px-1 rounded">192.168.56.1:1234</code> for AI-powered insights.
        </p>
        <p className="text-xs text-slate-500 mt-1">Start LM Studio and load a model to enable this feature.</p>
      </div>
    )
  }

  return (
    <div className="bg-slate-800/40 border border-slate-700/50 rounded-2xl p-6 mt-6">
      <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
        <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
        LLM Analysis
        <span className="text-xs text-emerald-400 font-normal">({llmStatus.default_model || 'connected'})</span>
      </h3>

      {/* Generate Analysis */}
      <button onClick={generateAnalysis} disabled={loading}
        className="w-full bg-purple-600/20 border border-purple-500/30 hover:bg-purple-600/30 disabled:bg-slate-800 text-purple-400 text-xs font-medium py-2 rounded-lg transition-colors mb-4">
        {loading ? 'Analyzing with LLM...' : 'Generate AI Risk Analysis'}
      </button>

      {analysis && (
        <div className="bg-slate-900/50 rounded-lg p-4 mb-4">
          <h4 className="text-xs font-semibold text-slate-300 mb-2">AI Analysis</h4>
          <div className="text-xs text-slate-300 whitespace-pre-wrap leading-relaxed">{analysis}</div>
        </div>
      )}

      {/* Ask Question */}
      <div className="border-t border-slate-700/50 pt-4">
        <h4 className="text-xs font-semibold text-slate-300 mb-2">Ask about this data</h4>
        <div className="flex gap-2">
          <input type="text" value={question} onChange={e => setQuestion(e.target.value)}
            placeholder="e.g., Which breach type causes the most financial damage?"
            className="flex-1 bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
            onKeyDown={e => e.key === 'Enter' && askQuestion()} />
          <button onClick={askQuestion} disabled={askLoading || !question.trim()}
            className="bg-purple-600 hover:bg-purple-500 disabled:bg-slate-700 text-white text-xs px-4 py-2 rounded-lg transition-colors">
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


function FeaturesChart({ features }) {
  const data = {
    labels: ['Day 0', 'Day +1', 'Day +5', 'Day +30'],
    datasets: [{
      label: 'Abnormal Return',
      data: [features.abnormal_return_day0, features.abnormal_return_day1,
             features.abnormal_return_day5, features.abnormal_return_day30],
      backgroundColor: [
        features.abnormal_return_day0 < 0 ? 'rgba(239,68,68,0.6)' : 'rgba(16,185,129,0.6)',
        features.abnormal_return_day1 < 0 ? 'rgba(239,68,68,0.6)' : 'rgba(16,185,129,0.6)',
        features.abnormal_return_day5 < 0 ? 'rgba(239,68,68,0.6)' : 'rgba(16,185,129,0.6)',
        features.abnormal_return_day30 < 0 ? 'rgba(239,68,68,0.6)' : 'rgba(16,185,129,0.6)',
      ],
      borderColor: [
        features.abnormal_return_day0 < 0 ? '#ef4444' : '#10b981',
        features.abnormal_return_day1 < 0 ? '#ef4444' : '#10b981',
        features.abnormal_return_day5 < 0 ? '#ef4444' : '#10b981',
        features.abnormal_return_day30 < 0 ? '#ef4444' : '#10b981',
      ],
      borderWidth: 1, borderRadius: 4,
    }],
  }
  const options = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { grid: { color: '#1e293b' }, ticks: { color: '#64748b' } },
      y: { grid: { color: '#1e293b' }, ticks: { color: '#64748b' } },
    },
  }
  return <div className="h-48"><Bar data={data} options={options} /></div>
}

// ── Main App ────────────────────────────────────────────────────────────

function App() {
  const [activeTab, setActiveTab] = useState('single')
  const [score, setScore] = useState(null)
  const [demos, setDemos] = useState([])
  const [loading, setLoading] = useState(false)
  const [demosLoading, setDemosLoading] = useState(false)
  const [error, setError] = useState(null)
  const [health, setHealth] = useState(null)

  // Upload state
  const [uploadData, setUploadData] = useState(null)
  const [batchData, setBatchData] = useState(null)

  // Explainability state
  const [explainData, setExplainData] = useState(null)
  const [explainLoading, setExplainLoading] = useState(false)

  // Settings state
  const [analysisConfig, setAnalysisConfig] = useState({
    estimation_window: 250, pre_event_window: 30, post_event_window: 60,
    recovery_max_days: 90, threshold_critical: -0.15, threshold_high: -0.07,
    threshold_medium: -0.02, car_short_start: -1, car_short_end: 1,
    car_long_start: -5, car_long_end: 30, benchmark: '^GSPC',
    start_date: '2010-01-01', min_records: 1000,
  })
  const [presets, setPresets] = useState([])

  const loadPresets = async () => {
    try {
      const res = await fetch(`${API}/config/presets`)
      setPresets(await res.json())
    } catch {}
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

  const handleExplain = async (demo) => {
    setExplainLoading(true); setError(null); setExplainData(null)
    try {
      const res = await fetch(`${API}/explain`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company: demo.company, breach_type: demo.breach_type || 'data_leak',
          records_affected: demo.pwn_count, breach_date: demo.breach_date,
        }),
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
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-blue-600 flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">BreachAlpha</h1>
              <p className="text-xs text-slate-500">Cyber-Financial Risk Quantifier</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${health?.status === 'ok' ? 'bg-emerald-400' : 'bg-slate-500'}`} />
            <span className="text-xs text-slate-500">{health?.model_loaded ? 'Model Ready' : 'No Model'}</span>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
        {/* Hero */}
        <div className="text-center mb-8">
          <h2 className="text-3xl font-bold text-white mb-3">Quantify Cyber Breach Impact</h2>
          <p className="text-slate-400 max-w-2xl mx-auto">
            Analyze how cybersecurity incidents affect stock prices. Upload a dataset or score individual companies.
          </p>
        </div>

        {/* Tabs */}
        <TabBar tabs={tabs} active={activeTab} onChange={setActiveTab} />

        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400 text-sm mb-6">{error}</div>
        )}

        {/* Single Analysis Tab */}
        {activeTab === 'single' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-4 space-y-6">
              <div className="bg-slate-800/40 border border-slate-700/50 rounded-2xl p-6">
                <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                  <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  Analyze a Company
                </h3>
                <ScoreForm onScore={handleScore} loading={loading} />
              </div>

              <div className="bg-slate-800/40 border border-slate-700/50 rounded-2xl p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                    <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    Famous Breaches
                  </h3>
                  <button onClick={loadDemos} disabled={demosLoading}
                    className="text-xs text-blue-400 hover:text-blue-300 disabled:text-slate-600">
                    {demosLoading ? 'Loading...' : 'Load Demos'}
                  </button>
                </div>
                <div className="space-y-3">
                  {demos.length === 0 && !demosLoading && (
                    <p className="text-xs text-slate-500 text-center py-4">Click "Load Demos" to see famous breach analysis</p>
                  )}
                  {demos.map((d, i) => (
                    <DemoCard key={i} demo={d} onClick={handleDemoClick} onExplain={handleExplain} />
                  ))}
                </div>
              </div>
            </div>

            <div className="lg:col-span-8 space-y-6">
              {!score && !error && (
                <div className="bg-slate-800/30 border border-slate-700/30 rounded-2xl p-12 text-center">
                  <svg className="w-16 h-16 text-slate-600 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
                      d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  <h3 className="text-lg font-semibold text-slate-400 mb-2">No Analysis Yet</h3>
                  <p className="text-sm text-slate-500">Enter a company name or load a demo to see the risk analysis</p>
                </div>
              )}

              {score && (
                <>
                  <div className="bg-slate-800/40 border border-slate-700/50 rounded-2xl p-6">
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <h3 className="text-xl font-bold text-white">{score.company}</h3>
                        <span className="text-sm text-slate-500">{score.ticker}</span>
                      </div>
                      <span className={`px-3 py-1.5 rounded-full text-xs font-semibold ${SEVERITY_BG[score.prediction] || 'bg-slate-700 text-slate-400 border border-slate-700'}`}>
                        {score.prediction?.toUpperCase() || 'N/A'}
                      </span>
                    </div>
                    <RiskGauge score={score.risk_score} prediction={score.prediction} />
                  </div>

                  <div className="bg-slate-800/40 border border-slate-700/50 rounded-2xl p-6">
                    <h4 className="text-sm font-semibold text-white mb-4">Severity Probability</h4>
                    <div className="space-y-3">
                      {Object.entries(score.probabilities || {}).map(([label, prob]) => (
                        <ProbabilityBar key={label} label={label} probability={prob} color={SEVERITY_COLORS[label]} />
                      ))}
                    </div>
                    <div className="mt-4 pt-3 border-t border-slate-700/50 flex items-center justify-between text-xs">
                      <span className="text-slate-500">Confidence</span>
                      <span className="text-white font-medium">{(score.confidence * 100).toFixed(1)}%</span>
                    </div>
                  </div>

                  {score.features && (
                    <div className="bg-slate-800/40 border border-slate-700/50 rounded-2xl p-6">
                      <h4 className="text-sm font-semibold text-white mb-4">Event Study Features</h4>
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-6">
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
            <div className="bg-slate-800/40 border border-slate-700/50 rounded-2xl p-6">
              <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                Upload Breach Dataset
              </h3>
              <p className="text-xs text-slate-400 mb-4">
                Upload a CSV, XLSX, or Excel file with breach data. The system will auto-detect columns
                like company name, breach date, and records affected.
              </p>
              <FileUpload onUpload={handleUpload} onAnalyze={handleAnalyze} loading={loading} />
            </div>

            {uploadData && <DatasetPreview data={uploadData} />}
            {batchData && <BatchResults data={batchData} />}
            {batchData && batchData.analyzed > 0 && <LLMAnalysisPanel batchData={batchData} />}
          </div>
        )}

        {/* Explain Tab */}
        {activeTab === 'explain' && (
          <div className="max-w-4xl mx-auto">
            {explainLoading && (
              <div className="text-center py-12">
                <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-4" />
                <p className="text-sm text-slate-400">Generating explanation...</p>
              </div>
            )}
            {!explainData && !explainLoading && (
              <div className="bg-slate-800/30 border border-slate-700/30 rounded-2xl p-12 text-center">
                <svg className="w-16 h-16 text-slate-600 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
                    d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                </svg>
                <h3 className="text-lg font-semibold text-slate-400 mb-2">No Explanation Yet</h3>
                <p className="text-sm text-slate-500">
                  Go to "Single Analysis", load a demo, and click "Explain" to see the full calculation breakdown
                </p>
              </div>
            )}
            {explainData && <ExplainabilityPanel data={explainData} />}
          </div>
        )}

        {/* Settings Tab */}
        {activeTab === 'settings' && (
          <div className="max-w-4xl mx-auto">
            <SettingsPanel
              config={analysisConfig}
              setConfig={setAnalysisConfig}
              presets={presets}
              onLoadPresets={loadPresets}
            />

            <div className="mt-6 bg-slate-800/40 border border-slate-700/50 rounded-2xl p-6">
              <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                <svg className="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Current Configuration
              </h3>
              <div className="bg-slate-900/50 rounded-lg p-4 font-mono text-xs text-slate-300 overflow-x-auto">
                <pre>{JSON.stringify(analysisConfig, null, 2)}</pre>
              </div>
              <p className="text-xs text-slate-500 mt-3">
                These settings apply to all analyses. Use presets for quick configuration or adjust individual parameters.
              </p>
            </div>
          </div>
        )}
      </main>

      <footer className="border-t border-slate-800 mt-12 py-6">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 text-center text-xs text-slate-600">
          BreachAlpha v0.1.0 — Cyber-Financial Risk Quantifier — Event Study Methodology (MacKinlay, 1997)
        </div>
      </footer>
    </div>
  )
}

export default App
