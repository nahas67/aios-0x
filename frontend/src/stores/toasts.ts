/**
 * Global toast store. Command results, errors, and important stream events
 * surface here. Severe engine conditions additionally render in-page.
 */
import { useSyncExternalStore } from "react";

export type ToastKind = "info" | "ok" | "warn" | "bad";

export interface Toast {
  id: number;
  kind: ToastKind;
  title: string;
  detail?: string;
}

let toasts: Toast[] = [];
const listeners = new Set<() => void>();
let nextId = 1;

function emit() {
  for (const fn of listeners) fn();
}

export function pushToast(kind: ToastKind, title: string, detail?: string): void {
  const toast: Toast = { id: nextId++, kind, title, detail };
  toasts = [...toasts, toast].slice(-5);
  emit();
  window.setTimeout(() => dismissToast(toast.id), 6000);
}

export function dismissToast(id: number): void {
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}

export function useToasts(): Toast[] {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => toasts,
  );
}
