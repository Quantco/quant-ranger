import { cn } from '@/lib/utils'

export function ChevronIcon({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      className={cn(
        'size-4 flex-none origin-center p-[0.08rem] text-primary opacity-80 transition-[color,opacity,transform] duration-[120ms]',
        className
      )}
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
      viewBox="0 0 16 16"
    >
      <path d="m6 3 5 5-5 5" />
    </svg>
  )
}
