// Small illustrations drawn as inline SVG: no chart library, and no style attributes (the content
// security policy and the lint rules forbid them). Colour comes from CSS classes on the shapes.
// Every chart is decorative (aria-hidden): the numbers it draws are always written next to it.

/** A change as a short rule under its number: its length is the size, its colour the direction. */
export function ChangeMark({ pct, scale = 30 }: { pct: number | null; scale?: number }) {
  const width = 40
  const reach = pct === null ? 0 : Math.max(Math.min(Math.abs(pct) / scale, 1) * width, 2)
  return (
    <svg className="chart chart--mark" viewBox={`0 0 ${width} 4`} width={width} height={4} aria-hidden="true" focusable="false">
      <rect className="chart__track" x={0} y={1} width={width} height={2} rx={1} />
      {pct !== null && <rect className={pct >= 0 ? 'chart__up' : 'chart__down'} x={width - reach} y={0} width={reach} height={4} rx={1} />}
    </svg>
  )
}

/** How far a move went against the investor's threshold: the bar is the move, the tick the threshold. */
export function ThresholdMeter({ value, threshold }: { value: number; threshold: number }) {
  const width = 96
  const top = Math.max(Math.abs(value), Math.abs(threshold)) * 1.25 || 1
  const reach = (Math.abs(value) / top) * width
  const tick = (Math.abs(threshold) / top) * width
  return (
    <svg className="chart chart--meter" viewBox={`0 0 ${width} 10`} width={width} height={10} aria-hidden="true" focusable="false">
      <rect className="chart__track" x={0} y={3} width={width} height={4} rx={2} />
      <rect className={value >= 0 ? 'chart__up' : 'chart__down'} x={0} y={2} width={Math.max(reach, 2)} height={6} rx={3} />
      <line className="chart__tick" x1={tick} x2={tick} y1={0} y2={10} />
    </svg>
  )
}

/** A share of a whole, 0 to 100: a slim gauge. */
export function Gauge({ pct }: { pct: number }) {
  const width = 120
  const reach = (Math.max(0, Math.min(pct, 100)) / 100) * width
  return (
    <svg className="chart chart--gauge" viewBox={`0 0 ${width} 8`} width={width} height={8} aria-hidden="true" focusable="false">
      <rect className="chart__track" x={0} y={1} width={width} height={6} rx={3} />
      <rect className={pct >= 20 ? 'chart__down' : 'chart__accent'} x={0} y={1} width={Math.max(reach, 2)} height={6} rx={3} />
    </svg>
  )
}

export interface BarPoint {
  label: string
  value: number
  /** A second, smaller series drawn inside the bar (PAT inside revenue). */
  inner?: number
}

/** Quarters as bars, oldest on the left; the latest one in the accent colour. */
export function QuarterBars({ points, height = 96 }: { points: BarPoint[]; height?: number }) {
  if (points.length === 0) return null
  const gap = 6
  const bar = 22
  const width = points.length * (bar + gap) - gap
  const top = Math.max(...points.map((p) => Math.max(p.value, p.inner ?? 0)), 1)
  const scale = (v: number) => (Math.max(v, 0) / top) * (height - 4)
  return (
    <svg className="chart chart--quarters" viewBox={`0 0 ${width} ${height}`} width={width * 2} height={height} preserveAspectRatio="none" aria-hidden="true" focusable="false">
      {points.map((p, i) => {
        const x = i * (bar + gap)
        const h = scale(p.value)
        const latest = i === points.length - 1
        return (
          <g key={p.label}>
            <rect className={latest ? 'chart__bar chart__bar--latest' : 'chart__bar'} x={x} y={height - h} width={bar} height={h} rx={3} />
            {p.inner !== undefined && p.inner > 0 && (
              <rect className="chart__inner" x={x + 5} y={height - scale(p.inner)} width={bar - 10} height={scale(p.inner)} rx={2} />
            )}
          </g>
        )
      })}
    </svg>
  )
}

/** Counts as one stacked bar, in the order given. */
export function StackBar({ parts }: { parts: { key: string; count: number; className: string }[] }) {
  const total = parts.reduce((sum, p) => sum + p.count, 0)
  if (total === 0) return null
  const width = 240
  const starts = parts.map((_, i) => parts.slice(0, i).reduce((sum, p) => sum + (p.count / total) * width, 0))
  return (
    <svg className="chart chart--stack" viewBox={`0 0 ${width} 10`} width="100%" height={10} preserveAspectRatio="none" aria-hidden="true" focusable="false">
      {parts.map((p, i) => {
        const w = (p.count / total) * width
        return <rect key={p.key} className={p.className} x={starts[i]} y={0} width={Math.max(w - 2, 0)} height={10} rx={2} />
      })}
    </svg>
  )
}
