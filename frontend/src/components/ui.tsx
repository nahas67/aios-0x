/**
 * Shared UI primitives. Everything visual composes from here so the design
 * language stays coherent (Figma-extracted tokens in styles/tokens.css).
 */
import { useEffect, useRef, type ReactNode } from "react";
import { pushToast } from "../stores/toasts";

export function Panel({
  title,
  right,
  children,
  className = "",
}: {
  title?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {title !== undefined && (
        <div className="ph">
          <h2>{title}</h2>
          <div className="grow" />
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function Pill({ tone = "dim", children }: { tone?: string; children: ReactNode }) {
  return <span className={`pill ${tone}`}>{children}</span>;
}

export function Dot({ tone = "dim" }: { tone?: string }) {
  return <span className={`dot ${tone}`} />;
}

export function Skeleton({ h = 13, w = "100%" }: { h?: number; w?: string | number }) {
  return <div className="skel" style={{ height: h, width: w }} />;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function ErrorBox({ title, detail }: { title: string; detail?: string | null }) {
  return (
    <div className="error-box" role="alert">
      <div className="t">{title}</div>
      {detail ? <code>{detail}</code> : null}
    </div>
  );
}

export interface Column<T> {
  key: string;
  label: string;
  render?: (row: T) => ReactNode;
  numeric?: boolean;
  onRowClick?: boolean;
}

export function DataTable<T>({
  columns,
  rows,
  onRowClick,
  rowKey,
  empty = "No data",
}: {
  columns: Column<T>[];
  rows: T[] | null | undefined;
  onRowClick?: (row: T) => void;
  rowKey: (row: T, index?: number) => string;
  empty?: string;
}) {
  if (!rows) {
    return (
      <div>
        <Skeleton />
        <Skeleton />
        <Skeleton w="70%" />
      </div>
    );
  }
  if (rows.length === 0) return <Empty>{empty}</Empty>;
  return (
    <table className="dtable">
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c.key} style={c.numeric ? { textAlign: "right" } : undefined}>
              {c.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={rowKey(row)}
            className={onRowClick ? "clickable" : undefined}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
          >
            {columns.map((c) => (
              <td key={c.key} className={c.numeric ? "num" : undefined}>
                {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key] ?? "—")}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
    </div>
  );
}

export function KV({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="kv">
      <span className="k">{k}</span>
      <span>{v}</span>
    </div>
  );
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: readonly T[];
  value: T;
  onChange: (t: T) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t}
          role="tab"
          aria-selected={t === value}
          className={t === value ? "active" : ""}
          onClick={() => onChange(t)}
          type="button"
        >
          {t}
        </button>
      ))}
    </div>
  );
}

export function Modal({
  title,
  onClose,
  children,
  width = 460,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  width?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    ref.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-back" onClick={onClose}>
      <div
        className="modal"
        style={{ maxWidth: width }}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={ref}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <h3>{title}</h3>
        {children}
      </div>
    </div>
  );
}

export interface ConfirmSpec {
  title: string;
  body: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => Promise<void> | void;
}

export function ConfirmModal({ spec, onClose }: { spec: ConfirmSpec; onClose: () => void }) {
  const busy = useRef(false);
  const run = async () => {
    if (busy.current) return;
    busy.current = true;
    try {
      await spec.onConfirm();
      onClose();
    } catch (err) {
      pushToast("bad", "Action failed", String(err instanceof Error ? err.message : err));
      onClose();
    }
  };
  return (
    <Modal title={spec.title} onClose={onClose}>
      {spec.danger ? (
        <div className="danger-zone">
          <p>{spec.body}</p>
        </div>
      ) : (
        <p>{spec.body}</p>
      )}
      <div className="row">
        <button className="btn" onClick={onClose} type="button">
          Cancel
        </button>
        <button className={`btn ${spec.danger ? "danger" : "primary"}`} onClick={run} type="button">
          {spec.confirmLabel}
        </button>
      </div>
    </Modal>
  );
}

export function Toolbar({ children }: { children: ReactNode }) {
  return <div className="toolbar">{children}</div>;
}
