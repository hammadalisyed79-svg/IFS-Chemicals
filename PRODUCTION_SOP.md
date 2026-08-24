# IFS Chemicals — Production SOPs & Operation Sequences

**IFS Industrial ERP V17.3** — Production module standard operating procedures.

Follow these sequences in order unless you use a specialized industrial screen (Spray Dryer, Reactor, etc.) that creates its own batch ticket.

---

## 0. Prerequisites (before any production)

| Step | Screen | Action |
|------|--------|--------|
| 1 | **Masters → Products** | Create **raw materials**, **packaging**, and **finished goods** with codes, units, purchase/sale prices |
| 2 | **Masters → Warehouses** | Ensure **Main Warehouse** (or production WH) exists |
| 3 | **Production → Machines** | Register lines: spray dryer, reactor, gravure, PET, corrugated |
| 4 | **Inventory → Stock** | Receive RM via **GRN / Purchase Invoice** so stock is available |
| 5 | **Production → BOM** | Create and **Approve** composition for each FG |
| 6 | **Production → Formula Master** | (Optional) Pilot/commercial formulas with % composition for chemicals/detergent |

---

## 1. Master production flow (generic)

Use this for standard batch manufacturing linked to BOM and stock.

```
BOM Draft → BOM Approved → Production Order Draft → Issue Materials
→ Complete + QC → FG in Stock → QC Lab COA → Cost Roll-up / Reports
```

| Seq | Screen | Tab | Operation | ERP result |
|-----|--------|-----|-----------|------------|
| 1 | **BOM** | New Composition | Enter FG, type, version, components → **Save** | Status: `draft` |
| 2 | **BOM** | Edit / Approve | **Approve Composition** | Status: `approved` — usable on PO |
| 3 | **Production Orders** | New Order | Select approved BOM, planned qty, batch no, WH, machine → **Create** | Status: `draft` |
| 4 | **Production Orders** | Issue / Complete | **Issue Materials to Production** | RM ↓ stock, WIP issued |
| 5 | **Production Orders** | Issue / Complete | Enter actual qty, wastage, QC → **Complete & Receive FG** | FG ↑ stock, status `completed` |
| 6 | **QC Laboratory** | New Inspection | In-process / FG inspection → **Record Results** → **Approve COA** | QC on batch |
| 7 | **Industrial Costing** | — | Review variance after batches complete | Material/labour/utility roll-up |
| 8 | **Industrial Reports** | — | Production Register, Yield Analysis | Audit evidence |

**Rollback:** Production Orders → Issue / Complete → **Rollback & Reopen** (reverses FG + re-issues RM to stock) → fix on **Edit Draft** → re-issue.

---

## 2. BOM / Composition — SOP

**Purpose:** Approved recipe for detergent, liquid, corrugated, gravure, etc.

**Composition types in system:**

- Detergent Powder (dry mix / spray dry)
- Liquid Detergent (blending / filling)
- Dishwash Bar (extrusion / stamping)
- Dishwash Liquid (blending / filling)
- Corrugated Box (board / conversion)
- Flexible Wrapper / Gravure Printing
- Other / General Assembly

### SOP — Create new BOM

1. **Production → BOM → New Composition**
2. Enter composition code, date, **composition type**, finished product
3. Set version (auto-suggested), standard output qty
4. Add process notes (mixing time, GSM, colours, fill volume)
5. **Continue to Components** → add RM lines (qty, wastage %, rate)
6. **Save Composition** (draft)

### SOP — Approve for production

1. **Edit / Approve** tab → select composition
2. Verify components and standard cost
3. **Approve Composition** — only approved BOMs appear on Production Orders

### Operation sequence

```
Draft → Review → Approve → (optional) Copy to New Version
```

---

## 3. Formula Master — SOP

**Purpose:** Chemical/detergent formulas with revision control (pilot / commercial / production).

| Seq | Tab | Steps |
|-----|-----|-------|
| 1 | **New / Edit** | Formula code, name, type, finished product, batch qty, tolerance % |
| 2 | | Add RM lines (% composition, max 5 lines) |
| 3 | | **Save Formula** |
| 4 | **Register** | Verify formula_code, revision, status, total_cost |

**Link to production:** Spray Dryer and batch tickets can reference `formula_id`. Ensure FG product matches BOM.

---

## 4. Production Orders — SOP

**Purpose:** Official batch order — issue RM, receive FG, post to inventory.

### SOP — New batch

