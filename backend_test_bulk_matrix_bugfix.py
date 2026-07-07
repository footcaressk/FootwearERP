#!/usr/bin/env python3
"""
Backend test for POST /api/components/bulk-matrix bug fix.

BUG (before fix): When a (component_code, color, size) already existed in component_master,
the endpoint caught DuplicateKeyError and silently skipped — including any opening_qty the
user had typed. Result: user's typed quantities in "extend mode" of the Add-Stock-in-Bulk
drawer were completely dropped, and the component's stock never went up.

FIX applied: In the DuplicateKeyError branch, if opening_qty > 0 we now look up the existing
row and record a `purchase_in` movement (reference_type='bulk_matrix_topup') via
_record_component_movement(). A new `updated` counter tracks these, and `results[]` gets
status='stock_added' with `qty`. Return body now has {created, updated, skipped, results}.
Existing rows with opening_qty=0 still return status='exists' and are counted in `skipped`
(true no-op).
"""

import requests
import time
import sys
from typing import Dict, Any

# Configuration
BASE_URL = "https://footwear-hub-565.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"

# Use unique component_code for this test run to avoid state from earlier tests
TIMESTAMP = int(time.time())
COMPONENT_CODE = f"BugFixGinger_{TIMESTAMP}"

# Test state
access_token = None
test_results = []


