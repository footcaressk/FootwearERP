import { useEffect, useState, useMemo } from "react";
import { http, inr, num } from "../lib/api";
import { PageHeader, Card, BtnPrimary, BtnSecondary, Input, Badge } from "../components/ui-kit";
import { TrendingUp, Calendar, Users as UsersIcon } from "lucide-react";

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

  const load = async () => {
    const params = new URLSearchParams();
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const { data } = await http.get(`/reports/payroll?${params.toString()}`);
    setData(data);
  };
  useEffect(() => { load(); }, []); // initial

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
          </div>
        }
      />

      <div className="p-8 space-y-4">
        {!data ? <Card className="p-12 text-center text-slate-400">Loading...</Card> : (
          <>
            <div className="grid grid-cols-3 gap-4">
              <KpiTile label="Karigars Earning" value={data.worker_count} icon={<UsersIcon className="w-4 h-4" />} />
              <KpiTile label="Total Payout" value={inr(data.grand_total)} accent="#C27842" icon={<TrendingUp className="w-4 h-4" />} />
              <KpiTile label="Period" value={`${data.from_date || "—"} → ${data.to_date || "—"}`} accent="#2563EB" />
            </div>

            <Card className="overflow-hidden">
              <table className="w-full text-sm" data-testid="payroll-table">
                <thead className="bg-slate-50 border-b-2 border-slate-200">
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                    <th className="px-4 py-3 font-bold">Karigar</th>
                    <th className="px-4 py-3 font-bold">Primary Skill</th>
                    <th className="px-4 py-3 font-bold">Phone</th>
                    <th className="px-4 py-3 font-bold text-right">Rate/pair</th>
                    <th className="px-4 py-3 font-bold text-right">Total Pairs</th>
                    <th className="px-4 py-3 font-bold text-right">Earnings</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {data.rows.length === 0 ? (
                    <tr><td colSpan="7" className="px-6 py-10 text-center text-slate-400">No payroll data in this period. Assign karigars to production cards and mark completed quantities.</td></tr>
                  ) : data.rows.map(r => (
                    <ExpandableRow key={r.worker_id} r={r} expanded={expanded === r.worker_id} onToggle={() => setExpanded(expanded === r.worker_id ? null : r.worker_id)} />
                  ))}
                </tbody>
                {data.rows.length > 0 && (
                  <tfoot>
                    <tr className="bg-[#0F172A] text-white">
                      <td colSpan="5" className="px-4 py-3 text-right font-bold uppercase tracking-wider text-xs">Grand Total</td>
                      <td className="px-4 py-3 text-right font-mono font-black text-lg text-[#C27842]">{inr(data.grand_total)}</td>
                      <td />
                    </tr>
                  </tfoot>
                )}
              </table>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}

function ExpandableRow({ r, expanded, onToggle }) {
  return (
    <>
      <tr className="border-b border-slate-100 hover:bg-slate-50 cursor-pointer" onClick={onToggle} data-testid={`payroll-row-${r.worker_id}`}>
        <td className="px-4 py-3 font-bold">{r.name}</td>
        <td className="px-4 py-3"><Badge color="orange">{r.skill}</Badge></td>
        <td className="px-4 py-3 font-mono text-xs text-slate-500">{r.phone || "—"}</td>
        <td className="px-4 py-3 text-right font-mono">₹{r.rate_per_pair}</td>
        <td className="px-4 py-3 text-right font-mono font-bold">{r.total_pairs}</td>
        <td className="px-4 py-3 text-right font-mono font-bold text-[#C27842]">{inr(r.total_earning)}</td>
        <td className="px-4 py-3 text-xs text-slate-500">{expanded ? "▼" : "▶"}</td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan="7" className="bg-slate-50 px-8 py-5">
            <div className="space-y-3">
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500 mb-2">Pairs by role</div>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(r.by_role).map(([role, pairs]) => (
                    <div key={role} className="bg-white border border-slate-200 px-3 py-1.5">
                      <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mr-2">{ROLE_LABEL[role] || role}</span>
                      <span className="font-mono font-bold">{pairs}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500 mb-2">Jobs ({r.jobs.length})</div>
                <table className="w-full text-xs border border-slate-200">
                  <thead className="bg-white">
                    <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                      <th className="px-2 py-1.5 border-b">PO</th>
                      <th className="px-2 py-1.5 border-b">Style</th>
                      <th className="px-2 py-1.5 border-b">Color</th>
                      <th className="px-2 py-1.5 border-b">Size</th>
                      <th className="px-2 py-1.5 border-b">Role</th>
                      <th className="px-2 py-1.5 border-b text-right">Pairs</th>
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
                        <td className="px-2 py-1.5"><Badge color="slate">{ROLE_LABEL[j.role] || j.role}</Badge></td>
                        <td className="px-2 py-1.5 text-right font-mono">{j.pairs}</td>
                        <td className="px-2 py-1.5 text-right font-mono font-bold">{inr(j.earning)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
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
