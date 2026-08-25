import { Button } from '../components/ui/button'
import { Textarea } from '../components/ui/textarea'
import { useClipboard } from '../hooks/useClipboard'
import { cn } from '../lib/utils'

function CopyIcon({ copied }: { copied: boolean }) {
  return copied ? (
    <svg
      aria-hidden="true"
      className="size-full"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
      viewBox="0 0 24 24"
    >
      <path d="m5 12 4 4L19 6" />
    </svg>
  ) : (
    <svg
      aria-hidden="true"
      className="size-full"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
      viewBox="0 0 24 24"
    >
      <rect height="13" rx="2" width="13" x="9" y="9" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  )
}

export function CopyableRepositoryList({ label, value }: { label: string; value: string }) {
  const { copy, copyState } = useClipboard()
  const copyLabel =
    copyState === 'copied'
      ? 'Copied'
      : copyState === 'failed'
        ? 'Could not copy'
        : `Copy ${label.toLocaleLowerCase()} repository names`

  return (
    <div className="relative">
      <Textarea
        aria-label={`${label} repository names`}
        className="min-h-32 pr-[2.9rem] font-mono"
        onFocus={(event) => event.currentTarget.select()}
        readOnly
        value={value}
      />
      <Button
        aria-label={copyLabel}
        className={cn(
          'absolute top-[0.45rem] right-[0.45rem] grid size-8 rounded-[0.3rem] border border-border bg-white p-[0.4rem] text-muted-foreground hover:bg-muted hover:text-foreground',
          copyState === 'copied' && 'text-success'
        )}
        onClick={() => void copy(value)}
        title={copyLabel}
        type="button"
        variant="ghost"
      >
        <CopyIcon copied={copyState === 'copied'} />
      </Button>
    </div>
  )
}
