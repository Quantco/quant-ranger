import { createContext, useContext, type ComponentProps, type ReactNode } from 'react'
import { Legend, ResponsiveContainer, Tooltip, type LegendPayload } from 'recharts'

import { cn } from '@/lib/class-merge'

export type ChartConfig = Record<string, { label: ReactNode }>

const ChartContext = createContext<ChartConfig | null>(null)

const useChart = () => {
  const config = useContext(ChartContext)
  if (config == null) throw new Error('Chart components must be used inside ChartContainer.')
  return config
}

export const ChartContainer = ({
  children,
  className,
  config,
  ...props
}: ComponentProps<'div'> & {
  children: ComponentProps<typeof ResponsiveContainer>['children']
  config: ChartConfig
}) => (
  <ChartContext value={config}>
    <div className={cn('min-h-0 min-w-0 text-xs', className)} data-slot="chart" {...props}>
      <ResponsiveContainer initialDimension={{ height: 160, width: 320 }}>{children}</ResponsiveContainer>
    </div>
  </ChartContext>
)

export const ChartLegend = Legend
export const ChartTooltip = Tooltip

const payloadValue = (payload: unknown, key: string | undefined): unknown =>
  key != null && isRecord(payload) ? payload[key] : undefined

const isRecord = (value: unknown): value is Record<PropertyKey, unknown> => typeof value === 'object' && value !== null

const stringValue = (value: unknown): string | undefined => {
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  return undefined
}

type ChartLegendContentProps = {
  className?: string
  nameKey?: string
  payload?: readonly LegendPayload[]
  valueKey?: string
}

export const ChartLegendContent = ({ className, nameKey, payload, valueKey }: ChartLegendContentProps) => {
  const config = useChart()
  if (payload == null || payload.length === 0) return null

  return (
    <div className={cn('grid max-h-full gap-1.5 overflow-auto pr-2', className)}>
      {payload.map((item) => {
        const key = stringValue(payloadValue(item.payload, nameKey)) ?? stringValue(item.dataKey) ?? 'value'
        const value = payloadValue(item.payload, valueKey)
        const displayedValue = stringValue(value)
        return (
          <div className="flex items-center gap-2" key={key}>
            <span
              aria-hidden="true"
              className="size-2.5 flex-none rounded-sm"
              style={{ backgroundColor: item.color }}
            />
            <span className="min-w-0 flex-1 wrap-anywhere">{config[key]?.label ?? item.value}</span>
            {displayedValue != null && <strong className="tabular-nums">{displayedValue}</strong>}
          </div>
        )
      })}
    </div>
  )
}
