import { useState, useEffect, useCallback, useRef } from 'react'
import { Header } from '@/components/layout/Header'
import { TabBar } from '@/components/layout/TabBar'
import { Footer } from '@/components/layout/Footer'
import { ScoreForm } from '@/components/score/ScoreForm'
import { RiskGauge } from '@/components/score/RiskGauge'
import { ProbabilityBar } from '@/components/score/ProbabilityBar'
import { FeatureCard } from '@/components/score/FeatureCard'
import { FeaturesChart } from '@/components/score/FeaturesChart'
import { FileUpload } from '@/components/upload/FileUpload'
import { DatasetPreview } from '@/components/upload/DatasetPreview'
import { BatchResults } from '@/components/upload/BatchResults'
import { ExplainabilityPanel } from '@/components/explain/ExplainabilityPanel'
import { SettingsPanel } from '@/components/settings/SettingsPanel'
import { DemoCard } from '@/components/demos/DemoCard'
import { LLMAnalysisPanel } from '@/components/llm/LLMAnalysisPanel'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { cn, SEVERITY_COLORS, SEVERITY_CLASSES } from '@/lib/utils'

const API = '/api'

export default function App() {
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

  const abortRef = useRef(null)

  const loadPresets = useCallback(async () => {
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const res = await fetch(`${API}/config/presets`, { signal: controller.signal })
      setPresets(await res.json())
    } catch (e) {
      if (e.name !== 'AbortError') console.error('Failed to load presets:', e)
    }
  }, [])

  useEffect(() => {
    fetch(`${API}/health`).then(r => r.json()).then(setHealth)
      .catch(() => setHealth({ status: 'offline', model_loaded: false }))
  }, [])

  const loadDemos = useCallback(async () => {
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setDemosLoading(true)
    try {
      const res = await fetch(`${API}/demo`, { signal: controller.signal })
      setDemos(await res.json())
    } catch (e) {
      if (e.name !== 'AbortError') setError('Failed to load demo data. Is the backend running?')
    }
    setDemosLoading(false)
  }, [])

  const handleScore = useCallback(async (params) => {
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true); setError(null); setScore(null)
    try {
      const res = await fetch(`${API}/score/config`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          req: params,
          config: {
            estimation_window: analysisConfig.estimation_window,
            pre_event_window: analysisConfig.pre_event_window,
            post_event_window: analysisConfig.post_event_window,
            recovery_max_days: analysisConfig.recovery_max_days,
            threshold_critical: analysisConfig.threshold_critical,
            threshold_high: analysisConfig.threshold_high,
            threshold_medium: analysisConfig.threshold_medium,
            car_short_start: analysisConfig.car_short_start,
            car_short_end: analysisConfig.car_short_end,
            car_long_start: analysisConfig.car_long_start,
            car_long_end: analysisConfig.car_long_end,
            benchmark: analysisConfig.benchmark,
            start_date: analysisConfig.start_date,
            min_records: analysisConfig.min_records,
          },
        }),
      })
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail) }
      setScore(await res.json())
    } catch (e) { setError(e.message) }
    setLoading(false)
  }, [analysisConfig])

  const handleUpload = useCallback(async (file) => {
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true); setError(null); setUploadData(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch(`${API}/upload`, { method: 'POST', body: form, signal: controller.signal })
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail) }
      setUploadData(await res.json())
    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message)
    }
    setLoading(false)
  }, [])

  const handleAnalyze = useCallback(async (file) => {
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true); setError(null); setBatchData(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch(`${API}/upload/analyze`, { method: 'POST', body: form, signal: controller.signal })
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail) }
      setBatchData(await res.json())
    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message)
    }
    setLoading(false)
  }, [])

  const handleAutoExplain = useCallback(async (ticker) => {
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setExplainLoading(true); setError(null); setExplainData(null)
    try {
      const res = await fetch(`${API}/explain/auto`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({ company: ticker }),
      })
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail) }
      setExplainData(await res.json())
      setActiveTab('explain')
    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message)
    }
    setExplainLoading(false)
  }, [])

  const handleDemoClick = useCallback((demo) => {
    setScore({
      company: demo.company, ticker: demo.ticker,
      risk_score: demo.risk_score, prediction: demo.prediction,
      confidence: demo.confidence, features: null,
    })
  }, [])

  return (
    <div className="min-h-screen bg-background" role="application" aria-label="BreachAlpha cyber-financial risk quantifier">
      <a
        href="https://chai4.me/darkcharon3301"
        target="_blank"
        rel="noopener noreferrer"
        title="Support darkcharon3301 on Chai4Me"
        className="fixed bottom-4 right-4 sm:bottom-6 sm:right-6 z-[100] inline-flex items-center gap-2 px-4 py-2.5 rounded-xl font-mono text-xs font-semibold tracking-wide transition-all duration-200 shadow-lg hover:scale-105"
        style={{
          background: 'linear-gradient(135deg, #ff9500, #ffb340)',
          color: '#0a0f1a',
          boxShadow: '0 4px 20px rgba(255, 149, 0, 0.35), 0 0 40px rgba(255, 149, 0, 0.15)',
        }}
      >
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
        </svg>
        Support
      </a>

      <Header />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-7" role="main" aria-live="polite">
        <div className="text-center mb-7 fade-in">
          <h2 className="text-2xl sm:text-3xl font-bold mb-2 tracking-tight font-mono text-foreground leading-tight">
            Quantify Cyber Breach{' '}
            <span className="text-cyan">Impact</span>
          </h2>
          <p className="text-xs max-w-2xl mx-auto leading-relaxed text-secondary-foreground">
            Analyze how cybersecurity incidents affect stock prices using event study methodology.
          </p>
        </div>

        <TabBar active={activeTab} onChange={setActiveTab} />

        <div role="tabpanel" id={`panel-${activeTab}`} aria-labelledby={`tab-${activeTab}`}>
          {error && (
            <div className="rounded-xl p-4 mb-6 flex items-start gap-3 animate-in fade-in bg-red-500/5 border border-red-500/25 text-red-400" role="alert">
              <svg className="w-4 h-4 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div className="flex-1">
                <p className="font-semibold mb-0.5 text-xs tracking-wide uppercase">Analysis Error</p>
                <p className="opacity-80 text-xs">{error}</p>
                <button onClick={() => setError(null)} className="text-xs mt-1 underline hover:opacity-80 text-red-400 transition-opacity">
                  Dismiss
                </button>
              </div>
            </div>
          )}

          {activeTab === 'single' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-4 space-y-6">
                <div className="terminal-card corner-accent p-5 fade-in stagger-1">
                  <h3 className="text-xs font-semibold tracking-wider uppercase mb-4 flex items-center gap-2 font-mono text-dim">
                    <svg className="w-4 h-4 text-cyan" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    Analyze a Company
                  </h3>
                  <ScoreForm onScore={handleScore} loading={loading} />
                </div>

                <div className="terminal-card corner-accent p-5 fade-in stagger-2">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-xs font-semibold tracking-wider uppercase flex items-center gap-2 font-mono text-dim">
                      <svg className="w-4 h-4 text-amber" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      Famous Breaches
                    </h3>
                    <Button variant="secondary" size="sm" onClick={loadDemos} disabled={demosLoading} className="text-xs py-1 px-2.5">
                      {demosLoading ? (
                        <>
                          <div className="animate-spin w-2.5 h-2.5 border-2 border-cyan-400 border-t-transparent rounded-full" />
                          Loading
                        </>
                      ) : (
                        'Load Demos'
                      )}
                    </Button>
                  </div>
                  <div className="space-y-3">
                    {demos.length === 0 && !demosLoading && (
                      <div className="py-6 text-center">
                        <svg className="w-10 h-10 text-dim mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                        </svg>
                        <h3 className="text-sm font-semibold text-foreground mb-1">No Demos Loaded</h3>
                        <p className="text-xs text-secondary-foreground">Click "Load Demos" to analyze Equifax, Capital One, and Marriott breaches.</p>
                      </div>
                    )}
                    {demos.length === 0 && demosLoading && (
                      <div className="space-y-2.5">
                        {[1, 2, 3].map((i) => (
                          <div key={i} className="bg-card border border-border rounded-lg p-4">
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
                  <div className="terminal-card p-6 fade-in">
                    <div className="flex items-center gap-4 mb-5">
                      <Skeleton className="h-5 w-32" />
                      <Skeleton className="h-5 w-16 rounded-full" />
                    </div>
                    <div className="flex justify-center mb-5">
                      <Skeleton className="w-36 h-36 rounded-full" />
                    </div>
                    <div className="space-y-2.5">
                      {[1, 2, 3, 4].map((i) => (
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
                  <div className="terminal-card py-16 text-center fade-in">
                    <svg className="w-14 h-14 text-dim mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                    <h3 className="text-sm font-semibold text-foreground mb-1">No Analysis Yet</h3>
                    <p className="text-xs text-secondary-foreground">Enter a company name in the form or load a demo to see the risk analysis.</p>
                  </div>
                )}

                {score && (
                  <>
                    <div className="terminal-card corner-accent p-6 fade-in stagger-1">
                      <div className="flex items-center justify-between mb-4">
                        <div>
                          <h3 className="text-xl font-bold font-mono text-foreground">{score.company}</h3>
                          <span className="text-xs tracking-wider uppercase text-secondary-foreground">{score.ticker}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => handleAutoExplain(score.ticker || score.company)}
                            disabled={explainLoading}
                            className="text-[0.6875rem] py-1 px-2.5"
                          >
                            {explainLoading ? (
                              <>
                                <div className="animate-spin w-2.5 h-2.5 border-2 border-cyan-400 border-t-transparent rounded-full" />
                                Loading
                              </>
                            ) : (
                              <>
                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                                </svg>
                                Explain
                              </>
                            )}
                          </Button>
                          <span
                            className={cn(
                              'text-[0.625rem] px-1.5 py-0.5 rounded-full font-mono',
                              score.prediction && SEVERITY_CLASSES[score.prediction]
                                ? SEVERITY_CLASSES[score.prediction]
                                : 'bg-surface text-secondary-foreground border border-border'
                            )}
                          >
                            {score.prediction?.toUpperCase() || 'N/A'}
                          </span>
                        </div>
                      </div>
                      <RiskGauge score={score.risk_score} prediction={score.prediction} />
                    </div>

                    <div className="terminal-card corner-accent p-6 fade-in stagger-2">
                      <h4 className="text-xs font-semibold tracking-wider uppercase mb-4 font-mono text-dim">
                        Severity Probability
                      </h4>
                      <div className="space-y-3">
                        {Object.entries(score.probabilities || {}).map(([label, prob]) => (
                          <ProbabilityBar key={label} label={label} probability={prob} color={SEVERITY_COLORS[label]} />
                        ))}
                      </div>
                      <div className="mt-4 pt-3 flex items-center justify-between text-xs border-t border-border">
                        <span className="text-secondary-foreground">Confidence</span>
                        <span className="font-semibold text-cyan">{(score.confidence * 100).toFixed(1)}%</span>
                      </div>
                    </div>

                    {score.features && (
                      <div className="terminal-card corner-accent p-6 fade-in stagger-3">
                        <h4 className="text-xs font-semibold tracking-wider uppercase mb-4 font-mono text-dim">
                          Event Study Features
                        </h4>
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-6">
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
                        <h4 className="text-xs font-semibold tracking-wider uppercase mb-3 font-mono text-dim">
                          Abnormal Returns Timeline
                        </h4>
                        <FeaturesChart features={score.features} />
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          )}

          {activeTab === 'upload' && (
            <div className="max-w-4xl mx-auto space-y-6">
              <div className="terminal-card corner-accent p-6 fade-in stagger-1">
                <h3 className="text-xs font-semibold tracking-wider uppercase mb-4 flex items-center gap-2 font-mono text-dim">
                  <svg className="w-4 h-4 text-cyan" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  Upload Breach Dataset
                </h3>
                <p className="text-xs mb-4 leading-relaxed text-secondary-foreground">
                  Upload a CSV, XLSX, or Excel file with breach data. The system auto-detects columns
                  for company name, breach date, and records affected.
                </p>
                <FileUpload onUpload={handleUpload} onAnalyze={handleAnalyze} loading={loading} />
              </div>
              {loading && !uploadData && !batchData && (
                <div className="terminal-card p-6 fade-in">
                  <div className="space-y-3">
                    <Skeleton className="h-4 w-32 mb-4" />
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
                      {[1, 2, 3].map((i) => (
                        <Skeleton key={i} className="h-20 rounded-lg" />
                      ))}
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

          {activeTab === 'explain' && (
            <div className="max-w-4xl mx-auto">
              {explainLoading && (
                <div className="terminal-card p-12 text-center fade-in">
                  <div className="animate-spin w-7 h-7 border-2 border-cyan-500 border-t-transparent rounded-full mx-auto mb-4" role="status" aria-label="Loading explanation" />
                  <p className="text-sm text-secondary-foreground">Generating explainability report...</p>
                </div>
              )}
              {!explainData && !explainLoading && (
                <div className="terminal-card py-16 text-center fade-in">
                  <svg className="w-14 h-14 text-dim mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                  </svg>
                  <h3 className="text-sm font-semibold text-foreground mb-1">No Explanation Yet</h3>
                  <p className="text-xs text-secondary-foreground">
                    Search a ticker in "Single Analysis" and click "Explain" next to the risk score, or load a demo and click "Explain" on any card.
                  </p>
                </div>
              )}
              {explainData && <ExplainabilityPanel data={explainData} />}
            </div>
          )}

          {activeTab === 'settings' && (
            <div className="max-w-4xl mx-auto">
              <SettingsPanel config={analysisConfig} setConfig={setAnalysisConfig} presets={presets} onLoadPresets={loadPresets} />
              <div className="terminal-card corner-accent p-5 mt-6 fade-in stagger-1">
                <h3 className="text-xs font-semibold tracking-wider uppercase mb-4 flex items-center gap-2 font-mono text-dim">
                  <svg className="w-4 h-4 text-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Current Configuration
                </h3>
                <div className="rounded-lg p-4 text-xs overflow-x-auto bg-background border border-border font-mono text-secondary-foreground">
                  <pre>{JSON.stringify(analysisConfig, null, 2)}</pre>
                </div>
                <p className="text-[0.65rem] mt-3 text-dim">
                  These settings apply to all analyses. Use presets for quick config.
                </p>
              </div>
            </div>
          )}
        </div>
      </main>

      <Footer />
    </div>
  )
}