1. **New Order** → select **approved** composition
2. Planned qty (scales BOM requirements), production date, **batch no**
3. Warehouse, machine/line, optional conversion costs (labour, utility, packing, overhead)
4. **Create Production Order**

### SOP — Execute batch

1. **Issue / Complete** → select order (`draft`)
2. Review material requirements (incl. wastage)
3. If short stock: confirm issue or fix stock first
4. **Issue Materials to Production** → status `issued`
5. Enter **Actual Output Qty**, **Process Wastage**, **QC Status**
6. **Complete Production & Receive FG** → status `completed`

---

## 5. Job Cards — SOP

**Purpose:** Shop-floor consumption document for **Gravure/Wrapper** and **Corrugated** (actual use vs BOM).

**Job types:** Gravure/Wrapper (`JCG`), Corrugated Box (`JCC`)

### SOP

| Seq | Tab | Action |
|-----|-----|--------|
| 1 | **New Job Card** | Select job type, date, warehouse |
| 2 | | **Produced item** + production qty |
| 3 | | **Load from BOM** (optional) — pulls approved BOM lines |
| 4 | | Adjust material lines (product, qty, rate) |
| 5 | | **Save draft** OR **Save & Post** |
| 6 | **Register & Print** | Find card → **Post** (if draft) → **Print** |

**Post effect:** Consumes RM from stock, records production output (BOM-style posting).

---

## 6. Spray Dryer — SOP (Detergent powder)

**Stages (in order):**

1. Raw material charging
2. Slurry preparation
3. Slurry tank
4. Homogenization
5. Spray drying
6. Bulk collection
7. Sieving
8. Post dosing
9. Perfume addition
10. Packing

### Operation sequence

| Seq | Tab | Action |
|-----|-----|--------|
| 1 | **New Batch** | Batch no, planned qty, shift, **recipe (formula)**, slurry tank, machine → **Start** |
| 2 | **Process** | Select active batch |
| 3 | | **Advance Stage** through each stage |
| 4 | | **Log Temperature** (hot air °C, outlet °C) each drying cycle |
| 5 | | **Record Utilities** (steam kg, gas m³, electricity kWh) |
| 6 | | **Issue Materials** (links to batch ticket / production order) |
| 7 | | Enter yield, moisture %, bulk density, production loss |
| 8 | | **Complete & Receive FG** |

---

## 7. Batch Manufacturing — SOP

**Purpose:** Central batch ticket for all process types.

**Process types:** spray_dryer, dishwash_bar, liquid_detergent, toilet_cleaner, industrial_chemical, corrugated, gravure, flexible_packaging, pet_blowing, toll, reactor

| Seq | Action |
|-----|--------|
| 1 | **New Ticket** → batch no, process type, planned qty |
| 2 | Ticket appears in **Register** (ticket_no, yield, QC status) |
| 3 | Use specialized screen (Spray Dryer, Reactor, etc.) OR Production Orders for issue/complete |
| 4 | **Issue Materials** / **Complete Batch** via batch service ties to production order + inventory |

---

## 8. Chemical Reactor — SOP

**Stages:** mixing → heating → cooling → reaction → agitation → transfer → holding → packing

| Seq | Tab | Action |
|-----|-----|--------|
| 1 | **New Batch** | Batch no, reactor code, planned qty (L) → **Start** |
| 2 | **Register** | Monitor batch status |
| 3 | (Process tab on related batch ticket) | Advance stages, complete with yield/QC |

---

## 9. Corrugated Production — SOP

| Seq | Tab | Action |
|-----|-----|--------|
| 1 | **New Run** | Batch no, paper GSM, flute type (A/B/C/E/BC), board size, planned sheets |
| 2 | **Start Run** | Creates corrugated batch run |
| 3 | **Register** | Track run status |
| 4 | **Job Cards** (type: Corrugated) | Record actual paper consumption + boxes produced → **Post** |

---

## 10. Gravure / Packaging — SOP

| Seq | Tab | Action |
|-----|-----|--------|
| 1 | **Cylinders** | Register cylinder code, artwork revision, repeat length |
| 2 | **New Run** | Batch no, cylinder, film micron, planned kg, type (gravure / flexible_packaging) |
| 3 | **Start Run** | |
| 4 | **Job Cards** (type: Gravure) | Ink/film consumption + output → **Post** |

---

## 11. PET Bottle Blowing — SOP

| Seq | Tab | Action |
|-----|-----|--------|
| 1 | **New Run** | Batch no, preform product, bottle weight (g), cavities, planned pcs |
| 2 | **Start Run** | |
| 3 | Complete via batch ticket / production order when FG bottles ready |

