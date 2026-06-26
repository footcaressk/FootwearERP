import { useEffect, useMemo, useState } from "react";
import { http, inr, API } from "../lib/api";
import { PageHeader, Card, BtnPrimary, BtnSecondary } from "../components/ui-kit";
import { useAuth } from "../lib/auth";
import { FileDown, Check } from "lucide-react";

const STAGES = [
  { key: "procurement", label: "Procurement", color: "#64748B" },
  { key: "cutting", label: "Cutting", color: "#2563EB" },
  { key: "folding", label: "Folding", color: "#0284C7" },
  { key: "attachment", label: "Attachment", color: "#7C3AED" },
  { key: "stitching", label: "Stitching", color: "#C27842" },
  { key: "lasting", label: "Lasting", color: "#A65D24" },
  { key: "sole_pasting", label: "Sole Pasting", color: "#F59E0B" },
  { key: "finishing", label: "Finish / QC / Pack", color: "#16A34A" },
  { key: "dispatched", label: "Dispatched", color: "#F97316" },
];

const COMPONENT_LAYERS = {
  upper: ["Upper Top", "Mid Layer / Reinforcement", "Lining"],
  bottom: ["Bottom Layer", "Insole Board + Cushion", "Insole Cover (PU/Leather)"],
  sole: ["Sole"],
};

const sortSizes = (a, b) => {
  const na = parseFloat(a), nb = parseFloat(b);
  if (!isNaN(na) && !isNaN(nb)) return na - nb;
  return String(a).localeCompare(String(b));
};

/** Group jobs by (po_number, style_code, color) — one card per color. */
function groupJobsByColor(jobs) {
  const groups = {};
  for (const j of jobs) {
    const color = j.color || "—";
    const key = `${j.po_number}::${j.style_code}::${color}`;
    if (!groups[key]) {
      groups[key] = {
        key,
        po_number: j.po_number,
        po_id: j.po_id,
        style_code: j.style_code,
        client_name: j.client_name,
        description: j.description,
        delivery_date: j.delivery_date,
        color,
        rows: [],
        sizes: new Set(),
      };
    }
    groups[key].rows.push(j);
    groups[key].sizes.add(String(j.size || "—"));
  }
  return Object.values(groups).map(g => ({
    ...g,
    sizes: Array.from(g.sizes).sort(sortSizes),
    totalQty: g.rows.reduce((s, r) => s + (r.quantity || 0), 0),
    components: aggregateComponents(g.rows),
  }));
}

function aggregateComponents(rows) {
  // a component is considered done if it's done on ALL rows in the group
  const all = (key) => rows.every(r => r.components?.[key]);
  return {
    upper_done: all("upper_done"),
    bottom_done: all("bottom_done"),
    sole_done: all("sole_done"),
  };
}