def log_test(test_name: str, passed: bool, details: str = ""):
    """Log test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"\n{status}: {test_name}")
    if details:
        print(f"  Details: {details}")
    test_results.append({
        "test": test_name,
        "passed": passed,
        "details": details
    })


def login() -> str:
    """Login and return access token."""
    global access_token
    print(f"\n{'='*80}")
    print("SETUP: Logging in as admin...")
    print(f"{'='*80}")
    
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    
    if response.status_code != 200:
        print(f"❌ Login failed: {response.status_code} - {response.text}")
        sys.exit(1)
    
    data = response.json()
    access_token = data.get("access_token")
    
    if not access_token:
        print(f"❌ No access_token in response: {data}")
        sys.exit(1)
    
    print(f"✅ Login successful. Token: {access_token[:20]}...")
    return access_token


def get_headers() -> Dict[str, str]:
    """Get authorization headers."""
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }


def setup_fixture():
    """
    SETUP: Create the fixture component with 2 rows at 0 stock.
    POST /api/components/bulk-matrix
    body: {
        "component_code": <code>,
        "component_name": "Ginger Test",
        "component_category": "Insole",
        "vendor": "",
        "unit": "pair",
        "reorder_level": 0,
        "minimum_stock": 5,
        "lead_time_days": 0,
        "rows": [
            {"color": "Silver", "size": "36", "opening_qty": 0},
            {"color": "Silver", "size": "37", "opening_qty": 0}
        ]
    }
    EXPECT: 200 with created==2, updated==0, skipped==0
    """
    print(f"\n{'='*80}")
    print(f"SETUP: Creating fixture component '{COMPONENT_CODE}'")
    print(f"{'='*80}")
    
    payload = {
        "component_code": COMPONENT_CODE,
        "component_name": "Ginger Test",
        "component_category": "Insole",
        "vendor": "",
        "unit": "pair",
        "reorder_level": 0,
        "minimum_stock": 5,
        "lead_time_days": 0,
        "rows": [
            {"color": "Silver", "size": "36", "opening_qty": 0},
            {"color": "Silver", "size": "37", "opening_qty": 0}
        ]
    }
    
    response = requests.post(
        f"{BASE_URL}/components/bulk-matrix",
        headers=get_headers(),
        json=payload
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    if response.status_code != 200:
        print(f"❌ Setup failed: {response.status_code} - {response.text}")
        sys.exit(1)
    
    data = response.json()
    
    # Verify response structure
    assert data.get("created") == 2, f"Expected created==2, got {data.get('created')}"
    assert data.get("updated") == 0, f"Expected updated==0, got {data.get('updated')}"
    assert data.get("skipped") == 0, f"Expected skipped==0, got {data.get('skipped')}"
    assert len(data.get("results", [])) == 2, f"Expected 2 results, got {len(data.get('results', []))}"
    
    # Verify both results have status='created' with qty:0
    for result in data["results"]:
        assert result["status"] == "created", f"Expected status='created', got {result['status']}"
        assert result["qty"] == 0, f"Expected qty=0, got {result['qty']}"
    
    print(f"✅ Fixture created successfully")
    
    # Verify GET /api/components?code=<code> returns 2 rows with current_stock==0
    response = requests.get(
        f"{BASE_URL}/components",
        headers=get_headers(),
        params={"code": COMPONENT_CODE}
    )
    
    if response.status_code != 200:
        print(f"❌ GET components failed: {response.status_code} - {response.text}")
        sys.exit(1)
    
    rows = response.json()
    assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}"
    
    for row in rows:
        assert row["current_stock"] == 0, f"Expected current_stock==0, got {row['current_stock']}"
    
    print(f"✅ Verified: 2 rows exist with current_stock==0")


def test_1_bug_fix_extend_mode_stock_topup():
    """
    TEST 1 — THE BUG FIX (extend-mode stock top-up):
    POST /api/components/bulk-matrix same code/meta, rows:[
        {"color":"Silver","size":"36","opening_qty":20},
        {"color":"Silver","size":"37","opening_qty":15}
    ]
    EXPECT 200 with:
      - response.created == 0
      - response.updated == 2   (NEW field — was missing before fix)
      - response.skipped == 0
      - response.results is a list of 2 with status=="stock_added", qty in [20,15]
    
    GET /api/components?code=<code>&color=Silver — verify:
      - Silver/36 row has current_stock == 20 (was 0)
      - Silver/37 row has current_stock == 15 (was 0)
    
    GET /api/components/movements?component_code=<code> — 2 new ledger entries:
      - movement_type=='purchase_in'
      - reference_type=='bulk_matrix_topup'
      - quantity 20 and 15 respectively
      - current_delta +20 and +15
      - current_before/current_after correctly show 0→20 and 0→15
    """
    print(f"\n{'='*80}")
    print("TEST 1: THE BUG FIX (extend-mode stock top-up)")
    print(f"{'='*80}")
    
    payload = {
        "component_code": COMPONENT_CODE,
        "component_name": "Ginger Test",
        "component_category": "Insole",
        "vendor": "",
        "unit": "pair",
        "reorder_level": 0,
        "minimum_stock": 5,
        "lead_time_days": 0,
        "rows": [
            {"color": "Silver", "size": "36", "opening_qty": 20},
            {"color": "Silver", "size": "37", "opening_qty": 15}
        ]
    }
    
    response = requests.post(
        f"{BASE_URL}/components/bulk-matrix",
        headers=get_headers(),
        json=payload
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    if response.status_code != 200:
        log_test("TEST 1 - POST bulk-matrix", False, f"Status {response.status_code}: {response.text}")
        return
    
    data = response.json()
    
    # Verify response structure
    checks = []
    checks.append(("created == 0", data.get("created") == 0))
    checks.append(("updated == 2", data.get("updated") == 2))
    checks.append(("skipped == 0", data.get("skipped") == 0))
    checks.append(("results length == 2", len(data.get("results", [])) == 2))
    
    # Verify results
    results = data.get("results", [])
    if len(results) == 2:
        checks.append(("result[0] status == 'stock_added'", results[0].get("status") == "stock_added"))
        checks.append(("result[0] qty == 20", results[0].get("qty") == 20))
        checks.append(("result[1] status == 'stock_added'", results[1].get("status") == "stock_added"))
        checks.append(("result[1] qty == 15", results[1].get("qty") == 15))
    
    all_passed = all(check[1] for check in checks)
    details = "\n    ".join([f"{check[0]}: {'✓' if check[1] else '✗'}" for check in checks])
    
    if not all_passed:
        log_test("TEST 1 - POST bulk-matrix response", False, details)
        return
    
    log_test("TEST 1 - POST bulk-matrix response", True, details)
    
    # Verify GET /api/components?code=<code>&color=Silver
    response = requests.get(
        f"{BASE_URL}/components",
        headers=get_headers(),
        params={"code": COMPONENT_CODE, "color": "Silver"}
    )
    
    if response.status_code != 200:
        log_test("TEST 1 - GET components", False, f"Status {response.status_code}: {response.text}")
        return
    
    rows = response.json()
    
    # Find Silver/36 and Silver/37 rows
    row_36 = next((r for r in rows if r["size"] == "36"), None)
    row_37 = next((r for r in rows if r["size"] == "37"), None)
    
    checks = []
    checks.append(("Silver/36 exists", row_36 is not None))
    checks.append(("Silver/37 exists", row_37 is not None))
    
    if row_36:
        checks.append(("Silver/36 current_stock == 20", row_36["current_stock"] == 20))
    if row_37:
        checks.append(("Silver/37 current_stock == 15", row_37["current_stock"] == 15))
    
    all_passed = all(check[1] for check in checks)
    details = "\n    ".join([f"{check[0]}: {'✓' if check[1] else '✗'}" for check in checks])
    
    if not all_passed:
        log_test("TEST 1 - GET components verification", False, details)
        return
    
    log_test("TEST 1 - GET components verification", True, details)
    
    # Verify GET /api/components/movements
    # Note: The endpoint doesn't support component_code filter directly, so we'll filter client-side
    response = requests.get(
        f"{BASE_URL}/components/movements",
        headers=get_headers(),
        params={"limit": 500}
    )
    
    if response.status_code != 200:
        log_test("TEST 1 - GET movements", False, f"Status {response.status_code}: {response.text}")
        return
    
    movements = response.json()
    
    # Filter by component_code
    relevant_movements = [m for m in movements if m.get("component_code") == COMPONENT_CODE]
    
    # Filter by reference_type='bulk_matrix_topup'
    topup_movements = [m for m in relevant_movements if m.get("reference_type") == "bulk_matrix_topup"]
    
    checks = []
    checks.append(("2 bulk_matrix_topup movements", len(topup_movements) == 2))
    
    if len(topup_movements) == 2:
        # Sort by quantity to get consistent ordering
        topup_movements.sort(key=lambda m: m.get("quantity", 0), reverse=True)
        
        mov_20 = topup_movements[0]
        mov_15 = topup_movements[1]
        
        checks.append(("movement[0] movement_type == 'purchase_in'", mov_20.get("movement_type") == "purchase_in"))
        checks.append(("movement[0] quantity == 20", mov_20.get("quantity") == 20))
        checks.append(("movement[0] current_delta == 20", mov_20.get("current_delta") == 20))
        checks.append(("movement[0] current_before == 0", mov_20.get("current_before") == 0))
        checks.append(("movement[0] current_after == 20", mov_20.get("current_after") == 20))
        
        checks.append(("movement[1] movement_type == 'purchase_in'", mov_15.get("movement_type") == "purchase_in"))
        checks.append(("movement[1] quantity == 15", mov_15.get("quantity") == 15))
        checks.append(("movement[1] current_delta == 15", mov_15.get("current_delta") == 15))
        checks.append(("movement[1] current_before == 0", mov_15.get("current_before") == 0))
        checks.append(("movement[1] current_after == 15", mov_15.get("current_after") == 15))
    
    all_passed = all(check[1] for check in checks)
    details = "\n    ".join([f"{check[0]}: {'✓' if check[1] else '✗'}" for check in checks])
    
    log_test("TEST 1 - GET movements verification", all_passed, details)


def test_2_mixed_batch():
    """
    TEST 2 — MIXED BATCH (some new, some existing):
    POST /api/components/bulk-matrix rows:[
        {"color":"Silver","size":"36","opening_qty":5},
        {"color":"Gold","size":"42","opening_qty":10}
    ]
    EXPECT 200 with:
      - response.created == 1   (Gold/42 is new)
      - response.updated == 1   (Silver/36 topped up)
      - response.skipped == 0
      - results contains one status='stock_added' (Silver/36, qty 5) and one status='created' (Gold/42, qty 10)
    
    GET /api/components?code=<code> — verify:
      - Silver/36 current_stock now 25 (was 20 + 5)
      - Silver/37 current_stock still 15 (untouched)
      - Gold/42 row exists with current_stock == 10
    """
    print(f"\n{'='*80}")
    print("TEST 2: MIXED BATCH (some new, some existing)")
    print(f"{'='*80}")
    
    payload = {
        "component_code": COMPONENT_CODE,
        "component_name": "Ginger Test",
        "component_category": "Insole",
        "vendor": "",
        "unit": "pair",
        "reorder_level": 0,
        "minimum_stock": 5,
        "lead_time_days": 0,
        "rows": [
            {"color": "Silver", "size": "36", "opening_qty": 5},
            {"color": "Gold", "size": "42", "opening_qty": 10}
        ]
    }
    
    response = requests.post(
        f"{BASE_URL}/components/bulk-matrix",
        headers=get_headers(),
        json=payload
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    if response.status_code != 200:
        log_test("TEST 2 - POST bulk-matrix", False, f"Status {response.status_code}: {response.text}")
        return
    
    data = response.json()
    
    # Verify response structure
    checks = []
    checks.append(("created == 1", data.get("created") == 1))
    checks.append(("updated == 1", data.get("updated") == 1))
    checks.append(("skipped == 0", data.get("skipped") == 0))
    checks.append(("results length == 2", len(data.get("results", [])) == 2))
    
    # Verify results
    results = data.get("results", [])
    if len(results) == 2:
        # Find stock_added and created results
        stock_added = next((r for r in results if r.get("status") == "stock_added"), None)
        created = next((r for r in results if r.get("status") == "created"), None)
        
        checks.append(("one result with status='stock_added'", stock_added is not None))
        checks.append(("one result with status='created'", created is not None))
        
        if stock_added:
            checks.append(("stock_added color='Silver', size='36'", 
                          stock_added.get("color") == "Silver" and stock_added.get("size") == "36"))
            checks.append(("stock_added qty=5", stock_added.get("qty") == 5))
        
        if created:
            checks.append(("created color='Gold', size='42'", 
                          created.get("color") == "Gold" and created.get("size") == "42"))
            checks.append(("created qty=10", created.get("qty") == 10))
    
    all_passed = all(check[1] for check in checks)
    details = "\n    ".join([f"{check[0]}: {'✓' if check[1] else '✗'}" for check in checks])
    
    if not all_passed:
        log_test("TEST 2 - POST bulk-matrix response", False, details)
        return
    
    log_test("TEST 2 - POST bulk-matrix response", True, details)
    
    # Verify GET /api/components?code=<code>
    response = requests.get(
        f"{BASE_URL}/components",
        headers=get_headers(),
        params={"code": COMPONENT_CODE}
    )
    
    if response.status_code != 200:
        log_test("TEST 2 - GET components", False, f"Status {response.status_code}: {response.text}")
        return
    
    rows = response.json()
    
    # Find rows
    row_silver_36 = next((r for r in rows if r["color"] == "Silver" and r["size"] == "36"), None)
    row_silver_37 = next((r for r in rows if r["color"] == "Silver" and r["size"] == "37"), None)
    row_gold_42 = next((r for r in rows if r["color"] == "Gold" and r["size"] == "42"), None)
    
    checks = []
    checks.append(("Silver/36 exists", row_silver_36 is not None))
    checks.append(("Silver/37 exists", row_silver_37 is not None))
    checks.append(("Gold/42 exists", row_gold_42 is not None))
    
    if row_silver_36:
        checks.append(("Silver/36 current_stock == 25", row_silver_36["current_stock"] == 25))
    if row_silver_37:
        checks.append(("Silver/37 current_stock == 15", row_silver_37["current_stock"] == 15))
    if row_gold_42:
        checks.append(("Gold/42 current_stock == 10", row_gold_42["current_stock"] == 10))
    
    all_passed = all(check[1] for check in checks)
    details = "\n    ".join([f"{check[0]}: {'✓' if check[1] else '✗'}" for check in checks])
    
    log_test("TEST 2 - GET components verification", all_passed, details)


def test_3_existing_row_zero_qty():
    """
    TEST 3 — EXISTING ROW WITH ZERO QTY (true no-op):
    POST /api/components/bulk-matrix rows:[{"color":"Silver","size":"36","opening_qty":0}]
    EXPECT 200 with created==0, updated==0, skipped==1, one result status='exists'.
    GET the row — current_stock STILL 25 (unchanged). No new movement in the ledger.
    """
    print(f"\n{'='*80}")
    print("TEST 3: EXISTING ROW WITH ZERO QTY (true no-op)")
    print(f"{'='*80}")
    
    # Get current movement count before test
    response = requests.get(
        f"{BASE_URL}/components/movements",
        headers=get_headers(),
        params={"limit": 500}
    )
    movements_before = [m for m in response.json() if m.get("component_code") == COMPONENT_CODE]
    movement_count_before = len(movements_before)
    
    payload = {
        "component_code": COMPONENT_CODE,
        "component_name": "Ginger Test",
        "component_category": "Insole",
        "vendor": "",
        "unit": "pair",
        "reorder_level": 0,
        "minimum_stock": 5,
        "lead_time_days": 0,
        "rows": [
            {"color": "Silver", "size": "36", "opening_qty": 0}
        ]
    }
    
    response = requests.post(
        f"{BASE_URL}/components/bulk-matrix",
        headers=get_headers(),
        json=payload
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    if response.status_code != 200:
        log_test("TEST 3 - POST bulk-matrix", False, f"Status {response.status_code}: {response.text}")
        return
    
    data = response.json()
    
    # Verify response structure
    checks = []
    checks.append(("created == 0", data.get("created") == 0))
    checks.append(("updated == 0", data.get("updated") == 0))
    checks.append(("skipped == 1", data.get("skipped") == 1))
    checks.append(("results length == 1", len(data.get("results", [])) == 1))
    
    results = data.get("results", [])
    if len(results) == 1:
        checks.append(("result[0] status == 'exists'", results[0].get("status") == "exists"))
    
    all_passed = all(check[1] for check in checks)
    details = "\n    ".join([f"{check[0]}: {'✓' if check[1] else '✗'}" for check in checks])
    
    if not all_passed:
        log_test("TEST 3 - POST bulk-matrix response", False, details)
        return
    
    log_test("TEST 3 - POST bulk-matrix response", True, details)
    
    # Verify GET /api/components - current_stock should still be 25
    response = requests.get(
        f"{BASE_URL}/components",
        headers=get_headers(),
        params={"code": COMPONENT_CODE, "color": "Silver", "size": "36"}
    )
    
    if response.status_code != 200:
        log_test("TEST 3 - GET components", False, f"Status {response.status_code}: {response.text}")
        return
    
    rows = response.json()
    
    checks = []
    checks.append(("1 row returned", len(rows) == 1))
    
    if len(rows) == 1:
        checks.append(("current_stock == 25", rows[0]["current_stock"] == 25))
    
    all_passed = all(check[1] for check in checks)
    details = "\n    ".join([f"{check[0]}: {'✓' if check[1] else '✗'}" for check in checks])
    
    if not all_passed:
        log_test("TEST 3 - GET components verification", False, details)
        return
    
    log_test("TEST 3 - GET components verification", True, details)
    
    # Verify no new movement in ledger
    response = requests.get(
        f"{BASE_URL}/components/movements",
        headers=get_headers(),
        params={"limit": 500}
    )
    
    movements_after = [m for m in response.json() if m.get("component_code") == COMPONENT_CODE]
    movement_count_after = len(movements_after)
    
    checks = []
    checks.append(("no new movements", movement_count_after == movement_count_before))
    
    all_passed = all(check[1] for check in checks)
    details = "\n    ".join([f"{check[0]}: {'✓' if check[1] else '✗'}" for check in checks])
    
    log_test("TEST 3 - No new ledger entry", all_passed, details)


def test_4_negative_qty_guard():
    """
    TEST 4 — NEGATIVE QTY GUARD:
    POST /api/components/bulk-matrix rows:[{"color":"Silver","size":"36","opening_qty":-5}]
    EXPECT 200 with results containing status='invalid_qty' for that row. 
    current_stock still 25. No new ledger entry with quantity=-5.
    """
    print(f"\n{'='*80}")
    print("TEST 4: NEGATIVE QTY GUARD")
    print(f"{'='*80}")
    
    # Get current movement count before test
    response = requests.get(
        f"{BASE_URL}/components/movements",
        headers=get_headers(),
        params={"limit": 500}
    )
    movements_before = [m for m in response.json() if m.get("component_code") == COMPONENT_CODE]
    movement_count_before = len(movements_before)
    
    payload = {
        "component_code": COMPONENT_CODE,
        "component_name": "Ginger Test",
        "component_category": "Insole",
        "vendor": "",
        "unit": "pair",
        "reorder_level": 0,
        "minimum_stock": 5,
        "lead_time_days": 0,
        "rows": [
            {"color": "Silver", "size": "36", "opening_qty": -5}
        ]
    }
    
    response = requests.post(
        f"{BASE_URL}/components/bulk-matrix",
        headers=get_headers(),
        json=payload
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    if response.status_code != 200:
        log_test("TEST 4 - POST bulk-matrix", False, f"Status {response.status_code}: {response.text}")
        return
    
    data = response.json()
    
    # Verify response structure
    checks = []
    checks.append(("results length == 1", len(data.get("results", [])) == 1))
    
    results = data.get("results", [])
    if len(results) == 1:
        checks.append(("result[0] status == 'invalid_qty'", results[0].get("status") == "invalid_qty"))
    
    all_passed = all(check[1] for check in checks)
    details = "\n    ".join([f"{check[0]}: {'✓' if check[1] else '✗'}" for check in checks])
    
    if not all_passed:
        log_test("TEST 4 - POST bulk-matrix response", False, details)
        return
    
    log_test("TEST 4 - POST bulk-matrix response", True, details)
    
    # Verify current_stock still 25
    response = requests.get(
        f"{BASE_URL}/components",
        headers=get_headers(),
        params={"code": COMPONENT_CODE, "color": "Silver", "size": "36"}
    )
    
    if response.status_code != 200:
        log_test("TEST 4 - GET components", False, f"Status {response.status_code}: {response.text}")
        return
    
    rows = response.json()
    
    checks = []
    checks.append(("1 row returned", len(rows) == 1))
    
    if len(rows) == 1:
        checks.append(("current_stock == 25", rows[0]["current_stock"] == 25))
    
    all_passed = all(check[1] for check in checks)
    details = "\n    ".join([f"{check[0]}: {'✓' if check[1] else '✗'}" for check in checks])
    
    if not all_passed:
        log_test("TEST 4 - GET components verification", False, details)
        return
    
    log_test("TEST 4 - GET components verification", True, details)
    
    # Verify no new movement with quantity=-5
    response = requests.get(
        f"{BASE_URL}/components/movements",
        headers=get_headers(),
        params={"limit": 500}
    )
    
    movements_after = [m for m in response.json() if m.get("component_code") == COMPONENT_CODE]
    movement_count_after = len(movements_after)
    
    # Check no movement with quantity=-5
    negative_movements = [m for m in movements_after if m.get("quantity") == -5]
    
    checks = []
    checks.append(("no new movements", movement_count_after == movement_count_before))
    checks.append(("no movement with quantity=-5", len(negative_movements) == 0))
    
    all_passed = all(check[1] for check in checks)
    details = "\n    ".join([f"{check[0]}: {'✓' if check[1] else '✗'}" for check in checks])
    
    log_test("TEST 4 - No negative ledger entry", all_passed, details)


def test_5_ledger_stock_reconciliation():
    """
    TEST 5 — LEDGER + STOCK ARITHMETIC RECONCILIATION:
    GET /api/components?code=<code>:
      - Silver/36 current_stock == 25
      - Silver/37 current_stock == 15
      - Gold/42   current_stock == 10
    GET /api/components/movements filtered by component_code — verify all movements sum correctly per row:
      - Silver/36: entries totalling +25 (either +20 then +5, or however they landed)
      - Silver/37: entry of +15
      - Gold/42:   entry of +10
    """
    print(f"\n{'='*80}")
    print("TEST 5: LEDGER + STOCK ARITHMETIC RECONCILIATION")
    print(f"{'='*80}")
    
    # GET /api/components?code=<code>
    response = requests.get(
        f"{BASE_URL}/components",
        headers=get_headers(),
        params={"code": COMPONENT_CODE}
    )
    
    if response.status_code != 200:
        log_test("TEST 5 - GET components", False, f"Status {response.status_code}: {response.text}")
        return
    
    rows = response.json()
    
    # Find rows
    row_silver_36 = next((r for r in rows if r["color"] == "Silver" and r["size"] == "36"), None)
    row_silver_37 = next((r for r in rows if r["color"] == "Silver" and r["size"] == "37"), None)
    row_gold_42 = next((r for r in rows if r["color"] == "Gold" and r["size"] == "42"), None)
    
    checks = []
    checks.append(("Silver/36 exists", row_silver_36 is not None))
    checks.append(("Silver/37 exists", row_silver_37 is not None))
    checks.append(("Gold/42 exists", row_gold_42 is not None))
    
    if row_silver_36:
        checks.append(("Silver/36 current_stock == 25", row_silver_36["current_stock"] == 25))
    if row_silver_37:
        checks.append(("Silver/37 current_stock == 15", row_silver_37["current_stock"] == 15))
    if row_gold_42:
        checks.append(("Gold/42 current_stock == 10", row_gold_42["current_stock"] == 10))
    
    all_passed = all(check[1] for check in checks)
    details = "\n    ".join([f"{check[0]}: {'✓' if check[1] else '✗'}" for check in checks])
    
    if not all_passed:
        log_test("TEST 5 - GET components verification", False, details)
        return
    
    log_test("TEST 5 - GET components verification", True, details)
    
    # GET /api/components/movements and verify arithmetic
    response = requests.get(
        f"{BASE_URL}/components/movements",
        headers=get_headers(),
        params={"limit": 500}
    )
    
    if response.status_code != 200:
        log_test("TEST 5 - GET movements", False, f"Status {response.status_code}: {response.text}")
        return
    
    movements = response.json()
    
    # Filter by component_code
    relevant_movements = [m for m in movements if m.get("component_code") == COMPONENT_CODE]
    
    # Group by color and size
    silver_36_movements = [m for m in relevant_movements if m.get("color") == "Silver" and m.get("size") == "36"]
    silver_37_movements = [m for m in relevant_movements if m.get("color") == "Silver" and m.get("size") == "37"]
    gold_42_movements = [m for m in relevant_movements if m.get("color") == "Gold" and m.get("size") == "42"]
    
    # Sum current_delta for each
    silver_36_sum = sum(m.get("current_delta", 0) for m in silver_36_movements)
    silver_37_sum = sum(m.get("current_delta", 0) for m in silver_37_movements)
    gold_42_sum = sum(m.get("current_delta", 0) for m in gold_42_movements)
    
    checks = []
    checks.append(("Silver/36 movements sum to +25", silver_36_sum == 25))
    checks.append(("Silver/37 movements sum to +15", silver_37_sum == 15))
    checks.append(("Gold/42 movements sum to +10", gold_42_sum == 10))
    
    # Verify current_before/current_after for each movement
    for mov in silver_36_movements:
        expected_after = mov.get("current_before", 0) + mov.get("current_delta", 0)
        checks.append((f"Silver/36 movement current_after == current_before + current_delta", 
                      mov.get("current_after") == expected_after))
    
    for mov in silver_37_movements:
        expected_after = mov.get("current_before", 0) + mov.get("current_delta", 0)
        checks.append((f"Silver/37 movement current_after == current_before + current_delta", 
                      mov.get("current_after") == expected_after))
    
    for mov in gold_42_movements:
        expected_after = mov.get("current_before", 0) + mov.get("current_delta", 0)
        checks.append((f"Gold/42 movement current_after == current_before + current_delta", 
                      mov.get("current_after") == expected_after))
    
    all_passed = all(check[1] for check in checks)
    details = "\n    ".join([f"{check[0]}: {'✓' if check[1] else '✗'}" for check in checks])
    
    log_test("TEST 5 - Ledger arithmetic reconciliation", all_passed, details)


def test_6_brand_new_component_regression():
    """
    TEST 6 — BRAND-NEW COMPONENT REGRESSION:
    POST /api/components/bulk-matrix with a brand-new code (never seen before) with rows:[
        {"color":"Black","size":"38","opening_qty":10},
        {"color":"Black","size":"39","opening_qty":8}
    ]
    EXPECT 200 with created==2, updated==0, skipped==0. Both status='created'. 
    GET the component — current_stock 10 and 8 respectively. 
    Confirms the fix didn't break brand-new creation.
    """
    print(f"\n{'='*80}")
    print("TEST 6: BRAND-NEW COMPONENT REGRESSION")
    print(f"{'='*80}")
    
    new_component_code = f"BrandNew_{TIMESTAMP}"
    
    payload = {
        "component_code": new_component_code,
        "component_name": "Brand New Test",
        "component_category": "Insole",
        "vendor": "",
        "unit": "pair",
        "reorder_level": 0,
        "minimum_stock": 5,
        "lead_time_days": 0,
        "rows": [
            {"color": "Black", "size": "38", "opening_qty": 10},
            {"color": "Black", "size": "39", "opening_qty": 8}
        ]
    }
    
    response = requests.post(
        f"{BASE_URL}/components/bulk-matrix",
        headers=get_headers(),
        json=payload
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    if response.status_code != 200:
        log_test("TEST 6 - POST bulk-matrix", False, f"Status {response.status_code}: {response.text}")
        return
    
    data = response.json()
    
    # Verify response structure
    checks = []
    checks.append(("created == 2", data.get("created") == 2))
    checks.append(("updated == 0", data.get("updated") == 0))
    checks.append(("skipped == 0", data.get("skipped") == 0))
    checks.append(("results length == 2", len(data.get("results", [])) == 2))
    
    results = data.get("results", [])
    if len(results) == 2:
        checks.append(("result[0] status == 'created'", results[0].get("status") == "created"))
        checks.append(("result[1] status == 'created'", results[1].get("status") == "created"))
    
    all_passed = all(check[1] for check in checks)
    details = "\n    ".join([f"{check[0]}: {'✓' if check[1] else '✗'}" for check in checks])
    
    if not all_passed:
        log_test("TEST 6 - POST bulk-matrix response", False, details)
        return
    
    log_test("TEST 6 - POST bulk-matrix response", True, details)
    
    # Verify GET /api/components
    response = requests.get(
        f"{BASE_URL}/components",
        headers=get_headers(),
        params={"code": new_component_code}
    )
    
    if response.status_code != 200:
        log_test("TEST 6 - GET components", False, f"Status {response.status_code}: {response.text}")
        return
    
    rows = response.json()
    
    # Find rows
    row_38 = next((r for r in rows if r["size"] == "38"), None)
    row_39 = next((r for r in rows if r["size"] == "39"), None)
    
    checks = []
    checks.append(("Black/38 exists", row_38 is not None))
    checks.append(("Black/39 exists", row_39 is not None))
    
    if row_38:
        checks.append(("Black/38 current_stock == 10", row_38["current_stock"] == 10))
    if row_39:
        checks.append(("Black/39 current_stock == 8", row_39["current_stock"] == 8))
    
    all_passed = all(check[1] for check in checks)
    details = "\n    ".join([f"{check[0]}: {'✓' if check[1] else '✗'}" for check in checks])
    
    log_test("TEST 6 - GET components verification", all_passed, details)


def test_7_smoke_adjacent_endpoints():
    """
    TEST 7 — SMOKE ON ADJACENT ENDPOINTS:
    GET /api/components → 200
    GET /api/components/movements → 200
    POST /api/components/movements (single movement) → 200 for a valid movement on the Gold/42 row (+5)
    GET the Gold/42 row → current_stock now 15
    """
    print(f"\n{'='*80}")
    print("TEST 7: SMOKE ON ADJACENT ENDPOINTS")
    print(f"{'='*80}")
    
    # GET /api/components
    response = requests.get(
        f"{BASE_URL}/components",
        headers=get_headers()
    )
    
    checks = []
    checks.append(("GET /api/components → 200", response.status_code == 200))
    
    # GET /api/components/movements
    response = requests.get(
        f"{BASE_URL}/components/movements",
        headers=get_headers()
    )
    
    checks.append(("GET /api/components/movements → 200", response.status_code == 200))
    
    # Get Gold/42 row to get component_id
    response = requests.get(
        f"{BASE_URL}/components",
        headers=get_headers(),
        params={"code": COMPONENT_CODE, "color": "Gold", "size": "42"}
    )
    
    if response.status_code != 200:
        log_test("TEST 7 - GET Gold/42 row", False, f"Status {response.status_code}: {response.text}")
        return
    
    rows = response.json()
    if len(rows) == 0:
        log_test("TEST 7 - GET Gold/42 row", False, "Gold/42 row not found")
        return
    
    gold_42_row = rows[0]
    component_id = gold_42_row["id"]
    
    # POST /api/components/movements
    movement_payload = {
        "component_id": component_id,
        "movement_type": "purchase_in",
        "quantity": 5,
        "reference_type": "manual",
        "notes": "Test movement for Gold/42"
    }
    
    response = requests.post(
        f"{BASE_URL}/components/movements",
        headers=get_headers(),
        json=movement_payload
    )
    
    print(f"POST /api/components/movements Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    checks.append(("POST /api/components/movements → 200", response.status_code == 200))
    
    # GET the Gold/42 row again to verify current_stock now 15
    response = requests.get(
        f"{BASE_URL}/components",
        headers=get_headers(),
        params={"code": COMPONENT_CODE, "color": "Gold", "size": "42"}
    )
    
    if response.status_code != 200:
        log_test("TEST 7 - GET Gold/42 row after movement", False, f"Status {response.status_code}: {response.text}")
        return
    
    rows = response.json()
    if len(rows) == 0:
        log_test("TEST 7 - GET Gold/42 row after movement", False, "Gold/42 row not found")
        return
    
    gold_42_row = rows[0]
    checks.append(("Gold/42 current_stock == 15", gold_42_row["current_stock"] == 15))
    
    all_passed = all(check[1] for check in checks)
    details = "\n    ".join([f"{check[0]}: {'✓' if check[1] else '✗'}" for check in checks])
    
    log_test("TEST 7 - Smoke on adjacent endpoints", all_passed, details)


def print_summary():
    """Print test summary."""
    print(f"\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}")
    
    total = len(test_results)
    passed = sum(1 for r in test_results if r["passed"])
    failed = total - passed
    
    print(f"\nTotal tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success rate: {passed/total*100:.1f}%")
    
    if failed > 0:
        print(f"\n{'='*80}")
        print("FAILED TESTS:")
        print(f"{'='*80}")
        for result in test_results:
            if not result["passed"]:
                print(f"\n❌ {result['test']}")
                if result["details"]:
                    print(f"  {result['details']}")
    
    print(f"\n{'='*80}")
    print("ALL TESTS:")
    print(f"{'='*80}")
    for result in test_results:
        status = "✅ PASS" if result["passed"] else "❌ FAIL"
        print(f"{status}: {result['test']}")


def main():
    """Main test runner."""
    print(f"\n{'='*80}")
    print("BACKEND TEST: POST /api/components/bulk-matrix BUG FIX")
    print(f"{'='*80}")
    print(f"Component code: {COMPONENT_CODE}")
    print(f"Base URL: {BASE_URL}")
    
    # Login
    login()
    
    # Setup fixture
    setup_fixture()
    
    # Run tests
    test_1_bug_fix_extend_mode_stock_topup()
    test_2_mixed_batch()
    test_3_existing_row_zero_qty()
    test_4_negative_qty_guard()
    test_5_ledger_stock_reconciliation()
    test_6_brand_new_component_regression()
    test_7_smoke_adjacent_endpoints()
    
    # Print summary
    print_summary()
    
    # Exit with appropriate code
    failed = sum(1 for r in test_results if not r["passed"])
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
