"""SSK Footcare Management System — FastAPI backend."""
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

import os
import logging
from datetime import datetime, timezone
from typing import List, Optional, Literal

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr
from bson import ObjectId

from auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    set_auth_cookies, clear_auth_cookies,
    get_current_user_factory, require_roles, seed_admin,
)
from po_extractor import extract_po_from_pdf, extract_po_from_xlsx
from pdf_docs import generate_dispatch_challan_pdf, build_invoice
from pdf_procurement import build_material_requirement
from fastapi.responses import StreamingResponse
from io import BytesIO

# ---------- DB & app ----------
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="SSK Footcare ERP")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ssk")

# ---------- Helpers ----------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def oid(v) -> ObjectId:
    try:
        return ObjectId(v)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


def stringify(doc: dict) -> dict:
    if doc is None:
        return doc
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


# ---------- Pydantic models ----------
Role = Literal["admin", "manager", "production", "sales"]

class LoginInput(BaseModel):
    email: EmailStr
    password: str

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: Role = "production"

class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[Role] = None
    active: Optional[bool] = None
    password: Optional[str] = None

class MaterialIn(BaseModel):
    code: str
    name: str
    category: Literal["upper", "sole", "lining", "accessory", "consumable", "packing", "other"]
    unit: str
    rate: float
    reorder_level: float = 0
    notes: Optional[str] = ""

class BomItem(BaseModel):
    material_id: str
    material_name: str
    material_code: str
    unit: str
    rate: float
    quantity: float
    yield_per_unit: float = 1  # pairs produced per 1 unit of material (e.g., 10 uppers per meter)
    waste_pct: float = 0
    section: str = "Other"
    component: Optional[str] = None  # "upper" | "bottom" | "sole" (auto-classified or manual)

class LaborItem(BaseModel):
    name: str
    rate: float  # per pair

class StyleIn(BaseModel):
    code: str
    name: str
    category: Optional[str] = "Footwear"
    image_url: Optional[str] = ""
    description: Optional[str] = ""
    base_size: Optional[str] = "7"
    bom: List[BomItem] = []
    labor: List[LaborItem] = []
    overhead_pct: float = 0
    packing_cost: float = 0
    margin_pct: float = 25
    gst_pct: float = 5

class POLineItem(BaseModel):
    style_code: str
    description: Optional[str] = ""
    color: Optional[str] = ""
    size: Optional[str] = ""
    hsn_code: Optional[str] = ""
    quantity: int
    unit_price: float
    amount: float

class POIn(BaseModel):
    po_number: str
    po_date: str  # ISO
    client_name: str
    client_address: Optional[str] = ""
    billing_address: Optional[str] = ""
    shipping_address: Optional[str] = ""
    delivery_date: Optional[str] = ""
    payment_terms: Optional[str] = ""
    currency: str = "INR"
    line_items: List[POLineItem]
    subtotal: float = 0
    cgst_rate: float = 0
    cgst_amount: float = 0
    sgst_rate: float = 0
    sgst_amount: float = 0
    igst_rate: float = 0
    igst_amount: float = 0
    grand_total: float = 0
    total_quantity: int = 0
    notes: Optional[str] = ""

PRODUCTION_STAGES = [
    "procurement", "cutting", "folding", "attachment",
    "stitching", "lasting", "sole_pasting", "finishing", "dispatched",
]

class ProductionStageUpdate(BaseModel):
    stage: Literal["procurement", "cutting", "folding", "attachment",
                   "stitching", "lasting", "sole_pasting", "finishing", "dispatched"]
    completed_qty: Optional[int] = None
    rejected_qty: Optional[int] = None
    qc_pass: Optional[bool] = None
    notes: Optional[str] = ""

class ComponentUpdate(BaseModel):
    upper_done: Optional[bool] = None
    bottom_done: Optional[bool] = None
    sole_done: Optional[bool] = None
    notes: Optional[str] = ""

class WorkerIn(BaseModel):
    name: str
    phone: Optional[str] = ""
    skill: str = "general"  # general / cutting / upper / bottom / stitching / lasting / sole_pasting / finishing
    rate_per_pair: float = 0
    active: bool = True
    notes: Optional[str] = ""

class AssignmentUpdate(BaseModel):
    role: str  # cutting | upper | bottom | sole | stitching | lasting | sole_pasting | finishing
    worker_id: Optional[str] = None  # null = unassign
    worker_name: Optional[str] = None  # denormalised for quick display
    rate_per_pair: Optional[float] = None  # negotiated rate for THIS style/job (overrides worker default)

class BulkAssign(BaseModel):
    job_ids: List[str]
    role: str
    worker_id: Optional[str] = None
    rate_per_pair: Optional[float] = None

class AdvanceIn(BaseModel):
    worker_id: str
    amount: float
    date: Optional[str] = ""
    notes: Optional[str] = ""



class QuantityUpdate(BaseModel):
    quantity: Optional[int] = None
    completed_qty: Optional[int] = None
    rejected_qty: Optional[int] = None
    reason: Optional[str] = ""

class InventoryMovement(BaseModel):
    material_id: str
    type: Literal["in", "out", "adjustment"]  # in = stock-in (purchase), out = consumption, adjustment = correction
    quantity: float
    rate: Optional[float] = None  # unit rate at this movement (purchase price)
    party: Optional[str] = ""  # supplier name for IN, job/po reference for OUT
    job_id: Optional[str] = None  # if linked to a production job
    notes: Optional[str] = ""
    date: Optional[str] = ""  # ISO date

class InvoiceGenerate(BaseModel):
    po_id: str
    job_ids: Optional[List[str]] = None  # if None, full PO; otherwise dispatched-only items
    transport_mode: Optional[str] = ""
    vehicle_no: Optional[str] = ""
    supply_date: Optional[str] = ""

class DefectIn(BaseModel):
    po_number: str
    article: Optional[str] = ""
    stage: str
    defect_type: str
    description: str
    defective_qty: int
    root_cause: Optional[str] = ""
    responsible_dept: Optional[str] = ""
    corrective_action: Optional[str] = ""
    rework_qty: int = 0
    rework_completed: bool = False
    final_rejection_qty: int = 0
    cost: float = 0
    status: Literal["open", "in_progress", "closed"] = "open"


# ---------- Dependencies ----------
get_current_user = None  # set after startup


# ---------- AUTH ----------
@api.post("/auth/login")
async def login(payload: LoginInput, response: Response):
    email = payload.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("active", True) or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    uid = str(user["_id"])
    access = create_access_token(uid, email, user["role"])
    refresh = create_refresh_token(uid)
    set_auth_cookies(response, access, refresh)
    return {
        "id": uid, "email": email, "name": user["name"], "role": user["role"],
        "access_token": access,
    }

@api.post("/auth/logout")
async def logout(response: Response):
    clear_auth_cookies(response)
    return {"ok": True}

@api.get("/auth/me")
async def me(request: Request):
    user = await get_current_user(request)
    return user


# ---------- USERS (admin) ----------
@api.get("/users")
async def list_users(request: Request):
    user = await get_current_user(request)
    require_roles("admin")(user)
    docs = await db.users.find({}, {"password_hash": 0}).to_list(500)
    return [stringify(d) for d in docs]

@api.post("/users")
async def create_user(payload: UserCreate, request: Request):
    user = await get_current_user(request)
    require_roles("admin")(user)
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "Email already exists")
    doc = {
        "email": email, "name": payload.name, "role": payload.role,
        "password_hash": hash_password(payload.password),
        "active": True, "created_at": now_iso(),
    }
    res = await db.users.insert_one(doc)
    return {
        "id": str(res.inserted_id),
        "email": email,
        "name": payload.name,
        "role": payload.role,
        "active": True,
        "created_at": doc["created_at"],
    }