export default function Production() {
  const [jobs, setJobs] = useState([]);
  const [selected, setSelected] = useState({}); // keyed by group.key
  const [merging, setMerging] = useState(false);
  const { user } = useAuth();
  const canEdit = ["admin", "manager", "production"].includes(user?.role);

  const load = async () => {
    const { data } = await http.get("/production/jobs");
    setJobs(data);
  };
  useEffect(() => { load(); }, []);

  const moveGroup = async (group, nextStage) => {
    await Promise.all(group.rows.map(j =>
      http.patch(`/production/jobs/${j.id}`, { stage: nextStage })
    ));
    load();
  };

  const toggleComponent = async (group, componentKey, value) => {
    await Promise.all(group.rows.map(j =>
      http.patch(`/production/jobs/${j.id}/components`, { [componentKey]: value })
    ));
    load();
  };

  const toggleSelect = (group) => {
    setSelected((s) => {
      const next = { ...s };
      if (next[group.key]) delete next[group.key]; else next[group.key] = group;
      return next;
    });
  };

  const downloadGroupInvoice = async (group) => {
    try {
      const job_ids = group.rows.map(r => r.id);
      const res = await http.post("/invoices/job", { po_id: group.po_id, job_ids }, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      window.open(url, "_blank");
    } catch (e) {
      alert("Invoice failed: " + (e.response?.data?.detail || e.message));
    }
  };

  const downloadMergedInvoice = async () => {
    const groups = Object.values(selected);
    if (!groups.length) return;
    // ensure same client
    const clients = new Set(groups.map(g => g.client_name));
    if (clients.size > 1) {
      if (!window.confirm("Selected items belong to different clients. Continue with merged invoice using the first client's billing details?")) return;
    }
    // group by po_id
    const byPo = {};
    for (const g of groups) {
      if (!byPo[g.po_id]) byPo[g.po_id] = { po_id: g.po_id, job_ids: [] };
      byPo[g.po_id].job_ids.push(...g.rows.map(r => r.id));
    }
    try {
      setMerging(true);
      const res = await http.post("/invoices/merged", { entries: Object.values(byPo) }, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      window.open(url, "_blank");
      setSelected({});
    } catch (e) {
      alert("Merged invoice failed: " + (e.response?.data?.detail || e.message));
    } finally {
      setMerging(false);
    }
  };

  const dispatchedSelectedCount = Object.keys(selected).length;

  return (
    <div>
      <PageHeader
        title="Production Floor"
        subtitle="Manufacturing / Kanban"
        testId="production-header"
        action={dispatchedSelectedCount > 0 ? (
          <BtnPrimary onClick={downloadMergedInvoice} disabled={merging} data-testid="merged-invoice-btn">
            <FileDown className="w-3.5 h-3.5 inline -mt-0.5 mr-1" />
            {merging ? "Generating..." : `Merge Invoice (${dispatchedSelectedCount})`}
          </BtnPrimary>
        ) : null}
      />

      <div className="p-8">
        <div className="overflow-x-auto pb-4">
          <div className="flex gap-4 min-w-max">
            {STAGES.map((s) => {
              const stageJobs = jobs.filter((j) => j.stage === s.key);
              const groups = groupJobsByColor(stageJobs);
              const totalQty = stageJobs.reduce((sum, j) => sum + j.quantity, 0);
              return (
                <div key={s.key} className="w-[380px] flex-shrink-0" data-testid={`column-${s.key}`}>
                  <div className="bg-white border-2 border-slate-200 border-t-4 mb-3 p-3" style={{ borderTopColor: s.color }}>
                    <div className="flex items-baseline justify-between">
                      <div className="font-bold uppercase tracking-wider text-sm">{s.label}</div>
                      <div className="font-mono text-xs text-slate-500">
                        {groups.length} · <span className="font-bold text-slate-900">{totalQty}</span>
                      </div>
                    </div>
                  </div>
                  <div className="space-y-3">
                    {groups.length === 0 && (
                      <div className="border-2 border-dashed border-slate-200 p-6 text-center text-xs text-slate-400">Empty</div>
                    )}
                    {groups.map((g) => (
                      <ColorGroupCard
                        key={g.key}
                        group={g}
                        stageColor={s.color}
                        stageIdx={STAGES.findIndex(x => x.key === s.key)}
                        canEdit={canEdit}
                        onMove={moveGroup}
                        onToggleComponent={toggleComponent}
                        isDispatched={s.key === "dispatched"}
                        onDownloadInvoice={downloadGroupInvoice}
                        isSelected={!!selected[g.key]}
                        onToggleSelect={toggleSelect}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        {jobs.length === 0 && (
          <Card className="p-12 text-center text-slate-400 mt-4">
            No production jobs yet. Create a Purchase Order — jobs are auto-generated per line item.
          </Card>
        )}
      </div>
    </div>
  );
}

function ColorGroupCard({ group, stageColor, stageIdx, canEdit, onMove, onToggleComponent, isDispatched, onDownloadInvoice, isSelected, onToggleSelect }) {
  const nextStage = STAGES[stageIdx + 1];
  const prevStage = STAGES[stageIdx - 1];

  // size totals
  const sizeTotals = useMemo(() => {
    const t = {};
    for (const sz of group.sizes) {
      const row = group.rows.find(r => String(r.size || "—") === sz);
      t[sz] = row?.quantity || 0;
    }
    return t;
  }, [group]);

  return (
    <Card className="border-l-4 hover:border-[#C27842] transition-colors" style={{ borderLeftColor: stageColor }} data-testid={`group-${group.key}`}>
      <div className="p-3 pb-2 border-b border-slate-100">
        <div className="flex items-baseline justify-between mb-0.5">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">{group.po_number}</div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500">{group.client_name}</div>
        </div>
        <div className="flex items-center justify-between">
          <div>
            <div className="font-mono font-bold text-sm">{group.style_code}</div>
            <div className="text-xs">
              <span className="font-bold text-[#C27842]">{group.color}</span>
              <span className="text-slate-400 mx-1">·</span>
              <span className="text-slate-600 font-mono">{group.totalQty} pairs</span>
            </div>
          </div>
          {isDispatched && (
            <label className="inline-flex items-center gap-1.5 cursor-pointer" title="Select for merged invoice">
              <input type="checkbox" checked={isSelected} onChange={() => onToggleSelect(group)} className="w-4 h-4 accent-[#C27842]" data-testid={`select-${group.key}`} />
              <span className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Merge</span>
            </label>
          )}
        </div>
      </div>

      {/* Size matrix */}
      <div className="p-3 overflow-x-auto">
        <table className="w-full text-xs border border-slate-200">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-2 py-1 text-left text-[10px] uppercase tracking-wider font-bold text-slate-600 border-r border-slate-200">Size</th>
              {group.sizes.map(sz => (
                <th key={sz} className="px-2 py-1 text-center font-mono text-[11px] font-bold text-slate-700 border-r border-slate-200 last:border-r-0">{sz}</th>
              ))}
              <th className="px-2 py-1 text-right text-[10px] uppercase tracking-wider font-bold text-slate-900 bg-slate-100">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-t border-slate-200">
              <td className="px-2 py-1.5 font-bold text-slate-700 border-r border-slate-200" data-testid={`color-row-${group.color}`}>{group.color}</td>
              {group.sizes.map(sz => (
                <td key={sz} className="px-2 py-1.5 text-center font-mono border-r border-slate-200 last:border-r-0">{sizeTotals[sz]}</td>
              ))}
              <td className="px-2 py-1.5 text-right font-mono font-bold bg-[#0F172A] text-[#C27842]">{group.totalQty}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Component tracker */}
      <div className="px-3 pb-2">
        <div className="text-[10px] uppercase tracking-[0.15em] font-bold text-slate-500 mb-1.5">Components</div>
        <div className="grid grid-cols-3 gap-2">
          <ComponentCell label="Upper" done={group.components.upper_done} layers={COMPONENT_LAYERS.upper}
            disabled={!canEdit} onToggle={(v) => onToggleComponent(group, "upper_done", v)} testId={`comp-upper-${group.key}`} />
          <ComponentCell label="Bottom/Insole" done={group.components.bottom_done} layers={COMPONENT_LAYERS.bottom}
            disabled={!canEdit} onToggle={(v) => onToggleComponent(group, "bottom_done", v)} testId={`comp-bottom-${group.key}`} />
          <ComponentCell label="Sole" done={group.components.sole_done} layers={COMPONENT_LAYERS.sole}
            disabled={!canEdit} onToggle={(v) => onToggleComponent(group, "sole_done", v)} testId={`comp-sole-${group.key}`} />
        </div>
      </div>

      <div className="px-3 pb-3 flex items-center justify-between gap-2 flex-wrap">
        {group.delivery_date && <div className="text-[10px] text-slate-500">Deliver: {group.delivery_date}</div>}
        <div className="flex gap-2 ml-auto items-center">
          {isDispatched && (
            <button onClick={() => onDownloadInvoice(group)} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#C27842] hover:bg-[#A65D24] px-3 py-1 flex items-center gap-1" data-testid={`invoice-btn-${group.key}`}>
              <FileDown className="w-3 h-3" /> Invoice
            </button>
          )}
          {canEdit && prevStage && (
            <button onClick={() => onMove(group, prevStage.key)} className="text-[10px] uppercase tracking-wider font-bold text-slate-500 hover:text-slate-900 border border-slate-300 px-2 py-1" data-testid={`move-prev-${group.key}`}>← {prevStage.label}</button>
          )}
          {canEdit && nextStage && (
            <button onClick={() => onMove(group, nextStage.key)} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#0F172A] hover:bg-[#C27842] px-3 py-1" data-testid={`move-next-${group.key}`}>{nextStage.label} →</button>
          )}
        </div>
      </div>
    </Card>
  );
}

function ComponentCell({ label, done, layers, onToggle, disabled, testId }) {
  return (
    <div className={`border-2 p-2 ${done ? "border-[#16A34A] bg-green-50" : "border-slate-200 bg-white"}`}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onToggle(!done)}
        data-testid={testId}
        className="w-full flex items-center justify-between gap-1 text-left"
      >
        <span className="text-[10px] uppercase tracking-wider font-bold text-slate-700">{label}</span>
        <span className={`w-4 h-4 grid place-items-center border-2 ${done ? "bg-[#16A34A] border-[#16A34A]" : "border-slate-400 bg-white"}`}>
          {done && <Check className="w-3 h-3 text-white" strokeWidth={3} />}
        </span>
      </button>
      <div className="mt-1 space-y-0.5">
        {layers.map(l => (
          <div key={l} className="text-[9px] text-slate-500 leading-tight">• {l}</div>
        ))}
      </div>
    </div>
  );
}
