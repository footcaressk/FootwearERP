import { useEffect, useMemo, useState } from "react";
import { http } from "../lib/api";
import { PageHeader, Card, BtnPrimary, BtnSecondary } from "../components/ui-kit";
import { useAuth } from "../lib/auth";
import { FileDown, Check, UserPlus, Edit3, ClipboardList, X, HardHat, GripVertical } from "lucide-react";

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

const ASSIGNMENT_ROLES = [
  { key: "cutting", label: "Cutting" },
  { key: "upper", label: "Upper" },
  { key: "bottom", label: "Bottom/Insole" },
  { key: "stitching", label: "Stitching" },
  { key: "lasting", label: "Lasting" },
  { key: "sole_pasting", label: "Sole Pasting" },
  { key: "finishing", label: "Finishing" },
];

// Stage → most likely role mapping for bulk-drag assignment
const STAGE_TO_ROLE = {
  cutting: "cutting",
  folding: "upper",
  attachment: "upper",
  stitching: "stitching",
  lasting: "lasting",
  sole_pasting: "sole_pasting",
  finishing: "finishing",
};

const sortSizes = (a, b) => {
  const na = parseFloat(a), nb = parseFloat(b);
  if (!isNaN(na) && !isNaN(nb)) return na - nb;
  return String(a).localeCompare(String(b));
};

function groupJobsByColor(jobs) {
  const groups = {};
  for (const j of jobs) {
    const color = j.color || "—";
    const key = `${j.po_number}::${j.style_code}::${color}`;
    if (!groups[key]) {
      groups[key] = {
        key, po_number: j.po_number, po_id: j.po_id, style_code: j.style_code,
        client_name: j.client_name, description: j.description, delivery_date: j.delivery_date,
        color, rows: [], sizes: new Set(),
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
    assignments: aggregateAssignments(g.rows),
  }));
}

function aggregateComponents(rows) {
  const all = (key) => rows.every(r => r.components?.[key]);
  return { upper_done: all("upper_done"), bottom_done: all("bottom_done"), sole_done: all("sole_done") };
}

// take assignment from the first row for display (all rows in the group share)
function aggregateAssignments(rows) {
  const r0 = rows[0] || {};
  return r0.assignments || {};
}

