import { useEffect, useState } from "react";
import { http } from "../lib/api";
import { PageHeader, Card, BtnSecondary, Badge } from "../components/ui-kit";
import { useAuth } from "../lib/auth";

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

export default function Production() {
  const [jobs, setJobs] = useState([]);
  const { user } = useAuth();
  const canEdit = ["admin", "manager", "production"].includes(user?.role);

  const load = async () => {
    const { data } = await http.get("/production/jobs");
    setJobs(data);
  };
  useEffect(() => { load(); }, []);

  const move = async (job, nextStage) => {
    await http.patch(`/production/jobs/${job.id}`, { stage: nextStage });
    load();
  };

  return (
    <div>
      <PageHeader title="Production Floor" subtitle="Manufacturing / Kanban" testId="production-header" />

      <div className="p-8">
        <div className="overflow-x-auto pb-4">
          <div className="flex gap-4 min-w-max">
            {STAGES.map((s) => {
              const stageJobs = jobs.filter((j) => j.stage === s.key);
              const totalQty = stageJobs.reduce((sum, j) => sum + j.quantity, 0);
              return (
                <div key={s.key} className="w-72 flex-shrink-0" data-testid={`column-${s.key}`}>
                  <div className="bg-white border-2 border-slate-200 border-t-4 mb-3 p-3" style={{ borderTopColor: s.color }}>
                    <div className="flex items-baseline justify-between">
                      <div className="font-bold uppercase tracking-wider text-sm">{s.label}</div>
                      <div className="font-mono text-xs text-slate-500">{stageJobs.length} jobs · <span className="font-bold text-slate-900">{totalQty}</span> pairs</div>
                    </div>
                  </div>
                  <div className="space-y-3">
                    {stageJobs.length === 0 && (
                      <div className="border-2 border-dashed border-slate-200 p-6 text-center text-xs text-slate-400">Empty</div>
                    )}
                    {stageJobs.map((j) => {
                      const idx = STAGES.findIndex((x) => x.key === j.stage);
                      const nextStage = STAGES[idx + 1];
                      const prevStage = STAGES[idx - 1];
                      return (
                        <Card key={j.id} className="p-4 border-l-4 hover:border-[#C27842] transition-colors cursor-default" style={{ borderLeftColor: s.color }} data-testid={`kanban-card-${j.id}`}>
                          <div className="flex items-baseline justify-between mb-1">
                            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">{j.po_number}</div>
                            <Badge color="slate">{j.size ? `Sz ${j.size}` : "—"}</Badge>
                          </div>
                          <div className="font-mono font-bold text-sm">{j.style_code}</div>
                          <div className="text-xs text-slate-600 line-clamp-1">{j.description || j.client_name}</div>
                          {j.color && <div className="text-xs text-slate-500 mt-0.5">Color: {j.color}</div>}
                          <div className="flex items-baseline justify-between mt-3 pt-2 border-t border-dashed border-slate-200">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Qty</span>
                            <span className="font-mono font-bold text-lg">{j.quantity}</span>
                          </div>
                          {j.delivery_date && <div className="text-[10px] text-slate-500 mt-1">Deliver: {j.delivery_date}</div>}
                          {canEdit && (
                            <div className="flex gap-2 mt-3">
                              {prevStage && (
                                <button onClick={() => move(j, prevStage.key)} className="text-[10px] uppercase tracking-wider font-bold text-slate-500 hover:text-slate-900 border border-slate-300 px-2 py-1 flex-1" data-testid={`move-prev-${j.id}`}>← {prevStage.label}</button>
                              )}
                              {nextStage && (
                                <button onClick={() => move(j, nextStage.key)} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#0F172A] hover:bg-[#C27842] px-2 py-1 flex-1" data-testid={`move-next-${j.id}`}>{nextStage.label} →</button>
                              )}
                            </div>
                          )}
                        </Card>
                      );
                    })}
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
