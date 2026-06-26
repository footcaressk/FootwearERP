import { useEffect, useState } from "react";
import { http, API, inr } from "../lib/api";
import { PageHeader, Card, BtnPrimary, BtnSecondary, Input, Badge } from "../components/ui-kit";
import { Drawer } from "./Materials";
import { Calendar, FileDown, IndianRupee, Plus, Trash2, Check, X, Users as UsersIcon } from "lucide-react";

const ROLE_LABEL = {
  cutting: "Cutting", upper: "Upper", bottom: "Bottom/Insole",
  stitching: "Stitching", lasting: "Lasting", sole_pasting: "Sole Pasting",
  finishing: "Finishing",
};

export default function Payroll() {
  const today = new Date();
  const monthStart = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().slice(0, 10);
  const [fromDate, setFromDate] = useState(monthStart);
  const [toDate, setToDate] = useState(today.toISOString().slice(0, 10));
  const [data, setData] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [workers, setWorkers] = useState([]);
  const [showAdvances, setShowAdvances] = useState(false);
  const [advances, setAdvances] = useState([]);
  const [advForm, setAdvForm] = useState(null);

  const load = async () => {
    const params = new URLSearchParams();
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const [p, w] = await Promise.all([
      http.get(`/reports/payroll?${params.toString()}`),
      http.get("/workers"),
    ]);
    setData(p.data);
    setWorkers(w.data);
  };
  const loadAdvances = async () => {
    const { data } = await http.get("/advances");
    setAdvances(data);
  };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const openAdvancesDrawer = async () => { await loadAdvances(); setShowAdvances(true); };

  const dlPayrollPdf = () => {
    const url = `${API}/reports/payroll.pdf?from_date=${fromDate}&to_date=${toDate}`;
    window.open(url, "_blank");
  };
  const dlWageSlip = (wid, e) => {
    e.stopPropagation();
    const url = `${API}/reports/payroll/${wid}.pdf?from_date=${fromDate}&to_date=${toDate}`;
    window.open(url, "_blank");
  };

  const submitAdvance = async () => {
    try {
      await http.post("/advances", {
        worker_id: advForm.worker_id, amount: Number(advForm.amount),
        date: advForm.date, notes: advForm.notes,
      });
      setAdvForm(null);
      await loadAdvances();
      load();
    } catch (e) { alert(e.response?.data?.detail || e.message); }
  };
  const toggleSettled = async (adv) => {
    await http.patch(`/advances/${adv.id}`, { settled: !adv.settled });
    await loadAdvances();
    load();
  };
  const delAdvance = async (adv) => {
    if (!window.confirm("Delete this advance?")) return;
    await http.delete(`/advances/${adv.id}`);
    await loadAdvances();
    load();
  };

  return (
    <div>
      <PageHeader
        title="Karigar Payroll"
        subtitle="Reports / Payroll"
        testId="payroll-header"
        action={
          <div className="flex gap-2 items-end">
            <Input testId="payroll-from" label="From" type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
            <Input testId="payroll-to" label="To" type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} />
            <BtnPrimary onClick={load} data-testid="payroll-run-btn"><Calendar className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Run</BtnPrimary>
            <BtnPrimary onClick={openAdvancesDrawer} data-testid="open-advances-btn" className="bg-[#2563EB] border-[#2563EB] hover:bg-[#1E40AF]">
              <IndianRupee className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Advances
            </BtnPrimary>
            <BtnPrimary onClick={dlPayrollPdf} data-testid="payroll-pdf-btn" className="bg-[#C27842] border-[#C27842] hover:bg-[#A65D24]">
              <FileDown className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> PDF
            </BtnPrimary>
          </div>
        }
      />

      <div className="p-8 space-y-4">
        {!data ? <Card className="p-12 text-center text-slate-400">Loading...</Card> : (
          <>
            <div className="grid grid-cols-4 gap-4">
              <KpiTile label="Karigars" value={data.worker_count} icon={<UsersIcon className="w-4 h-4" />} />
              <KpiTile label="Total Earnings" value={inr(data.grand_total)} accent="#C27842" />
              <KpiTile label="Open Advances" value={inr(data.grand_advances_open)} accent="#DC2626" />
              <KpiTile label="Net Payable" value={inr(data.grand_net_payable)} accent="#16A34A" />
            </div>

            <Card className="overflow-hidden">
              <table className="w-full text-sm" data-testid="payroll-table">
                <thead className="bg-slate-50 border-b-2 border-slate-200">
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                    <th className="px-4 py-3 font-bold">Karigar</th>
                    <th className="px-4 py-3 font-bold">Skill</th>
                    <th className="px-4 py-3 font-bold text-right">Pairs</th>
                    <th className="px-4 py-3 font-bold text-right">Earnings</th>
                    <th className="px-4 py-3 font-bold text-right">Advances</th>
                    <th className="px-4 py-3 font-bold text-right">Net Payable</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {data.rows.length === 0 ? (
                    <tr><td colSpan="7" className="px-6 py-10 text-center text-slate-400">No payroll data in this period.</td></tr>
                  ) : data.rows.map(r => (
                    <ExpandableRow key={r.worker_id} r={r}
                      expanded={expanded === r.worker_id}
                      onToggle={() => setExpanded(expanded === r.worker_id ? null : r.worker_id)}
                      onSlip={(e) => dlWageSlip(r.worker_id, e)} />
                  ))}
                </tbody>
                {data.rows.length > 0 && (
                  <tfoot>
                    <tr className="bg-[#0F172A] text-white">
                      <td colSpan="3" className="px-4 py-3 text-right font-bold uppercase tracking-wider text-xs">Total</td>
                      <td className="px-4 py-3 text-right font-mono font-bold">{inr(data.grand_total)}</td>
                      <td className="px-4 py-3 text-right font-mono">{inr(data.grand_advances_open)}</td>
                      <td className="px-4 py-3 text-right font-mono font-black text-[#C27842] text-base">{inr(data.grand_net_payable)}</td>
                      <td />
                    </tr>
                  </tfoot>
                )}
              </table>
            </Card>
          </>
        )}
      </div>

      {showAdvances && (
        <Drawer onClose={() => setShowAdvances(false)} title="Karigar Advances" width="max-w-2xl">
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <p className="text-xs text-slate-600">Money taken in advance by a karigar — deducted from their earnings.</p>
              <BtnPrimary onClick={() => setAdvForm({ worker_id: "", amount: "", date: new Date().toISOString().slice(0, 10), notes: "" })} data-testid="new-advance-btn"><Plus className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> New</BtnPrimary>
            </div>
            <table className="w-full text-xs">
              <thead className="bg-slate-50 border-b-2 border-slate-200">
                <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                  <th className="px-3 py-2 font-bold">Date</th>
                  <th className="px-3 py-2 font-bold">Karigar</th>
                  <th className="px-3 py-2 font-bold text-right">Amount</th>
                  <th className="px-3 py-2 font-bold">Notes</th>
                  <th className="px-3 py-2 font-bold">Status</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {advances.length === 0 ? (
                  <tr><td colSpan="6" className="px-3 py-8 text-center text-slate-400">No advances recorded.</td></tr>
                ) : advances.map(a => (
                  <tr key={a.id} className="border-b border-slate-100">
                    <td className="px-3 py-2 font-mono">{(a.date || "").slice(0, 10)}</td>
                    <td className="px-3 py-2 font-bold">{a.worker_name}</td>
                    <td className="px-3 py-2 text-right font-mono font-bold">{inr(a.amount)}</td>
                    <td className="px-3 py-2 text-slate-600 max-w-xs truncate">{a.notes || "—"}</td>
                    <td className="px-3 py-2">
                      <button onClick={() => toggleSettled(a)} data-testid={`toggle-${a.id}`} className="text-[10px] uppercase tracking-wider font-bold">
                        {a.settled ? <Badge color="green">Settled</Badge> : <Badge color="red">Open</Badge>}
                      </button>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button onClick={() => delAdvance(a)} className="text-slate-500 hover:text-red-600 p-1"><Trash2 className="w-3.5 h-3.5" /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Drawer>
      )}

      {advForm && (
        <div className="fixed inset-0 z-[60] grid place-items-center bg-black/40 p-4">
          <div className="bg-white border-2 border-slate-200 shadow-2xl w-full max-w-md">
            <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between">
              <div className="font-bold">New Advance</div>
              <button onClick={() => setAdvForm(null)} className="p-1 hover:bg-slate-100"><X className="w-5 h-5" /></button>
            </div>
            <div className="p-5 space-y-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Karigar</label>
                <select value={advForm.worker_id} onChange={(e) => setAdvForm({ ...advForm, worker_id: e.target.value })}
                  className="w-full border-2 border-slate-300 px-3 py-2 text-sm" data-testid="adv-worker">
                  <option value="">— Select karigar —</option>
                  {workers.map(w => <option key={w.id} value={w.id}>{w.name} ({w.skill})</option>)}
                </select>
              </div>
              <Input label="Amount (₹)" type="number" step="0.01" value={advForm.amount}
                onChange={(e) => setAdvForm({ ...advForm, amount: e.target.value })} testId="adv-amount" />
              <Input label="Date" type="date" value={advForm.date}
                onChange={(e) => setAdvForm({ ...advForm, date: e.target.value })} />
              <Input label="Notes" value={advForm.notes}
                onChange={(e) => setAdvForm({ ...advForm, notes: e.target.value })} />
              <div className="flex gap-2 pt-3 border-t border-slate-200">
                <BtnPrimary onClick={submitAdvance} disabled={!advForm.worker_id || !advForm.amount} data-testid="adv-save"><Check className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Save</BtnPrimary>
                <BtnSecondary onClick={() => setAdvForm(null)}>Cancel</BtnSecondary>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ExpandableRow({ r, expanded, onToggle, onSlip }) {
  return (
    <>
      <tr className="border-b border-slate-100 hover:bg-slate-50 cursor-pointer" onClick={onToggle} data-testid={`payroll-row-${r.worker_id}`}>
        <td className="px-4 py-3 font-bold">{r.name}</td>
        <td className="px-4 py-3"><Badge color="orange">{r.skill}</Badge></td>
        <td className="px-4 py-3 text-right font-mono">{r.total_pairs}</td>
        <td className="px-4 py-3 text-right font-mono font-bold text-[#C27842]">{inr(r.total_earning)}</td>
        <td className="px-4 py-3 text-right font-mono text-red-700">{inr(r.advances_open)}</td>
        <td className="px-4 py-3 text-right font-mono font-bold text-green-700">{inr(r.net_payable)}</td>
        <td className="px-4 py-3 text-right">
          <button onClick={onSlip} className="text-slate-600 hover:text-[#C27842] p-1.5" title="Wage slip" data-testid={`wage-slip-${r.worker_id}`}>
            <FileDown className="w-4 h-4" />
          </button>
          <span className="text-xs text-slate-500 ml-1">{expanded ? "▼" : "▶"}</span>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan="7" className="bg-slate-50 px-8 py-5">
            <div className="space-y-3">
              <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">Per-job earnings (using job-specific rates)</div>
              <table className="w-full text-xs border border-slate-200">
                <thead className="bg-white">
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                    <th className="px-2 py-1.5 border-b">PO</th><th className="px-2 py-1.5 border-b">Style</th>
                    <th className="px-2 py-1.5 border-b">Color</th><th className="px-2 py-1.5 border-b">Size</th>
                    <th className="px-2 py-1.5 border-b">Role</th>
                    <th className="px-2 py-1.5 border-b text-right">Pairs</th>
                    <th className="px-2 py-1.5 border-b text-right">Rate</th>
                    <th className="px-2 py-1.5 border-b text-right">Earning</th>
                  </tr>
                </thead>
                <tbody>
                  {r.jobs.map((j, i) => (
                    <tr key={i} className="border-b border-slate-200">
                      <td className="px-2 py-1.5 font-mono">{j.po_number}</td>
                      <td className="px-2 py-1.5 font-mono">{j.style_code}</td>
                      <td className="px-2 py-1.5">{j.color}</td>
                      <td className="px-2 py-1.5 font-mono">{j.size}</td>
                      <td className="px-2 py-1.5"><Badge color="slate">{(ROLE_LABEL[j.role] || j.role).toUpperCase()}</Badge></td>
                      <td className="px-2 py-1.5 text-right font-mono">{j.pairs}</td>
                      <td className="px-2 py-1.5 text-right font-mono">{inr(j.rate)}/pr</td>
                      <td className="px-2 py-1.5 text-right font-mono font-bold">{inr(j.earning)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function KpiTile({ label, value, accent = "#0F172A", icon }) {
  return (
    <Card className="p-5 relative overflow-hidden">
      <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500 flex items-center gap-1.5">{icon}{label}</div>
      <div className="font-mono text-2xl font-bold mt-2">{value}</div>
      <div className="absolute left-0 top-0 bottom-0 w-1.5" style={{ background: accent }} />
    </Card>
  );
}
