import { Dialog as DialogPrimitive } from '@base-ui/react/dialog'

import { cn } from '@/lib/class-merge'

const Dialog = DialogPrimitive.Root

const DialogTrigger = (props: DialogPrimitive.Trigger.Props) => (
  <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />
)

const DialogContent = ({ className, ...props }: DialogPrimitive.Popup.Props) => (
  <DialogPrimitive.Portal>
    <DialogPrimitive.Backdrop className="fixed inset-0 z-50 min-h-dvh bg-black/35" data-slot="dialog-backdrop" />
    <DialogPrimitive.Viewport
      className="fixed inset-0 z-50 grid place-items-center overflow-y-auto p-4"
      data-slot="dialog-viewport"
    >
      <DialogPrimitive.Popup
        className={cn(
          'max-h-full w-full max-w-lg overflow-auto rounded-md border border-border bg-white p-4 text-foreground shadow-xl outline-none',
          className
        )}
        data-slot="dialog-content"
        {...props}
      />
    </DialogPrimitive.Viewport>
  </DialogPrimitive.Portal>
)

const DialogTitle = ({ className, ...props }: DialogPrimitive.Title.Props) => (
  <DialogPrimitive.Title className={cn('m-0 text-xl font-semibold', className)} data-slot="dialog-title" {...props} />
)

const DialogDescription = ({ className, ...props }: DialogPrimitive.Description.Props) => (
  <DialogPrimitive.Description
    className={cn('text-sm text-muted-foreground', className)}
    data-slot="dialog-description"
    {...props}
  />
)

const DialogClose = (props: DialogPrimitive.Close.Props) => (
  <DialogPrimitive.Close data-slot="dialog-close" {...props} />
)

export { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger }
