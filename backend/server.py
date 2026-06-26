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
    notes: Optional[str] = ""

class BomItem(BaseModel):
    material_id: str
    material_name: str
    material_code: str
    unit: str
    rate: float
    quantity: float
    waste_pct: float = 0
    section: Literal["upper", "sole", "lining", "accessory", "consumable", "packing", "other"] = "other"

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
        raise HTTPException(400, "Email already exists")
    doc = {
        "email": email, "name": payload.name, "role": payload.role,
        "password_hash": hash_password(payload.password),
        "active": True, "created_at": now_iso(),
    }
    res = await db.users.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc.pop("password_hash", None)
    return doc

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
    materials_cost = sum(
        (b["rate"] * b["quantity"] * (1 + (b.get("waste_pct", 0) / 100)))
        for b in style.get("bom", [])
    )
    labor_cost = sum(l["rate"] for l in style.get("labor", []))
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
    return stringify(await db.production_jobs.find_one({"_id": oid(jid)}))


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