---

## 12. QC Laboratory — SOP

| Seq | Tab | Action |
|-----|-----|--------|
| 1 | **Specifications** | Review incoming / in-process / FG specs |
| 2 | **New Inspection** | Type, link **batch ticket** → **Create Inspection** |
| 3 | | Enter measured values per parameter |
| 4 | | **Record Results** → pass/fail |
| 5 | | **Approve COA** for release |

**Gate:** Do not ship FG until COA approved (in-process QC on Production Order should be **Passed**).

---

## 13. Plant Maintenance — SOP

| Seq | Tab | Action |
|-----|-----|--------|
| 1 | **PM Schedules** | Machine, type (preventive/lubrication), frequency (days) |
| 2 | **Breakdown** | Report machine, cause → breakdown ticket |
| 3 | **Analysis** | Review downtime / MTBF metrics |

**Rule:** Log breakdown before running production on faulty equipment.

---

## 14. Energy Management — SOP

| Seq | Tab | Action |
|-----|-----|--------|
| 1 | **Record Reading** | Utility (steam/gas/electricity/diesel/compressed air/water), qty, UOM |
| 2 | | Link to **batch ticket** (optional) for batch costing |
| 3 | **Summary** | Review consumption by utility |

**Spray Dryer:** Also record utilities on Process tab during drying.

---

## 15. Industrial Costing — SOP

1. Complete production batches (material issue + FG receipt)
2. **Industrial Costing** → variance report (material, labour, utility, overhead)
3. Investigate negative yield or high variance in **Industrial Reports → Yield Analysis**

---

## 16. Toll Manufacturing — SOP

| Seq | Tab | Action |
|-----|-----|--------|
| 1 | **Agreements** | Customer, manufacturing charge/kg → **Save Agreement** |
| 2 | **Production** | Select active agreement, batch no, planned qty → **Start Toll Production** |
| 3 | | Customer RM/packaging handled per agreement; QC + billing per toll workflow |
| 4 | **Industrial Warehouse** | FG segregation if required |

---

## 17. Industrial Warehouse — SOP

| Seq | Tab | Action |
|-----|-----|--------|
| 1 | **Zones** | Verify RM / WIP / FG / rejected / scrap zones |
| 2 | **Transfer** | Inter-warehouse moves (FIFO/FEFO enforced) |
| 3 | **Traceability** | Enter batch no → full trace chain |

---

## 18. Industrial Dashboards & Reports

**Dashboards:** CEO, Plant, Production, Quality, Maintenance, Energy, Warehouse, Costing — daily management review.

**Reports (operation sequence for month-end):**

1. Production Register
2. Daily Production (by date)
3. Machine Utilization
4. Yield Analysis
5. Utility Consumption
6. Maintenance report

---

## 19. Recommended daily sequence (IFS Chemicals plant)

| Time | Activity | Screens |
|------|----------|---------|
| Start of shift | Review open batches, machine PM | Dashboards, Plant Maintenance |
| Planning | Confirm BOM/formula for today's SKUs | BOM, Formula Master |
| Batch start | Create PO or industrial batch | Production Orders OR Spray Dryer/Reactor/etc. |
| During run | Stage advance, temps, utilities, energy | Process tabs, Energy Management |
| End of batch | Issue (if not done), complete, QC | Production Orders, QC Laboratory |
| Packaging lines | Job cards for gravure/corrugated | Job Cards → Post |
| End of shift | Stock check, reports, costing | Industrial Warehouse, Industrial Reports |

---

## Quick reference — which screen for which plant?

| Plant area | Primary screens |
|------------|-----------------|
| Detergent powder | Formula Master → Spray Dryer → QC → Costing |
| Liquid / reactor | Formula Master → Chemical Reactor → Batch Mfg → QC |
| Corrugated | Corrugated Production → Job Cards (Corrugated) |
| Gravure / flexo | Gravure (Cylinders + Run) → Job Cards (Gravure) |
| PET bottles | PET Bottle Blowing → Production Orders |
| Generic / multi-SKU | BOM → Production Orders → QC |
| Toll / CM | Toll Manufacturing → Industrial Warehouse |

---

*Generated for IFS Industrial ERP V17.3 — evidence-based on `erp_ui/production_pages.py`, `erp_ui/industrial_pages.py`, `erp_ui/job_card_pages.py`, and `application/manufacturing/`.*