@api.patch("/users/{user_id}")
async def update_user(user_id: str, payload: UserUpdate, request: Request):
    user = await get_current_user(request)
    require_roles("admin")(user)
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if "password" in update:
        update["password_hash"] = hash_password(update.pop("password"))
    await db.users.update_one({"_id": oid(user_id)}, {"$set": update})
    doc = await db.users.find_one({"_id": oid(user_id)}, {"password_hash": 0})
    return stringify(doc)

@api.delete("/users/{user_id}")
async def delete_user(user_id: str, request: Request):
    user = await get_current_user(request)
    require_roles("admin")(user)
    if user["id"] == user_id:
        raise HTTPException(400, "Cannot delete yourself")
    await db.users.delete_one({"_id": oid(user_id)})
    return {"ok": True}


# ---------- MATERIALS (rate card) ----------
@api.get("/materials")
async def list_materials(request: Request):
    await get_current_user(request)
    docs = await db.materials.find({}).sort("name", 1).to_list(2000)
    return [stringify(d) for d in docs]

@api.post("/materials")
async def create_material(payload: MaterialIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    doc = payload.model_dump()
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    res = await db.materials.insert_one(doc)
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    return doc

@api.patch("/materials/{mid}")
async def update_material(mid: str, payload: MaterialIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    update = payload.model_dump()
    update["updated_at"] = now_iso()
    await db.materials.update_one({"_id": oid(mid)}, {"$set": update})
    return stringify(await db.materials.find_one({"_id": oid(mid)}))

@api.delete("/materials/{mid}")
async def delete_material(mid: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    await db.materials.delete_one({"_id": oid(mid)})
    return {"ok": True}


# ---------- STYLES ----------
def compute_style_costing(style: dict) -> dict:
    materials_cost = 0.0
    for b in style.get("bom", []):
        rate = float(b.get("rate", 0))
        qty = float(b.get("quantity", 0))
        yld = float(b.get("yield_per_unit", 1) or 1)
        waste = float(b.get("waste_pct", 0) or 0)
        # cost per pair = (rate * qty / yield) * (1 + waste%)
        materials_cost += (rate * qty / yld) * (1 + waste / 100)
    labor_cost = sum(float(l.get("rate", 0)) for l in style.get("labor", []))
    base_cost = materials_cost + labor_cost
    overhead_cost = base_cost * (style.get("overhead_pct", 0) / 100)
    packing = style.get("packing_cost", 0)
    total_cost = base_cost + overhead_cost + packing
    margin_amount = total_cost * (style.get("margin_pct", 0) / 100)
    selling_price = total_cost + margin_amount
    gst_amount = selling_price * (style.get("gst_pct", 0) / 100)
    final_price = selling_price + gst_amount
    return {
        "materials_cost": round(materials_cost, 2),
        "labor_cost": round(labor_cost, 2),
        "overhead_cost": round(overhead_cost, 2),
        "packing_cost": round(packing, 2),
        "total_cost": round(total_cost, 2),
        "margin_amount": round(margin_amount, 2),
        "selling_price": round(selling_price, 2),
        "gst_amount": round(gst_amount, 2),
        "final_price": round(final_price, 2),
    }

@api.get("/styles")
async def list_styles(request: Request):
    await get_current_user(request)
    docs = await db.styles.find({}).sort("created_at", -1).to_list(1000)
    out = []
    for d in docs:
        d = stringify(d)
        d["costing"] = compute_style_costing(d)
        out.append(d)
    return out

@api.get("/styles/{sid}")
async def get_style(sid: str, request: Request):
    await get_current_user(request)
    d = await db.styles.find_one({"_id": oid(sid)})
    if not d:
        raise HTTPException(404, "Not found")
    d = stringify(d)
    d["costing"] = compute_style_costing(d)
    return d

@api.post("/styles")
async def create_style(payload: StyleIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    doc = payload.model_dump()
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    res = await db.styles.insert_one(doc)
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    doc["costing"] = compute_style_costing(doc)
    return doc

@api.patch("/styles/{sid}")
async def update_style(sid: str, payload: StyleIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    update = payload.model_dump()
    update["updated_at"] = now_iso()
    await db.styles.update_one({"_id": oid(sid)}, {"$set": update})
    d = stringify(await db.styles.find_one({"_id": oid(sid)}))
    d["costing"] = compute_style_costing(d)
    return d

@api.delete("/styles/{sid}")
async def delete_style(sid: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    await db.styles.delete_one({"_id": oid(sid)})
    return {"ok": True}


# ---------- COSTING (live preview) ----------
@api.post("/costing/preview")
async def costing_preview(payload: StyleIn, request: Request):
    await get_current_user(request)
    return compute_style_costing(payload.model_dump())


# ---------- PURCHASE ORDERS ----------
@api.get("/pos")
async def list_pos(request: Request):
    await get_current_user(request)
    docs = await db.pos.find({}).sort("created_at", -1).to_list(1000)
    return [stringify(d) for d in docs]

@api.get("/pos/{pid}")
async def get_po(pid: str, request: Request):
    await get_current_user(request)
    d = await db.pos.find_one({"_id": oid(pid)})
    if not d:
        raise HTTPException(404, "Not found")
    return stringify(d)

@api.post("/pos")
async def create_po(payload: POIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager", "sales")(u)
    doc = payload.model_dump()
    doc["status"] = "pending"
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    if not doc.get("total_quantity"):
        doc["total_quantity"] = sum(li["quantity"] for li in doc["line_items"])
    if not doc.get("subtotal"):
        doc["subtotal"] = sum(li["amount"] for li in doc["line_items"])
    res = await db.pos.insert_one(doc)
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    # auto-create production jobs (one per line item)
    jobs = []
    for li in doc["line_items"]:
        jobs.append({
            "po_id": doc["id"],
            "po_number": doc["po_number"],
            "client_name": doc["client_name"],
            "style_code": li["style_code"],
            "description": li.get("description", ""),
            "color": li.get("color", ""),
            "size": li.get("size", ""),
            "quantity": li["quantity"],
            "completed_qty": 0,
            "stage": "procurement",
            "rejected_qty": 0,
            "delivery_date": doc.get("delivery_date", ""),
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "history": [{"stage": "procurement", "at": now_iso(), "by": u["email"], "notes": "Job created"}],
        })
    if jobs:
        await db.production_jobs.insert_many(jobs)
    return doc

@api.patch("/pos/{pid}")
async def update_po(pid: str, payload: POIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager", "sales")(u)
    update = payload.model_dump()
    update["updated_at"] = now_iso()
    await db.pos.update_one({"_id": oid(pid)}, {"$set": update})
    return stringify(await db.pos.find_one({"_id": oid(pid)}))

@api.delete("/pos/{pid}")
async def delete_po(pid: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    await db.pos.delete_one({"_id": oid(pid)})
    await db.production_jobs.delete_many({"po_id": pid})
    return {"ok": True}

@api.post("/pos/extract")
async def extract_po(file: UploadFile = File(...), request: Request = None):
    u = await get_current_user(request); require_roles("admin", "manager", "sales")(u)
    content = await file.read()
    fname = (file.filename or "").lower()
    try:
        if fname.endswith(".pdf"):
            data = await extract_po_from_pdf(content)
        elif fname.endswith(".xlsx") or fname.endswith(".xls"):
            data = await extract_po_from_xlsx(content)
        else:
            raise HTTPException(400, "Only PDF or Excel (xlsx) files are supported")
        return data
    except HTTPException:
        raise
    except Exception as e:
        log.exception("PO extraction failed")
        raise HTTPException(500, f"Extraction failed: {e}")


async def next_invoice_no() -> str:
    """Generate SSK<FY>-XXX format like SSK26-27-004. FY based on Apr-Mar split."""
    today = datetime.now(timezone.utc)
    # Indian FY starts April. If month < 4, FY started prev year.
    yr = today.year
    if today.month < 4:
        fy_start = yr - 1
    else:
        fy_start = yr
    fy_end = fy_start + 1
    fy_label = f"{str(fy_start)[-2:]}-{str(fy_end)[-2:]}"
    # Atomic counter
    counter = await db.counters.find_one_and_update(
        {"_id": f"invoice_{fy_label}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    seq = counter.get("seq", 1) if counter else 1
    return f"SSK{fy_label}-{seq:03d}"


async def _generate_invoice_payload(po: dict, job_ids: list[str] | None) -> tuple[dict, list[dict]]:
    """Returns the (po-augmented, line_items) for invoice generation.

    If job_ids given, filter dispatched jobs and rebuild line items from them — supports merged
    invoice across multiple dispatched cards.
    """
    if not job_ids:
        return po, po.get("line_items", [])

    # Pull dispatched production_jobs by ids, aggregate per (style_code, color, size)
    obj_ids = []
    for jid in job_ids:
        try:
            obj_ids.append(oid(jid))
        except HTTPException:
            continue
    jobs = await db.production_jobs.find({"_id": {"$in": obj_ids}}).to_list(2000)
    # Build map of line items from PO indexed by (style, color, size)
    po_items = po.get("line_items", [])
    idx = {}
    for li in po_items:
        idx[(li.get("style_code"), li.get("color"), str(li.get("size", "")))] = li

    line_items = []
    for j in jobs:
        key = (j.get("style_code"), j.get("color"), str(j.get("size", "")))
        li_src = idx.get(key, {})
        qty = j.get("quantity", 0)
        unit_price = li_src.get("unit_price", 0)
        line_items.append({
            "style_code": j.get("style_code", ""),
            "description": j.get("description") or li_src.get("description", ""),
            "color": j.get("color", ""),
            "size": str(j.get("size", "")),
            "hsn_code": li_src.get("hsn_code", "") or "64029990",
            "quantity": qty,
            "unit_price": unit_price,
            "amount": round(qty * unit_price, 2),
            "mrp": li_src.get("mrp", ""),
        })
    return po, line_items


@api.get("/pos/{pid}/invoice.pdf")
async def po_invoice(pid: str, request: Request):
    await get_current_user(request)
    doc = await db.pos.find_one({"_id": oid(pid)})
    if not doc:
        raise HTTPException(404, "Not found")
    po = stringify(doc)
    # auto-issue invoice number on first download (and persist)
    invoice_no = po.get("invoice_no")
    invoice_date = po.get("invoice_date")
    if not invoice_no:
        invoice_no = await next_invoice_no()
        invoice_date = datetime.now().strftime("%d/%m/%Y")
        await db.pos.update_one({"_id": oid(pid)}, {"$set": {"invoice_no": invoice_no, "invoice_date": invoice_date}})
        po["invoice_no"] = invoice_no
        po["invoice_date"] = invoice_date
    pdf_bytes = build_invoice(po, invoice_no, invoice_date)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice_no}.pdf"'},
    )


@api.post("/invoices/job")
async def invoice_for_jobs(payload: InvoiceGenerate, request: Request):
    """Generate an invoice for a subset of production jobs (dispatched). Supports merging."""
    u = await get_current_user(request); require_roles("admin", "manager", "sales")(u)
    po_doc = await db.pos.find_one({"_id": oid(payload.po_id)})
    if not po_doc:
        raise HTTPException(404, "PO not found")
    po = stringify(po_doc)
    po, line_items = await _generate_invoice_payload(po, payload.job_ids)
    if not line_items:
        raise HTTPException(400, "No line items for invoice")

    invoice_no = await next_invoice_no()
    invoice_date = datetime.now().strftime("%d/%m/%Y")
    pdf_bytes = build_invoice(
        po, invoice_no, invoice_date,
        transport_mode=payload.transport_mode or "",
        vehicle_no=payload.vehicle_no or "",
        supply_date=payload.supply_date or "",
        line_items=line_items,
    )
    # Store invoice record
    await db.invoices.insert_one({
        "invoice_no": invoice_no, "invoice_date": invoice_date,
        "po_id": payload.po_id, "po_number": po.get("po_number"),
        "client_name": po.get("client_name"),
        "job_ids": payload.job_ids or [],
        "line_items_snapshot": line_items,
        "transport_mode": payload.transport_mode, "vehicle_no": payload.vehicle_no,
        "supply_date": payload.supply_date,
        "by": u["email"], "created_at": now_iso(),
    })
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice_no}.pdf"'},
    )


@api.post("/invoices/merged")
async def merged_invoice(payload: dict, request: Request):
    """Generate a single merged invoice across multiple POs/jobs.
    payload: { entries: [{po_id, job_ids:[...]}] , transport_mode, vehicle_no, supply_date }
    All entries must share the same client (uses first PO's client).
    """
    u = await get_current_user(request); require_roles("admin", "manager", "sales")(u)
    entries = payload.get("entries", [])
    if not entries:
        raise HTTPException(400, "No entries")

    # use first PO as the parent (for client/billing/etc.)
    first_po = await db.pos.find_one({"_id": oid(entries[0]["po_id"])})
    if not first_po:
        raise HTTPException(404, "First PO not found")
    parent = stringify(first_po)

    all_items = []
    po_numbers = []
    job_ids_all = []
    for e in entries:
        po_doc = await db.pos.find_one({"_id": oid(e["po_id"])})
        if not po_doc:
            continue
        po_x = stringify(po_doc)
        po_numbers.append(po_x.get("po_number", ""))
        _, lis = await _generate_invoice_payload(po_x, e.get("job_ids"))
        all_items.extend(lis)
        job_ids_all.extend(e.get("job_ids") or [])

    if not all_items:
        raise HTTPException(400, "No line items found across entries")

    invoice_no = await next_invoice_no()
    invoice_date = datetime.now().strftime("%d/%m/%Y")
    # show comma-joined PO numbers in the parent for the meta block
    parent["po_number"] = ", ".join([p for p in po_numbers if p])
    pdf_bytes = build_invoice(
        parent, invoice_no, invoice_date,
        transport_mode=payload.get("transport_mode", ""),
        vehicle_no=payload.get("vehicle_no", ""),
        supply_date=payload.get("supply_date", ""),
        line_items=all_items,
    )
    await db.invoices.insert_one({
        "invoice_no": invoice_no, "invoice_date": invoice_date,
        "merged": True, "po_numbers": po_numbers, "job_ids": job_ids_all,
        "client_name": parent.get("client_name"),
        "line_items_snapshot": all_items,
        "by": u["email"], "created_at": now_iso(),
    })
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice_no}.pdf"'},
    )


@api.get("/pos/{pid}/challan.pdf")
async def po_challan(pid: str, request: Request, dispatch_qty: Optional[int] = None,
                     transporter: str = "", vehicle: str = ""):
    await get_current_user(request)
    doc = await db.pos.find_one({"_id": oid(pid)})
    if not doc:
        raise HTTPException(404, "Not found")
    po = stringify(doc)
    pdf_bytes = generate_dispatch_challan_pdf(po, dispatch_qty=dispatch_qty,
                                              transporter=transporter, vehicle=vehicle)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="challan-{po.get("po_number","po")}.pdf"'},
    )


# ---------- REPORTS ----------
@api.get("/reports/cost-variance")
async def report_cost_variance(request: Request):
    await get_current_user(request)
    styles = await db.styles.find({}).to_list(1000)
    style_costs = {}
    for s in styles:
        s_obj = stringify(s)
        c = compute_style_costing(s_obj)
        style_costs[s["code"]] = {"name": s["name"], "computed_cost": c["total_cost"], "selling_price": c["selling_price"]}
    pos = await db.pos.find({}).to_list(1000)
    rows = []
    for p in pos:
        for li in p.get("line_items", []):
            code = li.get("style_code", "")
            sc = style_costs.get(code, {})
            cost = sc.get("computed_cost", 0)
            sell = li.get("unit_price", 0)
            variance = sell - cost
            margin_pct = (variance / cost * 100) if cost else 0
            rows.append({
                "po_number": p.get("po_number"), "client": p.get("client_name"),
                "style_code": code, "style_name": sc.get("name", "—"),
                "computed_cost": round(cost, 2), "po_unit_price": round(sell, 2),
                "variance": round(variance, 2), "margin_pct": round(margin_pct, 2),
                "quantity": li.get("quantity", 0),
                "total_variance": round(variance * li.get("quantity", 0), 2),
            })
    rows.sort(key=lambda r: r["margin_pct"])
    return rows


@api.get("/reports/stage-cycle-time")
async def report_stage_cycle_time(request: Request):
    await get_current_user(request)
    jobs = await db.production_jobs.find({}).to_list(5000)
    from collections import defaultdict
    durations = defaultdict(list)
    for j in jobs:
        hist = sorted(j.get("history", []), key=lambda h: h.get("at", ""))
        for i in range(1, len(hist)):
            prev, cur = hist[i - 1], hist[i]
            try:
                t_prev = datetime.fromisoformat(prev["at"])
                t_cur = datetime.fromisoformat(cur["at"])
                hours = (t_cur - t_prev).total_seconds() / 3600
                if hours >= 0:
                    durations[(prev["stage"], cur["stage"])].append(hours)
            except Exception:
                continue
    out = []
    for (frm, to), vals in durations.items():
        out.append({
            "from_stage": frm, "to_stage": to, "samples": len(vals),
            "avg_hours": round(sum(vals) / len(vals), 2),
            "min_hours": round(min(vals), 2), "max_hours": round(max(vals), 2),
        })
    out.sort(key=lambda r: r["avg_hours"], reverse=True)
    return out


@api.get("/reports/defect-rate")
async def report_defect_rate(request: Request):
    await get_current_user(request)
    defects = await db.defects.find({}).to_list(2000)
    jobs = await db.production_jobs.find({}).to_list(5000)
    from collections import defaultdict
    stage_qty = defaultdict(int)
    for j in jobs:
        for h in j.get("history", []):
            stage_qty[h.get("stage", "")] += j.get("quantity", 0)
    by_stage = defaultdict(lambda: {"defective": 0, "rework": 0, "rejected": 0, "cost": 0.0, "incidents": 0})
    by_type = defaultdict(lambda: {"defective": 0, "cost": 0.0, "incidents": 0})
    total_defective = 0
    total_cost = 0.0
    for d in defects:
        s = d.get("stage", "unknown")
        by_stage[s]["defective"] += d.get("defective_qty", 0)
        by_stage[s]["rework"] += d.get("rework_qty", 0)
        by_stage[s]["rejected"] += d.get("final_rejection_qty", 0)
        by_stage[s]["cost"] += d.get("cost", 0) or 0
        by_stage[s]["incidents"] += 1
        t = d.get("defect_type", "unknown")
        by_type[t]["defective"] += d.get("defective_qty", 0)
        by_type[t]["cost"] += d.get("cost", 0) or 0
        by_type[t]["incidents"] += 1
        total_defective += d.get("defective_qty", 0)
        total_cost += d.get("cost", 0) or 0
    stages_out = []
    for stage, v in by_stage.items():
        produced = stage_qty.get(stage, 0)
        rate = (v["defective"] / produced * 100) if produced else 0
        stages_out.append({
            "stage": stage, "produced_qty": produced,
            "defective_qty": v["defective"], "rework_qty": v["rework"],
            "rejected_qty": v["rejected"], "cost": round(v["cost"], 2),
            "incidents": v["incidents"], "defect_rate_pct": round(rate, 2),
        })
    stages_out.sort(key=lambda r: r["defect_rate_pct"], reverse=True)
    types_out = [{"type": k, **v, "cost": round(v["cost"], 2)} for k, v in by_type.items()]
    types_out.sort(key=lambda r: r["defective"], reverse=True)
    return {
        "by_stage": stages_out, "by_type": types_out,
        "totals": {"total_defective": total_defective, "total_cost": round(total_cost, 2), "total_incidents": len(defects)},
    }


# ---------- PRODUCTION ----------
@api.get("/production/jobs")
async def list_jobs(request: Request):
    await get_current_user(request)
    docs = await db.production_jobs.find({}).sort("created_at", -1).to_list(2000)
    return [stringify(d) for d in docs]

@api.patch("/production/jobs/{jid}")
async def update_job(jid: str, payload: ProductionStageUpdate, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    job = await db.production_jobs.find_one({"_id": oid(jid)})
    if not job:
        raise HTTPException(404, "Not found")
    update = {"stage": payload.stage, "updated_at": now_iso()}
    if payload.completed_qty is not None:
        update["completed_qty"] = payload.completed_qty
    if payload.rejected_qty is not None:
        update["rejected_qty"] = payload.rejected_qty
    if payload.qc_pass is not None:
        update["qc_pass"] = payload.qc_pass
    history_entry = {
        "stage": payload.stage, "at": now_iso(), "by": u["email"],
        "notes": payload.notes or "",
        "qc_pass": payload.qc_pass, "rejected_qty": payload.rejected_qty,
    }
    await db.production_jobs.update_one(
        {"_id": oid(jid)},
        {"$set": update, "$push": {"history": history_entry}},
    )
    # auto-consume inventory when moving OUT of procurement (first time only)
    if job.get("stage") == "procurement" and payload.stage != "procurement":
        try:
            await _auto_consume_inventory(await db.production_jobs.find_one({"_id": oid(jid)}), u["email"])
        except Exception as e:
            log.warning(f"Auto-consume inventory failed for job {jid}: {e}")
    return stringify(await db.production_jobs.find_one({"_id": oid(jid)}))


@api.patch("/production/jobs/{jid}/components")
async def update_job_components(jid: str, payload: ComponentUpdate, request: Request):
    """Toggle Upper / Bottom / Sole completion per production job."""
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    job = await db.production_jobs.find_one({"_id": oid(jid)})
    if not job:
        raise HTTPException(404, "Not found")
    comps = job.get("components") or {"upper_done": False, "bottom_done": False, "sole_done": False}
    for k in ("upper_done", "bottom_done", "sole_done"):
        v = getattr(payload, k)
        if v is not None:
            comps[k] = bool(v)
    await db.production_jobs.update_one(
        {"_id": oid(jid)},
        {"$set": {"components": comps, "updated_at": now_iso()},
         "$push": {"history": {"event": "component_update", "components": comps,
                               "at": now_iso(), "by": u["email"], "notes": payload.notes or ""}}}
    )
    return stringify(await db.production_jobs.find_one({"_id": oid(jid)}))


@api.patch("/production/jobs/{jid}/assignment")
async def update_job_assignment(jid: str, payload: AssignmentUpdate, request: Request):
    """Assign / reassign a karigar to a particular role on a job with a job-specific rate."""
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    job = await db.production_jobs.find_one({"_id": oid(jid)})
    if not job:
        raise HTTPException(404, "Not found")
    assignments = job.get("assignments") or {}
    if payload.worker_id:
        worker = await db.workers.find_one({"_id": oid(payload.worker_id)})
        if not worker:
            raise HTTPException(404, "Worker not found")
        rate = payload.rate_per_pair if payload.rate_per_pair is not None else worker.get("rate_per_pair", 0)
        assignments[payload.role] = {
            "worker_id": payload.worker_id,
            "worker_name": worker.get("name", ""),
            "rate_per_pair": float(rate or 0),
        }
    else:
        assignments.pop(payload.role, None)
    await db.production_jobs.update_one(
        {"_id": oid(jid)},
        {"$set": {"assignments": assignments, "updated_at": now_iso()},
         "$push": {"history": {"event": "assignment_update", "role": payload.role,
                               "worker_id": payload.worker_id,
                               "worker_name": assignments.get(payload.role, {}).get("worker_name", ""),
                               "rate_per_pair": assignments.get(payload.role, {}).get("rate_per_pair"),
                               "at": now_iso(), "by": u["email"]}}}
    )
    return stringify(await db.production_jobs.find_one({"_id": oid(jid)}))


@api.patch("/production/jobs/{jid}/quantity")
async def update_job_quantity(jid: str, payload: QuantityUpdate, request: Request):
    """Increase, reduce or correct the quantity on a job at any stage."""
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    job = await db.production_jobs.find_one({"_id": oid(jid)})
    if not job:
        raise HTTPException(404, "Not found")
    update = {"updated_at": now_iso()}
    old_qty = job.get("quantity", 0)
    if payload.quantity is not None:
        update["quantity"] = int(payload.quantity)
    if payload.completed_qty is not None:
        update["completed_qty"] = int(payload.completed_qty)
    if payload.rejected_qty is not None:
        update["rejected_qty"] = int(payload.rejected_qty)
    history_entry = {
        "event": "quantity_update", "old_quantity": old_qty,
        "new_quantity": update.get("quantity", old_qty),
        "completed_qty": update.get("completed_qty"),
        "rejected_qty": update.get("rejected_qty"),
        "reason": payload.reason or "",
        "at": now_iso(), "by": u["email"],
    }
    await db.production_jobs.update_one(
        {"_id": oid(jid)}, {"$set": update, "$push": {"history": history_entry}}
    )
    return stringify(await db.production_jobs.find_one({"_id": oid(jid)}))


# ---------- WORKERS / KARIGARS ----------
@api.get("/workers")
async def list_workers(request: Request):
    await get_current_user(request)
    docs = await db.workers.find({}).sort("name", 1).to_list(500)
    return [stringify(d) for d in docs]

@api.post("/workers")
async def create_worker(payload: WorkerIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    doc = payload.model_dump()
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    res = await db.workers.insert_one(doc)
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    return doc

@api.patch("/workers/{wid}")
async def update_worker(wid: str, payload: WorkerIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    update = payload.model_dump()
    update["updated_at"] = now_iso()
    await db.workers.update_one({"_id": oid(wid)}, {"$set": update})
    return stringify(await db.workers.find_one({"_id": oid(wid)}))

@api.delete("/workers/{wid}")
async def delete_worker(wid: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    await db.workers.delete_one({"_id": oid(wid)})
    return {"ok": True}


# ---------- PROCUREMENT MATERIAL REQUIREMENT ----------
async def _compute_material_requirement(job_ids: list[str]) -> dict:
    """Aggregate material requirements across jobs based on their style BOM and yield."""
    obj_ids = []
    for jid in job_ids:
        try:
            obj_ids.append(oid(jid))
        except HTTPException:
            continue
    jobs = await db.production_jobs.find({"_id": {"$in": obj_ids}}).to_list(2000)
    # Pre-load styles for these jobs (by style_code)
    style_codes = list({j.get("style_code") for j in jobs})
    styles = await db.styles.find({"code": {"$in": style_codes}}).to_list(500)
    style_map = {s["code"]: stringify(s) for s in styles}

    # Pre-load all materials (for fresh rate + category info)
    materials = await db.materials.find({}).to_list(2000)
    mat_map = {str(m["_id"]): stringify(m) for m in materials}

    # Aggregate
    requirements = {}  # key = material_id or material_code; value = {code,name,category,unit,rate,total_qty}
    jobs_summary = []
    for j in jobs:
        st = style_map.get(j.get("style_code"))
        pairs = j.get("quantity", 0)
        jobs_summary.append({
            "po_number": j.get("po_number"),
            "style_code": j.get("style_code"),
            "color": j.get("color"),
            "total_pairs": pairs,
            "sizes_text": f"Size {j.get('size','')}",
        })
        if not st or not pairs:
            continue
        for b in st.get("bom", []):
            mid = b.get("material_id") or b.get("material_code")
            code = b.get("material_code") or ""
            name = b.get("material_name") or ""
            unit = b.get("unit") or ""
            rate = float(b.get("rate", 0))
            yld = float(b.get("yield_per_unit", 1) or 1)
            qty = float(b.get("quantity", 0))
            waste = float(b.get("waste_pct", 0) or 0)
            # per pair material in unit terms = qty / yield * (1 + waste%)
            per_pair = (qty / yld) * (1 + waste / 100)
            total_qty = per_pair * pairs
            key = code or mid
            if key not in requirements:
                cat = mat_map.get(str(mid), {}).get("category", b.get("section", "other"))
                requirements[key] = {
                    "code": code, "name": name, "category": cat, "unit": unit,
                    "rate": rate, "total_qty_required": 0.0, "total_cost": 0.0,
                }
            requirements[key]["total_qty_required"] += total_qty
            requirements[key]["total_cost"] += total_qty * rate

    # Round
    material_lines = []
    for v in requirements.values():
        v["total_qty_required"] = round(v["total_qty_required"], 2)
        v["total_cost"] = round(v["total_cost"], 2)
        material_lines.append(v)
    material_lines.sort(key=lambda m: (m["category"], m["code"]))

    # Merge jobs_summary for same (style+color) so summary is one row per card
    merged = {}
    for js in jobs_summary:
        key = (js["po_number"], js["style_code"], js["color"])
        if key not in merged:
            merged[key] = {**js, "sizes_text": "", "_sizes": set()}
        merged[key]["total_pairs"] += 0 if merged[key] is js else js["total_pairs"]
        # nb already counted? Let's just keep simple and aggregate
    # Simpler: aggregate inline
    summary_agg = {}
    for js in jobs_summary:
        key = (js["po_number"], js["style_code"], js["color"])
        if key not in summary_agg:
            summary_agg[key] = {"po_number": js["po_number"], "style_code": js["style_code"],
                                "color": js["color"], "total_pairs": 0, "_sizes": []}
        summary_agg[key]["total_pairs"] += js["total_pairs"]
        sz = js["sizes_text"].replace("Size ", "")
        if sz and sz not in summary_agg[key]["_sizes"]:
            summary_agg[key]["_sizes"].append(sz)
    summary_out = []
    for v in summary_agg.values():
        summary_out.append({
            "po_number": v["po_number"], "style_code": v["style_code"], "color": v["color"],
            "total_pairs": v["total_pairs"],
            "sizes_text": ", ".join(sorted(v["_sizes"], key=lambda x: (float(x) if x.replace('.', '', 1).isdigit() else 999))),
        })
    return {"jobs": summary_out, "materials": material_lines}


@api.post("/procurement/requirement")
async def procurement_requirement(payload: dict, request: Request):
    await get_current_user(request)
    job_ids = payload.get("job_ids", [])
    if not job_ids:
        raise HTTPException(400, "job_ids required")
    return await _compute_material_requirement(job_ids)


@api.post("/procurement/requirement.pdf")
async def procurement_requirement_pdf(payload: dict, request: Request):
    await get_current_user(request)
    job_ids = payload.get("job_ids", [])
    if not job_ids:
        raise HTTPException(400, "job_ids required")
    scope_label = payload.get("scope_label") or f"{len(job_ids)} production card(s)"
    notes = payload.get("notes", "")
    data = await _compute_material_requirement(job_ids)
    pdf_bytes = build_material_requirement(scope_label, data["jobs"], data["materials"], notes)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="material-requirement-{datetime.now().strftime("%Y%m%d-%H%M")}.pdf"'},
    )


# ---------- BULK ASSIGN ----------
@api.post("/production/bulk-assign")
async def bulk_assign(payload: BulkAssign, request: Request):
    """Assign one karigar to multiple jobs at once for a specific role."""
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    if not payload.job_ids:
        raise HTTPException(400, "job_ids required")
    worker_name = ""
    rate = float(payload.rate_per_pair or 0)
    if payload.worker_id:
        w = await db.workers.find_one({"_id": oid(payload.worker_id)})
        if not w:
            raise HTTPException(404, "Worker not found")
        worker_name = w.get("name", "")
        if payload.rate_per_pair is None:
            rate = float(w.get("rate_per_pair", 0) or 0)

    obj_ids = []
    for jid in payload.job_ids:
        try:
            obj_ids.append(oid(jid))
        except HTTPException:
            continue
    jobs = await db.production_jobs.find({"_id": {"$in": obj_ids}}).to_list(2000)
    affected = 0
    for j in jobs:
        assignments = j.get("assignments") or {}
        if payload.worker_id:
            assignments[payload.role] = {
                "worker_id": payload.worker_id, "worker_name": worker_name,
                "rate_per_pair": rate,
            }
        else:
            assignments.pop(payload.role, None)
        await db.production_jobs.update_one(
            {"_id": j["_id"]},
            {"$set": {"assignments": assignments, "updated_at": now_iso()},
             "$push": {"history": {"event": "bulk_assignment", "role": payload.role,
                                   "worker_id": payload.worker_id, "worker_name": worker_name,
                                   "rate_per_pair": rate,
                                   "at": now_iso(), "by": u["email"]}}}
        )
        affected += 1
    return {"affected": affected, "role": payload.role, "worker_id": payload.worker_id, "worker_name": worker_name, "rate_per_pair": rate}


# ---------- INVENTORY ----------
@api.get("/inventory")
async def list_inventory(request: Request):
    """List all materials with computed stock balance."""
    await get_current_user(request)
    materials = await db.materials.find({}).to_list(2000)
    movements = await db.inventory_movements.find({}).to_list(20000)

    # aggregate per material
    bal = {}
    last_in = {}
    for m in movements:
        mid = m.get("material_id")
        if mid not in bal:
            bal[mid] = {"in": 0, "out": 0, "adj": 0, "last_rate": 0, "last_date": ""}
        if m["type"] == "in":
            bal[mid]["in"] += m.get("quantity", 0)
            bal[mid]["last_rate"] = m.get("rate") or bal[mid]["last_rate"]
            bal[mid]["last_date"] = m.get("date") or m.get("created_at", "")
            last_in[mid] = m
        elif m["type"] == "out":
            bal[mid]["out"] += m.get("quantity", 0)
        else:
            bal[mid]["adj"] += m.get("quantity", 0)

    out = []
    for mat in materials:
        mat_id = str(mat["_id"])
        b = bal.get(mat_id, {"in": 0, "out": 0, "adj": 0, "last_rate": 0, "last_date": ""})
        stock = b["in"] - b["out"] + b["adj"]
        out.append({
            "material_id": mat_id,
            "code": mat.get("code"),
            "name": mat.get("name"),
            "category": mat.get("category"),
            "unit": mat.get("unit"),
            "current_rate": mat.get("rate"),
            "last_purchase_rate": b["last_rate"],
            "last_purchase_date": b["last_date"],
            "stock_in": round(b["in"], 2),
            "stock_out": round(b["out"], 2),
            "adjustments": round(b["adj"], 2),
            "balance": round(stock, 2),
            "value": round(stock * (b["last_rate"] or mat.get("rate", 0)), 2),
        })
    out.sort(key=lambda r: (r["category"] or "", r["name"] or ""))
    return out


@api.get("/inventory/movements")
async def list_movements(request: Request, material_id: Optional[str] = None, limit: int = 200):
    await get_current_user(request)
    q = {}
    if material_id:
        q["material_id"] = material_id
    docs = await db.inventory_movements.find(q).sort("created_at", -1).to_list(limit)
    return [stringify(d) for d in docs]


@api.post("/inventory/movements")
async def create_movement(payload: InventoryMovement, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    # validate material exists
    try:
        mat = await db.materials.find_one({"_id": oid(payload.material_id)})
    except HTTPException:
        mat = None
    if not mat:
        raise HTTPException(404, "Material not found")
    doc = payload.model_dump()
    doc["material_code"] = mat.get("code")
    doc["material_name"] = mat.get("name")
    doc["unit"] = mat.get("unit")
    doc["created_at"] = now_iso()
    doc["by"] = u["email"]
    if not doc.get("date"):
        doc["date"] = datetime.now(timezone.utc).date().isoformat()
    res = await db.inventory_movements.insert_one(doc)
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    return doc


@api.delete("/inventory/movements/{mid}")
async def delete_movement(mid: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    await db.inventory_movements.delete_one({"_id": oid(mid)})
    return {"ok": True}


@api.post("/inventory/shortage")
async def inventory_shortage(payload: dict, request: Request):
    """Given job_ids, compute material requirement and compare with current stock to expose shortage."""
    await get_current_user(request)
    job_ids = payload.get("job_ids", [])
    if not job_ids:
        raise HTTPException(400, "job_ids required")
    req = await _compute_material_requirement(job_ids)
    # current stock map
    bal_list = await list_inventory(request)
    bal_map = {(b["code"], b["name"]): b for b in bal_list}
    rows = []
    for m in req["materials"]:
        key = (m["code"], m["name"])
        b = bal_map.get(key, {"balance": 0, "unit": m["unit"]})
        shortage = max(0, m["total_qty_required"] - b.get("balance", 0))
        rows.append({
            "code": m["code"], "name": m["name"], "unit": m["unit"],
            "required": m["total_qty_required"],
            "in_stock": b.get("balance", 0),
            "shortage": round(shortage, 2),
            "purchase_cost_estimated": round(shortage * m["rate"], 2),
        })
    return {"jobs": req["jobs"], "shortage": rows}


# ---------- ADVANCES (worker money taken in advance, deducted from earnings) ----------
@api.get("/advances")
async def list_advances(request: Request, worker_id: Optional[str] = None):
    await get_current_user(request)
    q = {}
    if worker_id:
        q["worker_id"] = worker_id
    docs = await db.advances.find(q).sort("date", -1).to_list(2000)
    return [stringify(d) for d in docs]

@api.post("/advances")
async def create_advance(payload: AdvanceIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    worker = await db.workers.find_one({"_id": oid(payload.worker_id)})
    if not worker:
        raise HTTPException(404, "Worker not found")
    doc = payload.model_dump()
    doc["worker_name"] = worker.get("name", "")
    doc["date"] = doc.get("date") or datetime.now(timezone.utc).date().isoformat()
    doc["settled"] = False
    doc["by"] = u["email"]
    doc["created_at"] = now_iso()
    res = await db.advances.insert_one(doc)
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    return doc

@api.patch("/advances/{aid}")
async def update_advance(aid: str, payload: dict, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    update = {}
    if "settled" in payload:
        update["settled"] = bool(payload["settled"])
        update["settled_at"] = now_iso() if payload["settled"] else None
    if "amount" in payload:
        update["amount"] = float(payload["amount"])
    if "notes" in payload:
        update["notes"] = payload["notes"]
    await db.advances.update_one({"_id": oid(aid)}, {"$set": update})
    return stringify(await db.advances.find_one({"_id": oid(aid)}))

@api.delete("/advances/{aid}")
async def delete_advance(aid: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    await db.advances.delete_one({"_id": oid(aid)})
    return {"ok": True}


# ---------- REPORTS – PAYROLL ----------
@api.get("/reports/payroll")
async def report_payroll(request: Request, from_date: Optional[str] = None, to_date: Optional[str] = None):
    """Per-karigar earnings using JOB-SPECIFIC rate (set during assignment).
    Falls back to worker.rate_per_pair if no job-specific rate captured.
    Subtracts unsettled advances within the period from total earnings → net payable.
    """
    await get_current_user(request)
    workers = await db.workers.find({}).to_list(500)
    worker_map = {str(w["_id"]): w for w in workers}

    q = {}
    if from_date:
        q["updated_at"] = {"$gte": from_date}
    if to_date:
        q.setdefault("updated_at", {})
        q["updated_at"]["$lte"] = to_date + "T23:59:59Z"
    jobs = await db.production_jobs.find(q).to_list(5000)

    earnings = {}
    for j in jobs:
        comp = j.get("completed_qty", 0)
        if not comp and j.get("stage") == "dispatched":
            comp = j.get("quantity", 0)
        if not comp:
            continue
        assigns = j.get("assignments") or {}
        for role, a in assigns.items():
            wid = a.get("worker_id")
            if not wid:
                continue
            w = worker_map.get(wid)
            if not w:
                continue
            # Use job-specific rate if available, else worker default
            rate = float(a.get("rate_per_pair") if a.get("rate_per_pair") is not None
                         else w.get("rate_per_pair", 0) or 0)
            earn = rate * comp
            if wid not in earnings:
                earnings[wid] = {
                    "worker_id": wid, "name": w.get("name", ""), "skill": w.get("skill", ""),
                    "phone": w.get("phone", ""), "default_rate": float(w.get("rate_per_pair", 0) or 0),
                    "total_pairs": 0, "total_earning": 0.0,
                    "advances_taken": 0.0, "advances_open": 0.0,
                    "net_payable": 0.0,
                    "by_role": {}, "jobs": [],
                }
            earnings[wid]["total_pairs"] += comp
            earnings[wid]["total_earning"] += earn
            earnings[wid]["by_role"][role] = earnings[wid]["by_role"].get(role, 0) + comp
            earnings[wid]["jobs"].append({
                "po_number": j.get("po_number"), "style_code": j.get("style_code"),
                "color": j.get("color"), "size": j.get("size"),
                "role": role, "pairs": comp, "rate": rate, "earning": round(earn, 2),
            })

    # Aggregate advances per worker (filter by period if dates given)
    adv_q = {}
    if from_date:
        adv_q["date"] = {"$gte": from_date}
    if to_date:
        adv_q.setdefault("date", {})
        adv_q["date"]["$lte"] = to_date
    advances = await db.advances.find(adv_q).to_list(5000)
    adv_by_worker = {}
    for a in advances:
        wid = a.get("worker_id")
        if not wid:
            continue
        adv_by_worker.setdefault(wid, []).append(a)

    for wid, e in earnings.items():
        for a in adv_by_worker.get(wid, []):
            amt = float(a.get("amount", 0) or 0)
            e["advances_taken"] += amt
            if not a.get("settled"):
                e["advances_open"] += amt
        e["net_payable"] = round(e["total_earning"] - e["advances_open"], 2)
        e["total_earning"] = round(e["total_earning"], 2)
        e["advances_taken"] = round(e["advances_taken"], 2)
        e["advances_open"] = round(e["advances_open"], 2)

    # Also include workers with no earnings but with advances in period
    for wid, advs in adv_by_worker.items():
        if wid in earnings:
            continue
        w = worker_map.get(wid)
        if not w:
            continue
        taken = sum(float(a.get("amount", 0) or 0) for a in advs)
        open_amt = sum(float(a.get("amount", 0) or 0) for a in advs if not a.get("settled"))
        earnings[wid] = {
            "worker_id": wid, "name": w.get("name", ""), "skill": w.get("skill", ""),
            "phone": w.get("phone", ""), "default_rate": float(w.get("rate_per_pair", 0) or 0),
            "total_pairs": 0, "total_earning": 0.0,
            "advances_taken": round(taken, 2), "advances_open": round(open_amt, 2),
            "net_payable": round(-open_amt, 2),
            "by_role": {}, "jobs": [],
        }

    rows = list(earnings.values())
    rows.sort(key=lambda r: r["net_payable"], reverse=True)
    grand = round(sum(r["total_earning"] for r in rows), 2)
    grand_advances = round(sum(r["advances_open"] for r in rows), 2)
    return {
        "rows": rows,
        "grand_total": grand,
        "grand_advances_open": grand_advances,
        "grand_net_payable": round(grand - grand_advances, 2),
        "worker_count": len(rows),
        "from_date": from_date, "to_date": to_date,
    }


@api.get("/reports/payroll.pdf")
async def report_payroll_pdf(request: Request,
                             from_date: Optional[str] = None,
                             to_date: Optional[str] = None):
    """Payroll summary PDF (all karigars in the period)."""
    await get_current_user(request)
    data = await report_payroll(request, from_date, to_date)
    from pdf_payroll import build_payroll_summary
    pdf_bytes = build_payroll_summary(data)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="payroll-{from_date or ""}-{to_date or ""}.pdf"'},
    )


@api.get("/reports/payroll/{worker_id}.pdf")
async def report_wage_slip_pdf(worker_id: str, request: Request,
                               from_date: Optional[str] = None,
                               to_date: Optional[str] = None):
    """Per-karigar wage slip PDF."""
    await get_current_user(request)
    data = await report_payroll(request, from_date, to_date)
    row = next((r for r in data["rows"] if r["worker_id"] == worker_id), None)
    if not row:
        raise HTTPException(404, "No payroll data for this karigar in the period")
    advances = await db.advances.find({"worker_id": worker_id}).sort("date", -1).to_list(500)
    advances_list = [stringify(a) for a in advances]
    from pdf_payroll import build_wage_slip
    pdf_bytes = build_wage_slip(row, advances_list, data["from_date"], data["to_date"])
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="wage-slip-{row["name"].replace(" ", "_")}.pdf"'},
    )


# ---------- AUTO INVENTORY CONSUMPTION (on stage transition) ----------
async def _auto_consume_inventory(job: dict, by_email: str):
    """When a job advances from procurement → cutting, auto-create stock-out movements
    for each BOM material based on job's quantity × yield-adjusted consumption.
    Idempotent: marks job.inventory_consumed=True so we don't double-deduct.
    """
    if job.get("inventory_consumed"):
        return False
    # Lookup style
    style = await db.styles.find_one({"code": job.get("style_code")})
    if not style:
        return False
    style_d = stringify(style)
    pairs = job.get("quantity", 0)
    if not pairs or not style_d.get("bom"):
        return False
    # Build material id lookup by code
    mat_codes = [b.get("material_code") for b in style_d["bom"]]
    materials = await db.materials.find({"code": {"$in": mat_codes}}).to_list(500)
    by_code = {m["code"]: m for m in materials}

    movements = []
    for b in style_d["bom"]:
        rate = float(b.get("rate", 0))
        qty = float(b.get("quantity", 0))
        yld = float(b.get("yield_per_unit", 1) or 1)
        waste = float(b.get("waste_pct", 0) or 0)
        consume = pairs * (qty / yld) * (1 + waste / 100)
        if consume <= 0:
            continue
        mat = by_code.get(b.get("material_code"))
        if not mat:
            continue
        movements.append({
            "material_id": str(mat["_id"]),
            "material_code": mat.get("code"),
            "material_name": mat.get("name"),
            "unit": mat.get("unit"),
            "type": "out",
            "quantity": round(consume, 4),
            "rate": rate,
            "party": f"Job {job.get('po_number','')} · {job.get('style_code','')} · {job.get('color','')} · Sz {job.get('size','')}",
            "job_id": str(job["_id"]),
            "notes": "Auto-consumed when stage moved past Procurement",
            "date": datetime.now(timezone.utc).date().isoformat(),
            "by": by_email,
            "created_at": now_iso(),
            "auto": True,
        })
    if movements:
        await db.inventory_movements.insert_many(movements)
        await db.production_jobs.update_one(
            {"_id": job["_id"]},
            {"$set": {"inventory_consumed": True, "inventory_consumed_at": now_iso()}}
        )
        return True
    return False


@api.get("/inventory/alerts")
async def inventory_alerts(request: Request):
    """List materials whose balance <= reorder_level."""
    await get_current_user(request)
    inv_rows = await list_inventory(request)
    alerts = []
    materials = await db.materials.find({}).to_list(2000)
    rl = {str(m["_id"]): float(m.get("reorder_level", 0) or 0) for m in materials}
    for r in inv_rows:
        threshold = rl.get(r["material_id"], 0)
        if threshold > 0 and r["balance"] <= threshold:
            alerts.append({**r, "reorder_level": threshold, "shortfall": round(threshold - r["balance"], 2)})
    alerts.sort(key=lambda x: x["balance"])
    return alerts





# ---------- DEFECTS ----------
@api.get("/defects")
async def list_defects(request: Request):
    await get_current_user(request)
    docs = await db.defects.find({}).sort("created_at", -1).to_list(2000)
    return [stringify(d) for d in docs]

@api.post("/defects")
async def create_defect(payload: DefectIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    doc = payload.model_dump()
    doc["reported_by"] = u["email"]
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    res = await db.defects.insert_one(doc)
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    return doc

@api.patch("/defects/{did}")
async def update_defect(did: str, payload: DefectIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    update = payload.model_dump()
    update["updated_at"] = now_iso()
    if update["status"] == "closed":
        update["closed_at"] = now_iso()
    await db.defects.update_one({"_id": oid(did)}, {"$set": update})
    return stringify(await db.defects.find_one({"_id": oid(did)}))

@api.delete("/defects/{did}")
async def delete_defect(did: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    await db.defects.delete_one({"_id": oid(did)})
    return {"ok": True}


# ---------- DASHBOARD ----------
@api.get("/dashboard/stats")
async def dashboard_stats(request: Request):
    await get_current_user(request)
    total_pos = await db.pos.count_documents({})
    pending_pos = await db.pos.count_documents({"status": "pending"})
    jobs = await db.production_jobs.find({}).to_list(5000)
    pairs_in_wip = sum(j["quantity"] for j in jobs if j["stage"] != "dispatched")
    dispatched = sum(j["quantity"] for j in jobs if j["stage"] == "dispatched")
    stage_counts = {s: 0 for s in PRODUCTION_STAGES}
    for j in jobs:
        stage_counts[j["stage"]] = stage_counts.get(j["stage"], 0) + j["quantity"]
    revenue = 0.0
    pos = await db.pos.find({}).to_list(2000)
    for p in pos:
        revenue += p.get("grand_total", 0) or 0
    recent_pos = [stringify(p) for p in pos[-5:][::-1]]
    return {
        "total_pos": total_pos,
        "pending_pos": pending_pos,
        "pairs_in_wip": pairs_in_wip,
        "dispatched": dispatched,
        "stage_counts": stage_counts,
        "revenue": round(revenue, 2),
        "recent_pos": recent_pos,
        "materials_count": await db.materials.count_documents({}),
        "styles_count": await db.styles.count_documents({}),
    }


# ---------- SEED DEMO DATA (admin only) ----------
@api.post("/seed/demo")
async def seed_demo(request: Request):
    u = await get_current_user(request); require_roles("admin")(u)
    # only seed if empty
    if await db.materials.count_documents({}) > 0:
        return {"skipped": True, "reason": "Already seeded"}
    demo_materials = [
        ("CNV-001", "Cotton Canvas - Beige", "upper", "sqft", 28.0),
        ("CNV-002", "Cotton Canvas - Wine", "upper", "sqft", 28.0),
        ("LIN-001", "Cotton Lining White", "lining", "sqft", 14.0),
        ("PVC-001", "PVC Sole Brown 8mm", "sole", "pcs", 65.0),
        ("EVA-001", "EVA Cushion 4mm", "sole", "sqft", 22.0),
        ("ADH-001", "Solution Adhesive", "consumable", "gm", 0.35),
        ("ADH-002", "Hardener", "consumable", "gm", 0.45),
        ("THN-001", "Thinner", "consumable", "ml", 0.12),
        ("PRM-001", "Primer EVA", "consumable", "ml", 0.40),
        ("BCK-001", "Metal Buckle", "accessory", "pcs", 8.0),
        ("PKG-001", "Shoe Box - Standard", "packing", "pcs", 12.0),
    ]
    mat_docs = []
    for code, name, cat, unit, rate in demo_materials:
        mat_docs.append({
            "code": code, "name": name, "category": cat, "unit": unit,
            "rate": rate, "notes": "", "created_at": now_iso(), "updated_at": now_iso(),
        })
    await db.materials.insert_many(mat_docs)
    return {"ok": True, "materials_inserted": len(mat_docs)}


# ---------- App wiring ----------
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

@app.on_event("startup")
async def on_startup():
    global get_current_user
    get_current_user = await get_current_user_factory(db)
    await db.users.create_index("email", unique=True)
    await db.materials.create_index("code")
    await db.styles.create_index("code")
    await db.pos.create_index("po_number")
    await db.production_jobs.create_index("po_id")
    await seed_admin(db)
    log.info("Startup complete; admin seeded.")

@app.on_event("shutdown")
async def on_shutdown():
    client.close()
