import { useEffect, useState } from "react";
import { http, inr } from "../lib/api";
import { PageHeader, StatTile, Card, BtnSecondary, Badge } from "../components/ui-kit";
import { Link } from "react-router-dom";
import { useAuth } from "../lib/auth";

const STAGE_COLORS = {
  cutting: "#2563EB", fitting: "#0284C7", pasting: "#C27842",
  finishing: "#F59E0B", packing: "#16A34A", dispatched: "#F97316",
};

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const { user } = useAuth();

  useEffect(() => {
    http.get("/dashboard/stats").then((r) => setStats(r.data)).catch(() => {});
  }, []);

  const seedDemo = async () => {
    try {
      await http.post("/seed/demo");
      window.location.reload();
    } catch {}
  };

  if (!stats) return <div className="p-8 text-sm text-slate-500">Loading factory data...</div>;

  const maxStage = Math.max(...Object.values(stats.stage_counts), 1);

  return (
    <div>
      <PageHeader
        title="Control Room"
        subtitle="Dashboard"
        testId="dashboard-header"
        action={
          user?.role === "admin" && stats.materials_count === 0 ? (
            <BtnSecondary onClick={seedDemo} data-testid="seed-demo-btn">Seed demo materials</BtnSecondary>
          ) : (
            <div className="text-xs text-slate-500 uppercase tracking-wider">
              <span className="font-bold text-slate-900">{new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "short", year: "numeric" })}</span>
            </div>
          )
        }
      />

      <div className="p-8 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatTile testId="stat-active-pos" label="Active POs" value={stats.total_pos} sub={`${stats.pending_pos} pending`} accent="#0F172A" />
          <StatTile testId="stat-wip" label="Pairs in WIP" value={stats.pairs_in_wip} sub="across all stages" accent="#C27842" />
          <StatTile testId="stat-dispatched" label="Dispatched" value={stats.dispatched} sub="lifetime pairs" accent="#16A34A" />
          <StatTile testId="stat-revenue" label="Order Value" value={inr(stats.revenue)} sub="cumulative" accent="#2563EB" />
        </div>

        <div className="grid lg:grid-cols-3 gap-6">
          <Card className="lg:col-span-2 p-6">
            <div className="flex items-baseline justify-between mb-5">
              <h2 className="text-xl font-bold">Production Funnel</h2>
              <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Pairs by stage</span>
            </div>
            <div className="space-y-3" data-testid="production-funnel">
              {Object.entries(stats.stage_counts).map(([stage, count]) => (
                <div key={stage}>
                  <div className="flex items-baseline justify-between mb-1">
                    <span className="text-xs uppercase tracking-wider font-bold">{stage}</span>
                    <span className="font-mono text-sm font-bold">{count}</span>
                  </div>
                  <div className="h-6 bg-slate-100 relative overflow-hidden">
                    <div
                      className="h-full transition-all"
                      style={{ width: `${(count / maxStage) * 100}%`, background: STAGE_COLORS[stage] }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card className="p-6">
            <h2 className="text-xl font-bold mb-4">Quick Stats</h2>
            <div className="space-y-3 text-sm">
              <Row label="Materials" value={stats.materials_count} />
              <Row label="Styles" value={stats.styles_count} />
              <Row label="Total POs" value={stats.total_pos} />
              <Row label="Pending POs" value={stats.pending_pos} />
            </div>
            <div className="mt-6 pt-4 border-t border-slate-200 space-y-2">
              <Link to="/pos" className="block text-xs uppercase tracking-wider font-bold text-[#2563EB] hover:underline">→ Manage Purchase Orders</Link>
              <Link to="/production" className="block text-xs uppercase tracking-wider font-bold text-[#C27842] hover:underline">→ View Production Board</Link>
            </div>
          </Card>
        </div>

        <Card className="overflow-hidden">
          <div className="px-6 py-4 border-b-2 border-slate-200 flex items-baseline justify-between">
            <h2 className="text-xl font-bold">Recent Purchase Orders</h2>
            <Link to="/pos" className="text-xs uppercase tracking-wider font-bold text-slate-600 hover:text-[#C27842]">View all →</Link>
          </div>
          <table className="w-full text-sm" data-testid="recent-pos-table">
            <thead className="bg-slate-50 border-b-2 border-slate-200">
              <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                <th className="px-6 py-3 font-bold">PO #</th>
                <th className="px-6 py-3 font-bold">Client</th>
                <th className="px-6 py-3 font-bold text-right">Qty</th>
                <th className="px-6 py-3 font-bold text-right">Value</th>
                <th className="px-6 py-3 font-bold">Delivery</th>
              </tr>
            </thead>
            <tbody>
              {stats.recent_pos.length === 0 ? (
                <tr><td colSpan="5" className="px-6 py-10 text-center text-slate-400">No purchase orders yet. Upload your first PO from the Purchase Orders module.</td></tr>
              ) : stats.recent_pos.map((po) => (
                <tr key={po.id} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="px-6 py-3 font-mono font-bold">{po.po_number}</td>
                  <td className="px-6 py-3">{po.client_name}</td>
                  <td className="px-6 py-3 text-right font-mono">{po.total_quantity}</td>
                  <td className="px-6 py-3 text-right font-mono font-bold">{inr(po.grand_total)}</td>
                  <td className="px-6 py-3 text-xs text-slate-600">{po.delivery_date || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-baseline justify-between border-b border-dashed border-slate-200 pb-2">
      <span className="text-xs uppercase tracking-wider text-slate-500 font-bold">{label}</span>
      <span className="font-mono font-bold">{value}</span>
    </div>
  );
}
