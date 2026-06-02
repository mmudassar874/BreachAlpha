import { useState, useEffect, useCallback, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useDebounce } from '@/hooks/useDebounce'
import { cn } from '@/lib/utils'

const API = '/api'

const BREACH_TYPES = [
  { value: 'data_leak', label: 'Data Leak' },
  { value: 'ransomware', label: 'Ransomware' },
  { value: 'hack', label: 'External Hack' },
  { value: 'insider', label: 'Insider Threat' },
  { value: 'phishing', label: 'Phishing' },
]

export function ScoreForm({ onScore, loading }) {
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
  const [activeIdx, setActiveIdx] = useState(-1)

  const searchCache = useRef({})
  const abortRef = useRef(null)
  const searchRef = useRef(null)

  const debouncedCompany = useDebounce(company, 300)

  const searchTicker = useCallback(async (query) => {
    if (query.length < 2) {
      setSearchResults([])
      setSearching(false)
      return
    }
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
    } catch (e) {
      if (e.name !== 'AbortError') setSearchResults([])
    }
    if (!controller.signal.aborted) setSearching(false)
  }, [])

  useEffect(() => {
    if (debouncedCompany.length < 2) {
      setSearchResults([])
      setSearching(false)
      return
    }
    searchTicker(debouncedCompany)
  }, [debouncedCompany, searchTicker])

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
    } catch {
      setBreachResults([])
      setBreachError('Search failed — backend may be offline')
    }
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
    if (val.length < 2) {
      setSearchResults([])
      setSearching(false)
      setShowSearch(false)
    }
  }

  const selectResult = (result) => {
    if (abortRef.current) abortRef.current.abort()
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
      e.preventDefault()
      setActiveIdx((i) => Math.min(i + 1, searchResults.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx((i) => Math.max(i - 1, -1))
    } else if (e.key === 'Enter' && activeIdx >= 0) {
      e.preventDefault()
      selectResult(searchResults[activeIdx])
    } else if (e.key === 'Escape') {
      setShowSearch(false)
      setActiveIdx(-1)
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4">
      <div className="relative">
        <label className="text-sm font-medium text-foreground mb-1.5 block font-sans" htmlFor="company-input">
          Company / Ticker
        </label>
        <div className="relative">
          <Input
            id="company-input"
            type="text"
            value={company}
            onChange={handleCompanyChange}
            onFocus={() => searchResults.length > 0 && setShowSearch(true)}
            onBlur={() => setTimeout(() => { setShowSearch(false); setActiveIdx(-1) }, 200)}
            onKeyDown={handleSearchKeyDown}
            placeholder="Search any stock: VEDL, Reliance, MSFT..."
            className={cn(validationError && 'border-red-500 focus-visible:ring-red-500')}
            aria-invalid={!!validationError}
            aria-describedby={validationError ? 'company-error' : undefined}
            aria-autocomplete="list"
            autoComplete="off"
            required
          />
          {searching && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2" aria-hidden="true">
              <div className="animate-spin w-3.5 h-3.5 border-2 border-cyan-500 border-t-transparent rounded-full" />
            </div>
          )}
        </div>
        {validationError && (
          <p id="company-error" className="text-xs text-red-400 mt-1" role="alert">
            {validationError}
          </p>
        )}
        {showSearch && (
          <div
            ref={searchRef}
            className="absolute z-50 w-full mt-1 bg-surface-overlay border border-border rounded-lg shadow-xl max-h-60 overflow-y-auto"
            role="listbox"
            aria-label="Search results"
          >
            {searching && searchResults.length === 0 && (
              <div className="p-2 space-y-1.5">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="flex items-center gap-2.5 px-2 py-1.5">
                    <Skeleton className="h-4 w-16 rounded" />
                    <Skeleton className="h-3 flex-1 rounded" />
                  </div>
                ))}
              </div>
            )}
            {!searching && searchResults.length === 0 && company.length >= 2 && (
              <div className="px-3 py-2.5 text-xs text-secondary-foreground text-center">
                No results found
              </div>
            )}
            {searchResults.map((r, i) => (
              <button
                key={i}
                type="button"
                role="option"
                aria-selected={i === activeIdx}
                onClick={() => selectResult(r)}
                className={cn(
                  'w-full px-3 py-2 text-left transition-colors duration-200 border-b border-border/30 last:border-0',
                  i === activeIdx ? 'bg-cyan-600/20' : 'hover:bg-surface'
                )}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-sm text-foreground font-medium">
                      {r.ticker_full || r.symbol}
                    </span>
                    <span className="text-xs text-secondary-foreground ml-2">{r.exchange}</span>
                  </div>
                  {r.price && (
                    <span className="text-xs text-emerald-400 font-mono">
                      {r.currency === 'INR' ? '\u20B9' : '$'}{r.price?.toFixed(2)}
                    </span>
                  )}
                </div>
                <div className="text-xs text-secondary-foreground truncate">{r.name}</div>
              </button>
            ))}
          </div>
        )}
      </div>

      <Button
        type="button"
        variant="secondary"
        onClick={() => searchBreaches(company)}
        disabled={!company || breachSearching}
        className="w-full justify-center"
      >
        {breachSearching ? (
          <>
            <div className="animate-spin w-3 h-3 border-2 border-amber-400 border-t-transparent rounded-full" />
            Searching...
          </>
        ) : (
          <>
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            Find Breach Data from Internet
          </>
        )}
      </Button>

      {showBreaches && breachResults.length > 0 && (
        <div className="bg-card border border-border rounded-lg p-3 space-y-2 fade-in" role="listbox" aria-label="Breach incidents">
          <div className="flex items-center justify-between">
            <span className="text-xs text-secondary-foreground font-medium">Breach Incidents Found</span>
            <button
              type="button"
              onClick={() => setShowBreaches(false)}
              className="text-xs text-secondary-foreground hover:text-foreground transition-colors"
              aria-label="Close breach results"
            >
              &#x2715;
            </button>
          </div>
          {breachResults.map((inc, i) => (
            <button
              key={i}
              type="button"
              onClick={() => selectBreach(inc)}
              role="option"
              className="w-full text-left bg-surface border border-border rounded-lg px-3 py-2 hover:border-amber-500/40 transition-all duration-200 hover:bg-surface-raised"
            >
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-xs text-foreground font-medium">{inc.date}</span>
                <span
                  className={cn(
                    'text-[0.65rem] px-1.5 py-0.5 rounded-full font-mono',
                    inc.breach_type === 'ransomware'
                      ? 'bg-red-500/15 text-red-400 border border-red-500/20'
                      : 'bg-amber-500/15 text-amber-400 border border-amber-500/20'
                  )}
                >
                  {inc.breach_type?.replace(/_/g, ' ')}
                </span>
              </div>
              <p className="text-xs text-secondary-foreground line-clamp-1">{inc.description}</p>
              {inc.records_affected > 0 && (
                <span className="text-[0.65rem] text-secondary-foreground mt-0.5 block">
                  {(inc.records_affected / 1_000_000).toFixed(1)}M records
                </span>
              )}
            </button>
          ))}
          <p className="text-[0.65rem] text-secondary-foreground text-center">
            Click an incident to auto-fill
          </p>
        </div>
      )}
      {showBreaches && breachError && (
        <p className="text-xs text-secondary-foreground text-center py-1" role="alert">
          {breachError}
        </p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label htmlFor="breach-type" className="text-sm font-medium text-foreground mb-1.5 block font-sans">Breach Type</label>
          <Select id="breach-type" value={breachType} onValueChange={setBreachType}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {BREACH_TYPES.map((bt) => (
                <SelectItem key={bt.value} value={bt.value}>
                  {bt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <label htmlFor="records" className="text-sm font-medium text-foreground mb-1.5 block font-sans">Records Affected</label>
          <Input
            id="records"
            type="number"
            value={records}
            onChange={(e) => setRecords(e.target.value)}
            min="0"
          />
        </div>
      </div>
      <div>
        <label htmlFor="breach-date" className="text-sm font-medium text-foreground mb-1.5 block font-sans">Breach Date</label>
        <Input id="breach-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </div>
      <Button type="submit" disabled={loading} className="w-full py-2.5">
        {loading ? (
          <>
            <div className="animate-spin w-3.5 h-3.5 border-2 border-white/60 border-t-transparent rounded-full" />
            Analyzing...
          </>
        ) : (
          'Analyze Risk'
        )}
      </Button>
    </form>
  )
}
