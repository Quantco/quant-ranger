import { createContext, useContext, type ComponentProps, type ReactNode } from 'react'
import { Legend, ResponsiveContainer, Tooltip, type DefaultLegendContentProps } from 'recharts'

import { cn } from '@/lib/utils'

export type ChartConfig = Record<string, { label: ReactNode }>

const ChartContext = createContext<ChartConfig | null>(null)

function useChart() {
  const config = useContext(ChartContext)
  if (config == null) throw new Error('Chart components must be used inside ChartContainer.')
  return config
}

export function ChartContainer({
  children,
  className,
  config,
  ...props
}: ComponentProps<'div'> & {
  children: ComponentProps<typeof ResponsiveContainer>['children']
  config: ChartConfig
}) {
  return (
    <ChartContext value={config}>
      <div className={cn('min-h-0 min-w-0 text-xs', className)} data-slot="chart" {...props}>
        <ResponsiveContainer initialDimension={{ height: 160, width: 320 }}>{children}</ResponsiveContainer>
      </div>
    </ChartContext>
  )
}

export const ChartLegend = Legend
export const ChartTooltip = Tooltip

function payloadValue(payload: object | undefined, key: string | undefined) {
  return payload && key && key in payload ? payload[key as keyof typeof payload] : undefined
}

export function ChartLegendContent({
  className,
  nameKey,
  payload,
  valueKey
}: DefaultLegendContentProps & { nameKey?: string; valueKey?: string }) {
  const config = useChart()
  if (!payload?.length) return null

  return (
    <div className={cn('grid max-h-full gap-1.5 overflow-auto pr-2 [scrollbar-gutter:stable]', className)}>
      {payload.map((item) => {
        const key = String(payloadValue(item.payload, nameKey) ?? item.dataKey ?? 'value')
        const value = payloadValue(item.payload, valueKey)
        return (
          <div className="grid grid-cols-[0.65rem_minmax(0,1fr)_auto] items-center gap-2" key={key}>
            <span
              aria-hidden="true"
              className="size-[0.65rem] rounded-[0.15rem]"
              style={{ backgroundColor: item.color }}
            />
            <span className="min-w-0 [overflow-wrap:anywhere]">{config[key]?.label ?? item.value}</span>
            {value != null && <strong className="tabular-nums">{String(value)}</strong>}
          </div>
        )
      })}
    </div>
  )
}