export default function Production() {
  const [jobs, setJobs] = useState([]);
  const [workers, setWorkers] = useState([]);
  const [selected, setSelected] = useState({});
  const [procSelected, setProcSelected] = useState({});
  const [merging, setMerging] = useState(false);
  const [assignFor, setAssignFor] = useState(null);
  const [qtyFor, setQtyFor] = useState(null);
  const [dockOpen, setDockOpen] = useState(false);
  const [draggingWorker, setDraggingWorker] = useState(null);
  const [dropZone, setDropZone] = useState(null);
  const [bulkConfirm, setBulkConfirm] = useState(null);
  const { user } = useAuth();
  const canEdit = ["admin", "manager", "production"].includes(user?.role);

  const load = async () => {
    const [j, w] = await Promise.all([http.get("/production/jobs"), http.get("/workers")]);
    setJobs(j.data); setWorkers(w.data);
  };
  useEffect(() => { load(); }, []);

  const moveGroup = async (group, nextStage) => {
    await Promise.all(group.rows.map(j => http.patch(`/production/jobs/${j.id}`, { stage: nextStage })));
    load();
  };
  const toggleComponent = async (group, key, val) => {
    await Promise.all(group.rows.map(j => http.patch(`/production/jobs/${j.id}/components`, { [key]: val })));
    load();
  };
  const assignWorker = async (group, role, workerId) => {
    await Promise.all(group.rows.map(j =>
      http.patch(`/production/jobs/${j.id}/assignment`, { role, worker_id: workerId || null })
    ));
    setAssignFor(null);
    load();
  };
  const saveQuantity = async (rowId, body) => {
    await http.patch(`/production/jobs/${rowId}/quantity`, body);
    setQtyFor(null);
    load();
  };

  // Dispatched merge invoice
  const toggleSelect = (group) => setSelected(s => {
    const next = { ...s }; if (next[group.key]) delete next[group.key]; else next[group.key] = group; return next;
  });
  const downloadGroupInvoice = async (group) => {
    try {
      const res = await http.post("/invoices/job", { po_id: group.po_id, job_ids: group.rows.map(r => r.id) }, { responseType: "blob" });
      window.open(URL.createObjectURL(new Blob([res.data], { type: "application/pdf" })), "_blank");
    } catch (e) { alert("Invoice failed: " + (e.response?.data?.detail || e.message)); }
  };
  const downloadMergedInvoice = async () => {
    const groups = Object.values(selected); if (!groups.length) return;
    const byPo = {};
    for (const g of groups) {
      if (!byPo[g.po_id]) byPo[g.po_id] = { po_id: g.po_id, job_ids: [] };
      byPo[g.po_id].job_ids.push(...g.rows.map(r => r.id));
    }
    try {
      setMerging(true);
      const res = await http.post("/invoices/merged", { entries: Object.values(byPo) }, { responseType: "blob" });
      window.open(URL.createObjectURL(new Blob([res.data], { type: "application/pdf" })), "_blank");
      setSelected({});
    } catch (e) { alert("Merged failed: " + (e.response?.data?.detail || e.message)); }
    finally { setMerging(false); }
  };

  // Procurement: select cards & generate material requirement
  const toggleProcSelect = (group) => setProcSelected(s => {
    const next = { ...s }; if (next[group.key]) delete next[group.key]; else next[group.key] = group; return next;
  });
  const downloadMaterialRequirement = async (groups, label) => {
    const job_ids = [];
    groups.forEach(g => g.rows.forEach(r => job_ids.push(r.id)));
    try {
      const res = await http.post("/procurement/requirement.pdf",
        { job_ids, scope_label: label || `${groups.length} card(s)` }, { responseType: "blob" });
      window.open(URL.createObjectURL(new Blob([res.data], { type: "application/pdf" })), "_blank");
    } catch (e) { alert("Material requirement failed: " + (e.response?.data?.detail || e.message)); }
  };

  // ---- Drag & Drop bulk assignment ----
  const onDragStartWorker = (w) => (e) => {
    setDraggingWorker(w);
    try { e.dataTransfer.setData("text/plain", w.id); } catch {}
    e.dataTransfer.effectAllowed = "copy";
  };
  const onDragEndWorker = () => { setDraggingWorker(null); setDropZone(null); };
  const onDragOverStage = (stageKey) => (e) => {
    if (!draggingWorker) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    setDropZone(stageKey);
  };
  const onDropStage = (stageKey, stageJobs) => (e) => {
    e.preventDefault();
    const role = STAGE_TO_ROLE[stageKey];
    if (!role || !draggingWorker || !stageJobs.length) { setDropZone(null); return; }
    setBulkConfirm({
      worker: draggingWorker, role, stageKey,
      job_ids: stageJobs.map(j => j.id),
      stage_label: STAGES.find(s => s.key === stageKey)?.label || stageKey,
      card_count: groupJobsByColor(stageJobs).length,
    });
    setDropZone(null);
  };
  const runBulkAssign = async () => {
    if (!bulkConfirm) return;
    try {
      await http.post("/production/bulk-assign", {
        job_ids: bulkConfirm.job_ids,
        role: bulkConfirm.role,
        worker_id: bulkConfirm.worker.id,
      });
      setBulkConfirm(null);
      load();
    } catch (e) { alert("Bulk assignment failed: " + (e.response?.data?.detail || e.message)); }
  };

  const dispatchedCount = Object.keys(selected).length;
  const procSelectedCount = Object.keys(procSelected).length;

  return (
    <div>
      <PageHeader
        title="Production Floor"
        subtitle="Manufacturing / Kanban"
        testId="production-header"
        action={
          <div className="flex gap-2 items-center">
            {canEdit && (
              <button onClick={() => setDockOpen(d => !d)} data-testid="toggle-karigar-dock"
                className={`text-xs font-bold uppercase tracking-wider px-3 py-2 border-2 ${dockOpen ? "bg-[#C27842] text-white border-[#C27842]" : "bg-white text-slate-900 border-slate-300 hover:border-[#0F172A]"}`}>
                <HardHat className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Karigars
              </button>
            )}
            {procSelectedCount > 0 && (
              <BtnPrimary onClick={() => { downloadMaterialRequirement(Object.values(procSelected), `${procSelectedCount} procurement cards`); setProcSelected({}); }} data-testid="merged-mr-btn">
                <ClipboardList className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Material Requirement ({procSelectedCount})
              </BtnPrimary>
            )}
            {dispatchedCount > 0 && (
              <BtnPrimary onClick={downloadMergedInvoice} disabled={merging} data-testid="merged-invoice-btn">
                <FileDown className="w-3.5 h-3.5 inline -mt-0.5 mr-1" />
                {merging ? "..." : `Merge Invoice (${dispatchedCount})`}
              </BtnPrimary>
            )}
          </div>
        }
      />

      <div className="p-8">
        <div className="overflow-x-auto pb-4">
          <div className="flex gap-4 min-w-max">
            {STAGES.map((s) => {
              const stageJobs = jobs.filter((j) => j.stage === s.key);
              const groups = groupJobsByColor(stageJobs);
              const totalQty = stageJobs.reduce((sum, j) => sum + j.quantity, 0);
              const isProc = s.key === "procurement";
              const isDisp = s.key === "dispatched";
              return (
                <div key={s.key} className="w-[400px] flex-shrink-0" data-testid={`column-${s.key}`}>
                  <div
                    className={`bg-white border-2 mb-3 p-3 transition-all ${dropZone === s.key ? "border-[#C27842] bg-orange-50 shadow-ind" : "border-slate-200"} border-t-4`}
                    style={{ borderTopColor: s.color }}
                    onDragOver={STAGE_TO_ROLE[s.key] ? onDragOverStage(s.key) : undefined}
                    onDragLeave={() => setDropZone(null)}
                    onDrop={STAGE_TO_ROLE[s.key] ? onDropStage(s.key, stageJobs) : undefined}
                    data-testid={`column-header-${s.key}`}
                  >
                    <div className="flex items-baseline justify-between">
                      <div className="font-bold uppercase tracking-wider text-sm">{s.label}</div>
                      <div className="font-mono text-xs text-slate-500">
                        {groups.length} · <span className="font-bold text-slate-900">{totalQty}</span>
                      </div>
                    </div>
                    {STAGE_TO_ROLE[s.key] && draggingWorker && (
                      <div className="mt-1 text-[10px] uppercase tracking-wider font-bold text-[#C27842]">
                        Drop here → assign to {STAGE_TO_ROLE[s.key]} role on {groups.length} card(s)
                      </div>
                    )}
                  </div>
                  <div className="space-y-3">
                    {groups.length === 0 && (
                      <div className="border-2 border-dashed border-slate-200 p-6 text-center text-xs text-slate-400">Empty</div>
                    )}
                    {groups.map((g) => (
                      <ColorGroupCard
                        key={g.key}
                        group={g}
                        workers={workers}
                        stageColor={s.color}
                        stageIdx={STAGES.findIndex(x => x.key === s.key)}
                        canEdit={canEdit}
                        onMove={moveGroup}
                        onToggleComponent={toggleComponent}
                        onOpenAssign={(role) => setAssignFor({ group: g, role })}
                        onOpenQty={(rowId) => setQtyFor({ group: g, rowId })}
                        isProc={isProc}
                        isDispatched={isDisp}
                        onMatReq={() => downloadMaterialRequirement([g], `${g.style_code} · ${g.color}`)}
                        procSelected={!!procSelected[g.key]}
                        onToggleProcSelect={toggleProcSelect}
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
          <Card className="p-12 text-center text-slate-400 mt-4">No production jobs yet.</Card>
        )}
      </div>

      {assignFor && (
        <AssignDialog
          group={assignFor.group}
          role={assignFor.role}
          workers={workers}
          current={assignFor.group.assignments?.[assignFor.role]}
          onSave={(wid) => assignWorker(assignFor.group, assignFor.role, wid)}
          onClose={() => setAssignFor(null)}
        />
      )}

      {qtyFor && (
        <QuantityDialog
          group={qtyFor.group}
          row={qtyFor.group.rows.find(r => r.id === qtyFor.rowId)}
          onSave={(body) => saveQuantity(qtyFor.rowId, body)}
          onClose={() => setQtyFor(null)}
        />
      )}

      {dockOpen && (
        <div className="fixed left-64 right-0 bottom-0 bg-white border-t-2 border-slate-200 shadow-2xl z-40 p-3" data-testid="karigar-dock">
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs uppercase tracking-[0.2em] font-bold text-slate-600">
              Drag a karigar onto any stage column to assign them across all cards in that column
            </div>
            <button onClick={() => setDockOpen(false)} className="p-1 hover:bg-slate-100"><X className="w-4 h-4" /></button>
          </div>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {workers.length === 0 && <div className="text-xs text-slate-400 py-3">No karigars. Add some in the Karigars tab first.</div>}
            {workers.filter(w => w.active !== false).map(w => (
              <div
                key={w.id}
                draggable
                onDragStart={onDragStartWorker(w)}
                onDragEnd={onDragEndWorker}
                data-testid={`drag-worker-${w.id}`}
                className={`flex items-center gap-2 px-3 py-2 border-2 cursor-grab active:cursor-grabbing select-none ${draggingWorker?.id === w.id ? "border-[#C27842] bg-orange-50" : "border-slate-300 bg-white hover:border-[#0F172A]"}`}
              >
                <GripVertical className="w-3.5 h-3.5 text-slate-400" />
                <div>
                  <div className="font-bold text-sm leading-tight">{w.name}</div>
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">{w.skill} · ₹{w.rate_per_pair}/pr</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {bulkConfirm && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" data-testid="bulk-assign-dialog">
          <div className="bg-white border-2 border-slate-200 shadow-2xl w-full max-w-md">
            <div className="px-5 py-4 border-b-2 border-slate-200">
              <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-bold">Bulk Assignment</div>
              <div className="font-bold text-base">{bulkConfirm.worker.name} → {bulkConfirm.role.toUpperCase()}</div>
            </div>
            <div className="p-5 space-y-3">
              <p className="text-sm text-slate-700">
                Assign <b>{bulkConfirm.worker.name}</b> ({bulkConfirm.worker.skill}, ₹{bulkConfirm.worker.rate_per_pair}/pair) as the <b>{bulkConfirm.role}</b> karigar on <b>{bulkConfirm.card_count}</b> card(s) currently in <b>{bulkConfirm.stage_label}</b> stage?
              </p>
              <p className="text-xs text-slate-500">This will overwrite any existing {bulkConfirm.role} assignment on these cards. The full history is preserved.</p>
              <div className="flex gap-2 pt-2 border-t border-slate-200">
                <BtnPrimary onClick={runBulkAssign} data-testid="bulk-confirm-save"><Check className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Assign to all</BtnPrimary>
                <BtnSecondary onClick={() => setBulkConfirm(null)}>Cancel</BtnSecondary>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ColorGroupCard(props) {
  const { group, stageColor, stageIdx, canEdit, onMove, onToggleComponent,
    onOpenAssign, onOpenQty, isProc, isDispatched, onMatReq,
    procSelected, onToggleProcSelect, isSelected, onToggleSelect, onDownloadInvoice } = props;
  const nextStage = STAGES[stageIdx + 1];
  const prevStage = STAGES[stageIdx - 1];

  const sizeTotals = useMemo(() => {
    const t = {}; const rowIdBySize = {};
    for (const sz of group.sizes) {
      const row = group.rows.find(r => String(r.size || "—") === sz);
      t[sz] = row?.quantity || 0;
      rowIdBySize[sz] = row?.id;
    }
    return { t, rowIdBySize };
  }, [group]);

  const completedTotal = group.rows.reduce((s, r) => s + (r.completed_qty || 0), 0);
  const a = group.assignments || {};

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
              {completedTotal > 0 && (
                <>
                  <span className="text-slate-400 mx-1">·</span>
                  <span className="text-green-700 font-mono">{completedTotal} done</span>
                </>
              )}
            </div>
          </div>
          {isDispatched && (
            <label className="inline-flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" checked={isSelected} onChange={() => onToggleSelect(group)} className="w-4 h-4 accent-[#C27842]" data-testid={`select-${group.key}`} />
              <span className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Merge</span>
            </label>
          )}
          {isProc && (
            <label className="inline-flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" checked={procSelected} onChange={() => onToggleProcSelect(group)} className="w-4 h-4 accent-[#2563EB]" data-testid={`proc-select-${group.key}`} />
              <span className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Combine</span>
            </label>
          )}
        </div>
      </div>

      {/* Size matrix with click-to-edit qty */}
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
              <td className="px-2 py-1.5 font-bold text-slate-700 border-r border-slate-200">{group.color}</td>
              {group.sizes.map(sz => (
                <td key={sz} className="px-2 py-1.5 text-center font-mono border-r border-slate-200 last:border-r-0">
                  {canEdit ? (
                    <button onClick={() => onOpenQty(sizeTotals.rowIdBySize[sz])} className="hover:text-[#C27842] hover:underline w-full" data-testid={`qty-${group.key}-${sz}`}>
                      {sizeTotals.t[sz]}
                    </button>
                  ) : sizeTotals.t[sz]}
                </td>
              ))}
              <td className="px-2 py-1.5 text-right font-mono font-bold bg-[#0F172A] text-[#C27842]">{group.totalQty}</td>
            </tr>
          </tbody>
        </table>
        {canEdit && (
          <div className="text-[9px] text-slate-400 mt-1 italic">Click any qty cell to edit / adjust completed / rejected</div>
        )}
      </div>

      {/* Components */}
      <div className="px-3 pb-2">
        <div className="text-[10px] uppercase tracking-[0.15em] font-bold text-slate-500 mb-1.5">Components</div>
        <div className="grid grid-cols-3 gap-2">
          <ComponentCell label="Upper" done={group.components.upper_done} layers={COMPONENT_LAYERS.upper}
            disabled={!canEdit} onToggle={(v) => onToggleComponent(group, "upper_done", v)} />
          <ComponentCell label="Bottom/Insole" done={group.components.bottom_done} layers={COMPONENT_LAYERS.bottom}
            disabled={!canEdit} onToggle={(v) => onToggleComponent(group, "bottom_done", v)} />
          <ComponentCell label="Sole" done={group.components.sole_done} layers={COMPONENT_LAYERS.sole}
            disabled={!canEdit} onToggle={(v) => onToggleComponent(group, "sole_done", v)} />
        </div>
      </div>

      {/* Karigar assignments */}
      <div className="px-3 pb-2">
        <div className="text-[10px] uppercase tracking-[0.15em] font-bold text-slate-500 mb-1.5">Karigars</div>
        <div className="grid grid-cols-2 gap-1.5">
          {ASSIGNMENT_ROLES.map(r => (
            <button
              key={r.key}
              disabled={!canEdit}
              onClick={() => onOpenAssign(r.key)}
              data-testid={`assign-${group.key}-${r.key}`}
              className={`flex items-center justify-between gap-1 px-2 py-1 border ${a[r.key] ? "border-[#C27842] bg-orange-50" : "border-dashed border-slate-300 bg-white"} hover:border-slate-900 text-left transition-colors`}
            >
              <span className="text-[9px] uppercase tracking-wider font-bold text-slate-500">{r.label}</span>
              <span className={`text-[10px] font-bold truncate ${a[r.key] ? "text-[#0F172A]" : "text-slate-400 italic"}`}>
                {a[r.key]?.worker_name || "Assign…"}
              </span>
            </button>
          ))}
        </div>
      </div>

      <div className="px-3 pb-3 flex items-center justify-between gap-2 flex-wrap">
        {group.delivery_date && <div className="text-[10px] text-slate-500">Deliver: {group.delivery_date}</div>}
        <div className="flex gap-2 ml-auto items-center flex-wrap">
          {isProc && (
            <button onClick={onMatReq} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#2563EB] hover:bg-[#1E40AF] px-3 py-1 flex items-center gap-1" data-testid={`mat-req-${group.key}`}>
              <ClipboardList className="w-3 h-3" /> Material Req.
            </button>
          )}
          {isDispatched && (
            <button onClick={() => onDownloadInvoice(group)} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#C27842] hover:bg-[#A65D24] px-3 py-1 flex items-center gap-1" data-testid={`invoice-btn-${group.key}`}>
              <FileDown className="w-3 h-3" /> Invoice
            </button>
          )}
          {canEdit && prevStage && (
            <button onClick={() => onMove(group, prevStage.key)} className="text-[10px] uppercase tracking-wider font-bold text-slate-500 hover:text-slate-900 border border-slate-300 px-2 py-1">← {prevStage.label}</button>
          )}
          {canEdit && nextStage && (
            <button onClick={() => onMove(group, nextStage.key)} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#0F172A] hover:bg-[#C27842] px-3 py-1" data-testid={`move-next-${group.key}`}>{nextStage.label} →</button>
          )}
        </div>
      </div>
    </Card>
  );
}

function ComponentCell({ label, done, layers, onToggle, disabled }) {
  return (
    <div className={`border-2 p-2 ${done ? "border-[#16A34A] bg-green-50" : "border-slate-200 bg-white"}`}>
      <button type="button" disabled={disabled} onClick={() => onToggle(!done)}
        className="w-full flex items-center justify-between gap-1 text-left">
        <span className="text-[10px] uppercase tracking-wider font-bold text-slate-700">{label}</span>
        <span className={`w-4 h-4 grid place-items-center border-2 ${done ? "bg-[#16A34A] border-[#16A34A]" : "border-slate-400 bg-white"}`}>
          {done && <Check className="w-3 h-3 text-white" strokeWidth={3} />}
        </span>
      </button>
      <div className="mt-1 space-y-0.5">
        {layers.map(l => <div key={l} className="text-[9px] text-slate-500 leading-tight">• {l}</div>)}
      </div>
    </div>
  );
}

function AssignDialog({ group, role, workers, current, onSave, onClose }) {
  const roleObj = ASSIGNMENT_ROLES.find(r => r.key === role);
  // Prefer workers of matching skill (or 'general')
  const matchingSkill = role; // role keys align with skill keys for most
  const sorted = [...workers].sort((a, b) => {
    const am = (a.skill === matchingSkill || a.skill === "general") ? 0 : 1;
    const bm = (b.skill === matchingSkill || b.skill === "general") ? 0 : 1;
    return am - bm;
  });
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" data-testid="assign-dialog">
      <div className="bg-white border-2 border-slate-200 shadow-2xl w-full max-w-md">
        <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-bold">Assign Karigar</div>
            <div className="font-bold text-base">{group.style_code} · {group.color} · {roleObj?.label}</div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-100"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5 max-h-[60vh] overflow-y-auto">
          {sorted.length === 0 ? (
            <div className="text-center text-sm text-slate-500 py-8">
              No karigars yet. Go to <b>Karigars</b> tab and add some first.
            </div>
          ) : (
            <div className="space-y-1.5">
              <button
                onClick={() => onSave(null)}
                data-testid="assign-clear"
                className="w-full text-left px-3 py-2 border border-slate-200 hover:border-red-500 hover:text-red-700 text-xs font-bold uppercase tracking-wider"
              >
                ✕ Unassign
              </button>
              {sorted.map(w => (
                <button
                  key={w.id}
                  onClick={() => onSave(w.id)}
                  data-testid={`assign-worker-${w.id}`}
                  className={`w-full text-left px-3 py-2 border ${current?.worker_id === w.id ? "border-[#C27842] bg-orange-50" : "border-slate-200"} hover:border-[#0F172A] flex items-center justify-between`}
                >
                  <div>
                    <div className="font-bold text-sm">{w.name}</div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider">{w.skill}{w.phone ? ` · ${w.phone}` : ""}</div>
                  </div>
                  <div className="text-xs font-mono">₹{w.rate_per_pair}/pr</div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function QuantityDialog({ group, row, onSave, onClose }) {
  const [qty, setQty] = useState(row?.quantity || 0);
  const [completed, setCompleted] = useState(row?.completed_qty || 0);
  const [rejected, setRejected] = useState(row?.rejected_qty || 0);
  const [reason, setReason] = useState("");

  const save = () => {
    onSave({
      quantity: Number(qty),
      completed_qty: Number(completed),
      rejected_qty: Number(rejected),
      reason,
    });
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" data-testid="qty-dialog">
      <div className="bg-white border-2 border-slate-200 shadow-2xl w-full max-w-md">
        <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-bold">Edit Quantity</div>
            <div className="font-bold text-base">{group.style_code} · {group.color} · Size {row?.size}</div>
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mt-0.5">Stage: {row?.stage}</div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-100"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5 space-y-3">
          <div>
            <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Planned Qty (pairs)</label>
            <input type="number" value={qty} onChange={(e) => setQty(e.target.value)} data-testid="qty-input-planned"
              className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-lg focus:border-[#2563EB] focus:outline-none" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Completed</label>
              <input type="number" value={completed} onChange={(e) => setCompleted(e.target.value)} data-testid="qty-input-completed"
                className="w-full border-2 border-slate-300 px-3 py-2 font-mono focus:border-[#16A34A] focus:outline-none" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Rejected</label>
              <input type="number" value={rejected} onChange={(e) => setRejected(e.target.value)} data-testid="qty-input-rejected"
                className="w-full border-2 border-slate-300 px-3 py-2 font-mono focus:border-red-500 focus:outline-none" />
            </div>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Reason (optional)</label>
            <input type="text" value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder="e.g., 5 pairs damaged in cutting"
              className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#2563EB] focus:outline-none" />
          </div>
          <div className="flex gap-2 pt-3 border-t border-slate-200">
            <BtnPrimary onClick={save} data-testid="qty-save"><Check className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Save</BtnPrimary>
            <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
          </div>
        </div>
      </div>
    </div>
  );
}
