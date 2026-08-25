import { Dialog as DialogPrimitive } from '@base-ui/react/dialog'

import { cn } from '@/lib/utils'

const Dialog = DialogPrimitive.Root

function DialogTrigger(props: DialogPrimitive.Trigger.Props) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />
}

function DialogContent({ className, ...props }: DialogPrimitive.Popup.Props) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Backdrop
        className="fixed inset-0 z-50 min-h-dvh bg-black/35 supports-[-webkit-touch-callout:none]:absolute"
        data-slot="dialog-backdrop"
      />
      <DialogPrimitive.Viewport
        className="fixed inset-0 z-50 grid place-items-center overflow-y-auto p-4"
        data-slot="dialog-viewport"
      >
        <DialogPrimitive.Popup
          className={cn(
            'max-h-[calc(100dvh-2rem)] w-[min(32rem,calc(100vw-2rem))] overflow-auto rounded-small border border-border bg-white p-4 text-foreground shadow-[0_8px_24px_rgb(15_23_42/15%)] outline-none',
            className
          )}
          data-slot="dialog-content"
          {...props}
        />
      </DialogPrimitive.Viewport>
    </DialogPrimitive.Portal>
  )
}

function DialogTitle({ className, ...props }: DialogPrimitive.Title.Props) {
  return (
    <DialogPrimitive.Title className={cn('m-0 text-xl font-semibold', className)} data-slot="dialog-title" {...props} />
  )
}

function DialogDescription({ className, ...props }: DialogPrimitive.Description.Props) {
  return (
    <DialogPrimitive.Description
      className={cn('text-sm text-muted-foreground', className)}
      data-slot="dialog-description"
      {...props}
    />
  )
}

function DialogClose(props: DialogPrimitive.Close.Props) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />
}

export { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger }
