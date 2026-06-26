import { useEffect, useState } from "react";
import { http } from "../lib/api";
import { PageHeader, Card, BtnPrimary, BtnSecondary, Input, Select, Badge } from "../components/ui-kit";
import { Drawer } from "./Materials";
import { Plus, Trash2, Pencil, Save } from "lucide-react";

const ROLES = ["admin", "manager", "production", "sales"];
const empty = { email: "", name: "", role: "production", password: "" };

export default function Users() {
  const [users, setUsers] = useState([]);
  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(empty);

  const load = async () => {
    const { data } = await http.get("/users");
    setUsers(data);
  };
  useEffect(() => { load(); }, []);

  const startNew = () => { setEditId(null); setForm(empty); setOpen(true); };
  const startEdit = (u) => { setEditId(u.id); setForm({ email: u.email, name: u.name, role: u.role, password: "" }); setOpen(true); };
  const save = async () => {
    try {
      if (editId) {
        const body = { name: form.name, role: form.role };
        if (form.password) body.password = form.password;
        await http.patch(`/users/${editId}`, body);
      } else {
        await http.post("/users", form);
      }
      setOpen(false); load();
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    }
  };
  const remove = async (id) => {
    if (!window.confirm("Delete this user?")) return;
    await http.delete(`/users/${id}`); load();
  };

  const roleColor = { admin: "red", manager: "orange", production: "blue", sales: "green" };

  return (
    <div>
      <PageHeader
        title="Users & Roles"
        subtitle="Admin / Users"
        testId="users-header"
        action={<BtnPrimary onClick={startNew} data-testid="add-user-btn"><Plus className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Add User</BtnPrimary>}
      />
      <div className="p-8">
        <Card className="overflow-hidden">
          <table className="w-full text-sm" data-testid="users-table">
            <thead className="bg-slate-50 border-b-2 border-slate-200">
              <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                <th className="px-4 py-3 font-bold">Name</th>
                <th className="px-4 py-3 font-bold">Email</th>
                <th className="px-4 py-3 font-bold">Role</th>
                <th className="px-4 py-3 font-bold">Status</th>
                <th className="px-4 py-3 font-bold text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-3 font-bold">{u.name}</td>
                  <td className="px-4 py-3 font-mono text-xs">{u.email}</td>
                  <td className="px-4 py-3"><Badge color={roleColor[u.role]}>{u.role}</Badge></td>
                  <td className="px-4 py-3"><Badge color={u.active === false ? "red" : "green"}>{u.active === false ? "Inactive" : "Active"}</Badge></td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => startEdit(u)} className="text-slate-600 hover:text-[#2563EB] p-1.5"><Pencil className="w-4 h-4" /></button>
                    <button onClick={() => remove(u.id)} className="text-slate-600 hover:text-red-600 p-1.5 ml-1"><Trash2 className="w-4 h-4" /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      {open && (
        <Drawer onClose={() => setOpen(false)} title={editId ? "Edit User" : "New User"}>
          <div className="space-y-3">
            <Input label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} testId="form-user-name" />
            <Input label="Email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} disabled={!!editId} testId="form-user-email" />
            <Select label="Role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} testId="form-user-role">
              {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
            </Select>
            <Input label={editId ? "New password (optional)" : "Password"} type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            <div className="flex gap-2 pt-3">
              <BtnPrimary onClick={save} data-testid="save-user-btn"><Save className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Save</BtnPrimary>
              <BtnSecondary onClick={() => setOpen(false)}>Cancel</BtnSecondary>
            </div>
          </div>
        </Drawer>
      )}
    </div>
  );
}
