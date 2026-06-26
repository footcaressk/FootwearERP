# SSK Footcare Manufacturing ERP – PRD

## Original problem statement
> Build a footwear manufacturing management system that replicates the user's Excel master costing sheet, ingests their client POs (PDF/Excel), and tracks the manufacturing process end-to-end. Multi-user, multi-role, cloud-based. Tax per PO. Built to match the user's "B2B Shoe Production Management System" 8-stage workflow.

## User personas
1. **Admin (factory owner)** — manages users, masters, sees everything
2. **Manager** — operations, BOM, costing, POs, production
3. **Production staff** — moves jobs across stages, logs defects
4. **Sales** — creates/views POs, dashboard

## Core requirements (locked)
- Cloud-based, browser-accessible, multi-user with role-based access
- INR currency, GST per PO (CGST/SGST/IGST)
- Replicate master Excel costing sheet (materials + labor + overhead + margin)
- AI ingestion of PO PDF/Excel (Gemini via Emergent LLM key)
- 8-stage production tracking: procurement → cutting → folding → attachment → stitching → lasting → sole_pasting → finishing → dispatched
- Defect & rework tracker

## Implemented (Feb 2026)
- **Auth**: JWT + bcrypt, httpOnly cookies, login/logout/me, 4 roles, admin seed on startup
- **Users**: full CRUD with RBAC (admin-only)
- **Materials Rate Card**: full CRUD, categories (upper/sole/lining/accessory/consumable/packing/other)
- **Style Master**: BOM (multi-section), labor operations, overhead %, packing, margin %, GST %, live cost preview
- **Costing Calculator**: pick style, see full breakdown, override margin/GST to scenario-test
- **Purchase Orders**: manual entry + AI extraction from PDF/Excel (Gemini 2.5 Flash), full tax breakdown, auto-creates production jobs
- **Production Kanban**: 9 columns matching ops sheet, forward/backward stage moves with history audit
- **Defects & QC**: log defects per stage with type/qty/cost/root-cause/corrective action/rework status
- **Dashboard**: KPIs (active POs, WIP pairs, dispatched, revenue), production funnel chart, recent POs

## Tested (iteration 1)
- Backend: 92% (Users 500 bug fixed in retest pass)
- Frontend: 100% — all 8 sidebar pages load, Kanban shows 9 stages, AI extraction successfully parsed Siyaram PO (₹4,91,400, 20 line items)

## Backlog (P1 / P2)
- **P1** – Inventory module (track raw-material stock vs consumption against production jobs)
- **P1** – Per-line-item job assignment to specific operators on the Kanban
- **P1** – PDF invoice/dispatch challan generation for completed POs
- **P2** – Reports: cost variance, stage cycle time, defect rate by stage
- **P2** – Email/SMS notifications on stage completion
- **P2** – Size-wise stock & WIP matrix
- **P2** – Client master (separate from PO free-text) with history

## Tech stack
- Backend: FastAPI + Motor (MongoDB async), JWT auth, Pydantic v2
- AI: emergentintegrations + Gemini 2.5 Flash for PO extraction
- Frontend: React + React Router + Tailwind, Chivo/IBM Plex Sans/JetBrains Mono fonts
- Shadcn UI + lucide-react icons
