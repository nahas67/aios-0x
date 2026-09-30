import { useState } from "react";
import { approvalsApi } from "../../api/endpoints";
import { DataTable, ErrorBox, Field, Panel, Pill } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtPct, fmtPrice } from "../../lib/format";
import { ACTIONS } from "../../lib/control";
import { ApproveModal } from "../deck/ApproveModal";

export function ApprovalsPage() {
  const approvals = useApi(() => approvalsApi.approvals());
  const [decision, setDecision] = useState<{ planId: string; reject: boolean } | null>(null);
  const rows = approvals.data?.approvals ?? null;

  return (
    <>
      <div className="pagehead">
        <h1>Approvals</h1>
        <span className="sub">SUPERVISED-mode plan queue — approving routes the plan to real execution</span>
      </div>
      {approvals.error ? (
        <ErrorBox title="Approvals unavailable" detail={approvals.error} />
      ) : (
        <Panel title={`Pending Plans${rows ? ` (${rows.length})` : ""}`}>
          <DataTable
            rows={rows}
            rowKey={(r) => r.plan_id}
            empty="No pending plans. In SUPERVISED mode, approved strategies queue here for your decision."
            columns={[
              { key: "plan_id", label: "Plan", render: (r) => <span className="mono faint">{r.plan_id.slice(0, 16)}…</span> },
              { key: "symbol", label: "Symbol", render: (r) => <span className="sym">{r.symbol ?? "—"}</span> },
              { key: "action", label: "Side", render: (r) => <Pill tone={r.action === "BUY" ? "ok" : "bad"}>{r.action ?? "—"}</Pill> },
              { key: "entry_price", label: "Entry", numeric: true, render: (r) => fmtPrice(r.entry_price) },
              { key: "position_size_pct", label: "Size", numeric: true, render: (r) => fmtPct(r.position_size_pct) },
              { key: "status", label: "Status", render: () => <Pill tone="warn">PENDING_APPROVAL</Pill> },
              {
                key: "actions",
                label: "Decision",
                render: (r) => (
                  <span style={{ display: "flex", gap: 6 }}>
                    <button className="btn sm ok" type="button" onClick={() => setDecision({ planId: r.plan_id, reject: false })}>
                      Approve
                    </button>
                    <button className="btn sm danger" type="button" onClick={() => setDecision({ planId: r.plan_id, reject: true })}>
                      Reject
                    </button>
                  </span>
                ),
              },
            ]}
          />
        </Panel>
      )}
      {decision && (
        <PlanDecisionModal
          planId={decision.planId}
          reject={decision.reject}
          onClose={() => setDecision(null)}
          onDone={() => void approvals.refresh()}
        />
      )}
    </>
  );
}

function PlanDecisionModal({
  planId,
  reject,
  onClose,
  onDone,
}: {
  planId: string;
  reject: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const [note, setNote] = useState("");
  const meta = ACTIONS[reject ? "reject_plan" : "approve_plan"];
  return (
    <ApproveModal
      action={reject ? "reject_plan" : "approve_plan"}
      meta={meta}
      extraParams={reject ? { plan_id: planId, note } : { plan_id: planId }}
      onClose={onClose}
      onDone={onDone}
      renderBody={(m) => (
        <>
          <p>{m?.describe}</p>
          <p className="mono faint" style={{ fontSize: 11 }}>plan: {planId}</p>
          {reject && (
            <Field label="Rejection note (audited)">
              <input type="text" value={note} onChange={(e) => setNote(e.target.value)} placeholder="why this plan is rejected" autoFocus />
            </Field>
          )}
        </>
      )}
    />
  );
}
