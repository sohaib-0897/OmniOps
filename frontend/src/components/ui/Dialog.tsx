"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { X } from "lucide-react";

const modals = new Set<HTMLDialogElement>();
let bodyOverflow = "";
let returnFocus: HTMLElement | null = null;

/** Native modal semantics provide focus containment, Escape and inert background. */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  drawer = false,
  busy = false,
  compact = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  drawer?: boolean;
  busy?: boolean;
  compact?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [present, setPresent] = useState(open);
  const release = useRef<(() => void) | null>(null);
  const snapshot = useRef({ title, description, children });
  useEffect(() => { if (open) snapshot.current = { title, description, children }; });
  const displayed = open ? { title, description, children } : snapshot.current;
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open) {
      setPresent(true);
      dialog.dataset.state = "open";
      if (!dialog.open) {
        const previous = document.activeElement as HTMLElement | null;
        if (modals.size === 0) {
          bodyOverflow = document.body.style.overflow;
          returnFocus = previous;
        }
        modals.add(dialog);
        dialog.showModal();
        document.body.style.overflow = "hidden";
        release.current = () => {
          dialog.close();
          modals.delete(dialog);
          if (modals.size === 0) {
            document.body.style.overflow = bodyOverflow;
            if (returnFocus?.isConnected) returnFocus.focus();
            returnFocus = null;
          }
          release.current = null;
        };
      }
      return;
    }
    if (!dialog.open) return;
    dialog.dataset.state = "closing";
    const finish = () => {
      release.current?.();
      setPresent(false);
    };
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (motion.matches) { finish(); return; }
    const timer = window.setTimeout(finish, 160);
    const changed = () => { if (motion.matches) { window.clearTimeout(timer); finish(); } };
    motion.addEventListener("change", changed);
    return () => { window.clearTimeout(timer); motion.removeEventListener("change", changed); };
  }, [open]);
  useEffect(() => () => release.current?.(), []);
  return (
    <dialog
      ref={ref}
      data-drawer={drawer}
      aria-label={displayed.title}
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const elements = Array.from(
          event.currentTarget.querySelectorAll<HTMLElement>(
            'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], summary, [tabindex="0"]',
          ),
        ).filter((element) => element.getClientRects().length > 0);
        const first = elements[0],
          last = elements[elements.length - 1];
        if (!first) {
          event.preventDefault();
          return;
        }
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
      onClick={(event) => {
        if (!busy && event.target === event.currentTarget) {
          const rect = ref.current!.getBoundingClientRect();
          if (
            event.clientX < rect.left ||
            event.clientX > rect.right ||
            event.clientY < rect.top ||
            event.clientY > rect.bottom
          )
            onClose();
        }
      }}
      className={
        drawer
          ? "m-0 ml-auto h-dvh max-h-dvh w-full max-w-xl border-l border-zinc-700 bg-[#121315] p-0 text-zinc-100"
          : `max-h-[90dvh] w-[calc(100%_-_2rem)] ${compact ? "max-w-md" : "max-w-3xl"} rounded-lg border border-zinc-700 bg-[#121315] p-0 text-zinc-100`
      }
    >
      <div className="flex max-h-[inherit] flex-col">
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-zinc-800 p-4 sm:px-5">
          <div className="min-w-0">
            <h2 className="break-words text-base font-semibold">{displayed.title}</h2>
            {displayed.description && <p className="meta-copy mt-1">{displayed.description}</p>}
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={onClose}
            className="btn-icon"
            aria-label={`Close ${title}`}
          >
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="min-h-0 overflow-y-auto p-4 sm:p-5">
          {(open || present) && displayed.children}
        </div>
      </div>
    </dialog>
  );
}
