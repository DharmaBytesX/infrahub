import {
  Dialog as AriaDialog,
  type DialogProps as AriaDialogProps,
  Modal as AriaModal,
  type ModalOverlayProps as AriaModalOverlayProps,
} from "react-aria-components";

import { ModalOverlay } from "@/shared/components/aria/modal";
import { Stacked } from "@/shared/components/aria/utils/stacked";
import { DismissGuardContext, useDismissGuard } from "@/shared/hooks/useDismissGuard";
import { classNames } from "@/shared/utils/common";

export interface SheetProps
  extends Pick<AriaDialogProps, "aria-label" | "children">,
    Omit<AriaModalOverlayProps, "children"> {}

export function Sheet({
  isOpen,
  children,
  className,
  "aria-label": ariaLabel,
  onOpenChange,
  style,
  ...props
}: SheetProps) {
  const { setDismissable, guardedOnOpenChange } = useDismissGuard(onOpenChange);

  return (
    <DismissGuardContext value={{ setDismissable }}>
      <ModalOverlay isOpen={isOpen} onOpenChange={guardedOnOpenChange}>
        {({ state: { isOpen } }) => (
          <Stacked group="sheet" isStacked={isOpen}>
            {(depth) => (
              <AriaModal
                className={classNames(
                  "no-scrollbar fixed top-2 bottom-2 w-100 overflow-auto rounded-xl bg-white p-3 outline-hidden transition-all",
                  "data-entering:slide-in-from-right-1/2 data-entering:animate-in data-entering:duration-200 data-entering:ease-out",
                  "data-exiting:slide-out-to-right-1/2 data-exiting:animate-out data-exiting:duration-150 data-exiting:ease-in",
                  className
                )}
                style={{
                  ...style,
                  right: `${8 + depth * 40}px`,
                  scale: 1 - depth * 0.02,
                }}
                {...props}
              >
                <AriaDialog aria-label={ariaLabel ?? "sheet"} className="outline-hidden">
                  {children}
                </AriaDialog>
              </AriaModal>
            )}
          </Stacked>
        )}
      </ModalOverlay>
    </DismissGuardContext>
  );
}
