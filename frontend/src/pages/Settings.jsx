import { useEffect, useState } from "react";
import { http } from "../lib/api";
import { PageHeader, Card, BtnPrimary, BtnSecondary } from "../components/ui-kit";
import { Clock, RotateCcw, Save, Check, Package, Upload, Trash2, FileSpreadsheet } from "lucide-react";

const STAGE_LABEL = {
  procurement: "Procurement",
  cutting: "Cutting",
  folding: "Folding",
  attachment: "Attachment",
  stitching: "Stitching",
  lasting: "Lasting",
  sole_pasting: "Sole Pasting",
  finishing: "Finish / QC / Pack",
};

const STAGE_ORDER = ["procurement", "cutting", "folding", "attachment", "stitching", "lasting", "sole_pasting", "finishing"];

export default function Settings() {
  const [hours, setHours] = useState({});
  const [defaults, setDefaults] = useState({});
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const { data } = await http.get("/settings/stage-durations");
    setHours(data.hours || {});
    setDefaults(data.defaults || {});
  };
  useEffect(() => { load(); }, []);

  const setStage = (k, v) => setHours(h => ({ ...h, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      const payload = { hours: {} };
      STAGE_ORDER.forEach(k => { payload.hours[k] = Number(hours[k] || 0); });
      await http.put("/settings/stage-durations", payload);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) { alert(e.response?.data?.detail || e.message); }
    finally { setSaving(false); }
  };

  const resetToDefault = () => setHours({ ...defaults });

  const totalHours = STAGE_ORDER.reduce((s, k) => s + Number(hours[k] || 0), 0);

  return (
    <div>
      <PageHeader
        title="Settings"
        subtitle="System / ETA Configuration"
        testId="settings-header"
        action={
          <div className="flex gap-2">
            <BtnSecondary onClick={resetToDefault} data-testid="reset-defaults-btn">
              <RotateCcw className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Reset to default
            </BtnSecondary>
            <BtnPrimary onClick={save} disabled={saving} data-testid="save-settings-btn"
              className="bg-[#16A34A] border-[#16A34A] hover:bg-[#0F7A36]">
              {saved ? <><Check className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Saved</> : <><Save className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> {saving ? "Saving..." : "Save"}</>}
            </BtnPrimary>
          </div>
        }
      />
      <div className="p-8 space-y-6 max-w-4xl">
        <Card className="p-6">
          <div className="flex items-baseline justify-between mb-1">
            <h2 className="text-xl font-bold flex items-center gap-2">
              <Clock className="w-5 h-5 text-[#C27842]" /> Stage ETA / Deadline (hours)
            </h2>
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
              Total ETA: <span className="font-mono text-slate-900">{totalHours} hrs ≈ {(totalHours / 24).toFixed(1)} days</span>
            </div>
          </div>
          <p className="text-xs text-slate-600 mb-5">
            Maximum allowed time for a job to remain in each production stage. Once a stage is exceeded, the job appears in the <b>Overdue</b> alert on the Dashboard and is highlighted on the Production floor.
          </p>

          <div className="space-y-2" data-testid="stage-duration-list">
            {STAGE_ORDER.map((k) => (
              <div key={k} className="flex items-center gap-4 border-2 border-slate-200 px-4 py-3 hover:border-[#C27842] transition-colors">
                <div className="w-44 font-bold uppercase tracking-wider text-sm">{STAGE_LABEL[k]}</div>
                <div className="flex items-center gap-2 flex-1">
                  <input
                    type="number" min="0" step="1"
                    value={hours[k] ?? ""}
                    onChange={(e) => setStage(k, e.target.value)}
                    data-testid={`duration-input-${k}`}
                    className="w-28 border-2 border-slate-300 px-3 py-2 font-mono text-lg focus:border-[#C27842] focus:outline-none"
                  />
                  <span className="text-xs uppercase tracking-wider font-bold text-slate-500">hours</span>
                  <span className="text-xs text-slate-500 ml-2">≈ {(Number(hours[k] || 0) / 24).toFixed(1)} days</span>
                </div>
                <div className="text-[10px] uppercase tracking-wider text-slate-400">
                  Default: <span className="font-mono font-bold">{defaults[k]}h</span>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-5 bg-orange-50 border-orange-200">
          <div className="text-xs text-slate-700 leading-relaxed">
            <b className="text-[#C27842]">How this works:</b> Whenever a production job moves to a new stage, the system records the entry time and computes a deadline as <i>entry + stage hours</i>. If the deadline passes without the job moving forward, it appears in the <b>Overdue</b> widget on the Dashboard and the Production board card turns red with an alert badge. Existing jobs use these settings on their next stage transition.
          </div>
        </Card>

        <PackingTemplatesSection />
      </div>
    </div>
  );
}

/* -------------------- PACKING TEMPLATES SECTION -------------------- */
function PackingTemplatesSection() {
  const [templates, setTemplates] = useState([]);
  const [form, setForm] = useState({ client_name: "", name: "", aliases: "", file_b64: "", file_name: "" });
  const [uploading, setUploading] = useState(false);

  const load = async () => {
    const { data } = await http.get("/packing-templates");
    setTemplates(data || []);
  };
  useEffect(() => { load(); }, []);

  const pickFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => {
      const b64 = String(reader.result).split(",", 2)[1] || "";
      setForm(s => ({ ...s, file_b64: b64, file_name: f.name }));
    };
    reader.readAsDataURL(f);
  };

  const upload = async () => {
    if (!form.client_name || !form.name || !form.file_b64) {
      alert("Client name, template name and Excel file are required.");
      return;
    }
    setUploading(true);
    try {
      const aliases = form.aliases.split(",").map(s => s.trim()).filter(Boolean);
      await http.post("/packing-templates", {
        client_name: form.client_name, name: form.name, aliases, file_b64: form.file_b64,
      });
      setForm({ client_name: "", name: "", aliases: "", file_b64: "", file_name: "" });
      load();
    } catch (e) {
      alert("Upload failed: " + (e.response?.data?.detail || e.message));
    } finally {
      setUploading(false);
    }
  };

  const remove = async (t) => {
    if (!window.confirm(`Delete template "${t.name}"?`)) return;
    await http.delete(`/packing-templates/${t.id}`);
    load();
  };

  return (
    <Card className="p-6" data-testid="packing-templates-section">
      <h2 className="text-xl font-bold flex items-center gap-2 mb-1">
        <Package className="w-5 h-5 text-[#16A34A]" /> Packing-List Templates
      </h2>
      <p className="text-xs text-slate-600 mb-5">
        Upload custom Excel layouts your clients require. Use <code className="bg-slate-100 px-1">{`{{po_number}}`}</code>, <code className="bg-slate-100 px-1">{`{{client_name}}`}</code>, <code className="bg-slate-100 px-1">{`{{vendor_name}}`}</code>, <code className="bg-slate-100 px-1">{`{{carton_dim}}`}</code>, <code className="bg-slate-100 px-1">{`{{dispatch_date}}`}</code>, <code className="bg-slate-100 px-1">{`{{transporter}}`}</code>, <code className="bg-slate-100 px-1">{`{{vehicle_no}}`}</code>, <code className="bg-slate-100 px-1">{`{{notes}}`}</code> etc. as placeholders, and mark the line-item row with the cell <code className="bg-slate-100 px-1">{`{{lines}}`}</code>. The system auto-picks the template whose <b>alias</b> matches the PO client name.
      </p>

      <div className="bg-slate-50 border-2 border-dashed border-slate-300 p-4 mb-5">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
          <input value={form.client_name} onChange={e => setForm(s => ({ ...s, client_name: e.target.value }))}
            placeholder="Client name (eg. NEXTGEN FASTFASHION LIMITED)" data-testid="pt-client-name"
            className="border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#16A34A] outline-none" />
          <input value={form.name} onChange={e => setForm(s => ({ ...s, name: e.target.value }))}
            placeholder="Template label (eg. SHEIN std)" data-testid="pt-name"
            className="border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#16A34A] outline-none" />
          <input value={form.aliases} onChange={e => setForm(s => ({ ...s, aliases: e.target.value }))}
            placeholder="Aliases (comma-separated: shein, nextgen, ril)" data-testid="pt-aliases"
            className="border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#16A34A] outline-none" />
        </div>
        <div className="flex items-center gap-3">
          <label className="cursor-pointer inline-flex items-center gap-2 text-sm font-bold uppercase tracking-wider border-2 border-slate-300 hover:border-[#0F172A] px-4 py-2" data-testid="pt-file-label">
            <Upload className="w-4 h-4" /> {form.file_name || "Pick xlsx file"}
            <input type="file" accept=".xlsx" onChange={pickFile} className="hidden" data-testid="pt-file-input" />
          </label>
          <BtnPrimary onClick={upload} disabled={uploading} data-testid="pt-upload"
            className="bg-[#16A34A] border-[#16A34A] hover:bg-[#0F7A36]">
            {uploading ? "Uploading…" : "Save template"}
          </BtnPrimary>
        </div>
      </div>

      {templates.length === 0 ? (
        <div className="text-center text-slate-400 text-sm py-8" data-testid="pt-empty">
          No custom templates yet. The default SSK layout is used until you add one.
        </div>
      ) : (
        <table className="w-full text-sm" data-testid="pt-list">
          <thead className="bg-slate-50 border-b-2 border-slate-200">
            <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
              <th className="px-4 py-2 font-bold">Client</th>
              <th className="px-4 py-2 font-bold">Template</th>
              <th className="px-4 py-2 font-bold">Aliases</th>
              <th className="px-4 py-2 font-bold">Created</th>
              <th className="px-4 py-2 font-bold text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {templates.map(t => (
              <tr key={t.id} className="border-b border-slate-100 hover:bg-slate-50" data-testid={`pt-row-${t.id}`}>
                <td className="px-4 py-2 font-bold">{t.client_name}</td>
                <td className="px-4 py-2 flex items-center gap-2"><FileSpreadsheet className="w-3.5 h-3.5 text-[#16A34A]" /> {t.name}</td>
                <td className="px-4 py-2 text-xs text-slate-600 font-mono">{(t.aliases || []).join(", ") || "—"}</td>
                <td className="px-4 py-2 text-xs text-slate-500 font-mono">{(t.created_at || "").slice(0, 10)}</td>
                <td className="px-4 py-2 text-right">
                  <button onClick={() => remove(t)} className="text-slate-600 hover:text-red-600 p-1.5" data-testid={`pt-delete-${t.id}`}>
                    <Trash2 className="w-4 h-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
