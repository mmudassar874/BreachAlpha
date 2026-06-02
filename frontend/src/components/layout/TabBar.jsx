import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

const TABS = [
  { value: 'single', label: 'Score' },
  { value: 'upload', label: 'Upload' },
  { value: 'explain', label: 'Explain' },
  { value: 'settings', label: 'Settings' },
]

export function TabBar({ active, onChange }) {
  return (
    <Tabs value={active} onValueChange={onChange} className="mb-6 fade-in stagger-1">
      <TabsList
        className="w-full bg-surface border border-border rounded-xl p-1 h-auto gap-0.5"
        role="tablist"
        aria-label="Analysis sections"
      >
        {TABS.map((tab) => (
          <TabsTrigger
            key={tab.value}
            value={tab.value}
            className="flex-1 py-2.5 px-3 text-xs font-semibold font-mono tracking-wide rounded-lg text-dim border border-transparent transition-all duration-200 ease-out data-[state=active]:bg-cyan/10 data-[state=active]:text-cyan data-[state=active]:border-cyan/20 data-[state=active]:shadow-[0_0_16px_rgba(0,240,255,0.08)] hover:text-secondary-foreground"
          >
            {tab.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  )
}
