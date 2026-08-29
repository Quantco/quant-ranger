import { CheckIcon, CopyIcon } from 'lucide-react'

import { Button } from '../components/ui/button'
import { Textarea } from '../components/ui/textarea'
import { useClipboard } from '../hooks/useClipboard'
import { cn } from '../lib/utils'

function CopyStateIcon({ copied }: { copied: boolean }) {
  const Icon = copied ? CheckIcon : CopyIcon

  return <Icon aria-hidden="true" className="size-full" />
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
        className="min-h-32 pr-12 font-mono"
        onFocus={(event) => event.currentTarget.select()}
        readOnly
        value={value}
      />
      <Button
        aria-label={copyLabel}
        className={cn(
          'absolute top-2 right-2 grid size-8 rounded-md border border-border bg-white p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground',
          copyState === 'copied' && 'text-success'
        )}
        onClick={() => void copy(value)}
        title={copyLabel}
        type="button"
        variant="ghost"
      >
        <CopyStateIcon copied={copyState === 'copied'} />
      </Button>
    </div>
  )
}
