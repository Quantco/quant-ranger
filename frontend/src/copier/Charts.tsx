import { Pie, PieChart as RechartsPieChart } from 'recharts'

import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, type ChartConfig } from '../components/ui/chart'
import { displayValue } from '../lib/value'
import { repositoryName } from './dashboard'
import type { CountedValue, DashboardColumn, DashboardValue, FilterValue } from './dashboard'

interface PieChartProps {
  column: DashboardColumn
  data: CountedValue[]
  domain: FilterValue[]
  expanded: boolean
}

function displayValueLabel(column: DashboardColumn, value: DashboardValue) {
  const label = displayValue(value)
  return column.kind === 'repository' ? repositoryName(label) : label
}

function semanticColor(value: FilterValue) {
  if (value === true) return 'var(--color-success-chart)'
  if (value === false) return 'var(--color-error-chart)'
  if (value == null || value === '') return 'var(--color-chart-neutral)'
  return undefined
}

function chartColors(domain: FilterValue[]) {
  const categoryCount = domain.filter((value) => semanticColor(value) == null).length
  return new Map(
    domain.map((value, index) => {
      const hue = (250 + (index * 360) / categoryCount) % 360
      const color = semanticColor(value) ?? `oklch(65% 0.15 ${hue})`
      return [value, color]
    })
  )
}

export function PieChart({ column, data, domain, expanded }: PieChartProps) {
  const total = data.reduce((sum, { count }) => sum + count, 0)
  if (total === 0) return <p className="text-sm text-muted-foreground">No data for the selected filters.</p>

  const colors = chartColors(domain)
  const slices = data.map(({ count, value }, index) => ({
    configKey: `slice-${index}`,
    count,
    fill: colors.get(value),
    label: displayValueLabel(column, value)
  }))
  const config = Object.fromEntries(slices.map(({ configKey, label }) => [configKey, { label }])) satisfies ChartConfig

  return (
    <ChartContainer className={expanded ? 'h-64' : 'h-40'} config={config} key={expanded ? 'expanded' : 'compact'}>
      <RechartsPieChart accessibilityLayer aria-label={`${column.id} distribution`}>
        <Pie
          cx="28%"
          data={slices}
          dataKey="count"
          isAnimationActive={false}
          nameKey="label"
          outerRadius="44%"
          stroke="#fff"
          strokeWidth={1}
        />
        <ChartLegend
          align="right"
          content={
            <ChartLegendContent className={expanded ? 'max-h-60' : 'max-h-36'} nameKey="configKey" valueKey="count" />
          }
          itemSorter={null}
          layout="vertical"
          verticalAlign="middle"
          width="55%"
        />
        <ChartTooltip
          contentStyle={{
            background: '#fff',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-small)'
          }}
          cursor={false}
          formatter={(count, name) => [count, name]}
        />
      </RechartsPieChart>
    </ChartContainer>
  )
}
