#!/usr/bin/env python3
"""
Backend test suite for Phase 6.1 Component Inventory Foundation.

Tests all NEW backend endpoints for component master, movements ledger, and style⇄component BOM mapping.
"""

import requests
import json
import sys
import time

# Backend URL from frontend/.env
BASE_URL = "https://run-here.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"

def print_test(name):
    print(f"\n{'='*80}")
    print(f"TEST: {name}")
    print('='*80)

def print_pass(msg):
    print(f"✅ PASS: {msg}")

def print_fail(msg):
    print(f"❌ FAIL: {msg}")

def print_info(msg):
    print(f"ℹ️  INFO: {msg}")

# ============================================================================
# SETUP: Login and get access token
# ============================================================================
def login():
    print_test("SETUP: Login to get access token")
    
    url = f"{BASE_URL}/auth/login"
    payload = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    
    resp = requests.post(url, json=payload)
    
    print_info(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print_fail(f"Login failed with {resp.status_code}: {resp.text[:500]}")
        return None
    
    data = resp.json()
    access_token = data.get("access_token")
    
    if not access_token:
        print_fail("No access_token in response")
        return None
    
    print_pass(f"Login successful, got access token")
    return access_token

# ============================================================================
# SETUP: Get or create a style to use for testing
# ============================================================================
def get_or_create_style(headers):
    print_test("SETUP: Get or create a style for testing")
    
    # Try to get existing styles
    resp = requests.get(f"{BASE_URL}/styles", headers=headers)
    
    if resp.status_code == 200:
        styles = resp.json()
        if styles:
            style = styles[0]
            print_pass(f"Using existing style: {style['id']} (code: {style.get('code', 'N/A')})")
            return style['id'], style.get('code', 'TEST-STYLE')
    
    # Create a new style
    print_info("No existing styles found, creating a new one...")
    
    payload = {
        "code": "TEST-COMP-STYLE-001",
        "name": "Test Style for Component Testing",
        "category": "Footwear"
    }
    
    resp = requests.post(f"{BASE_URL}/styles", json=payload, headers=headers)
    
    if resp.status_code not in [200, 201]:
        print_fail(f"Failed to create style: {resp.status_code} - {resp.text[:500]}")
        return None, None
    
    data = resp.json()
    style_id = data.get("id")
    style_code = data.get("code", "TEST-COMP-STYLE-001")
    
    print_pass(f"Created new style: {style_id} (code: {style_code})")
    return style_id, style_code

# ============================================================================
# TEST 1: POST /api/components - create single component
# ============================================================================
def test_create_component(headers):
    print_test("TEST 1: POST /api/components - create single component")
    
    # Use unique timestamp to avoid collisions
    timestamp = int(time.time())
    
    payload = {
        "component_code": f"TEST-COMP-{timestamp}",
        "component_name": "Test Component Upper",
        "component_category": "Upper",
        "color": "Black",
        "size": "M",
        "vendor": "Test Vendor Inc",
        "unit": "pair",
        "current_stock": 100,  # Opening balance
        "reorder_level": 50,
        "minimum_stock": 20,
        "lead_time_days": 7,
        "active": True
    }
    
    resp = requests.post(f"{BASE_URL}/components", json=payload, headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:1000]}")
    
    if resp.status_code not in [200, 201]:
        print_fail(f"Expected 200/201, got {resp.status_code}")
        return False, None
    
    data = resp.json()
    
    # Verify response structure
    if not data.get("id"):
        print_fail("Response missing 'id' field")
        return False, None
    
    if data.get("current_stock") != 100:
        print_fail(f"Expected current_stock=100, got {data.get('current_stock')}")
        return False, None
    
    if data.get("reserved_stock") != 0:
        print_fail(f"Expected reserved_stock=0, got {data.get('reserved_stock')}")
        return False, None
    
    if data.get("available_stock") != 100:
        print_fail(f"Expected available_stock=100, got {data.get('available_stock')}")
        return False, None
    
    component_id = data["id"]
    print_pass(f"Component created successfully with id={component_id}")
    
    # Verify opening balance ledger entry
    print_info("Verifying opening balance ledger entry...")
    resp = requests.get(f"{BASE_URL}/components/movements?component_id={component_id}", headers=headers)
    
    if resp.status_code != 200:
        print_fail(f"Failed to fetch movements: {resp.status_code}")
        return False, None
    
    movements = resp.json()
    
    if len(movements) != 1:
        print_fail(f"Expected 1 movement (opening balance), got {len(movements)}")
        return False, None
    
    mov = movements[0]
    if mov.get("reference_type") != "opening_balance":
        print_fail(f"Expected reference_type='opening_balance', got {mov.get('reference_type')}")
        return False, None
    
    if mov.get("current_delta") != 100:
        print_fail(f"Expected current_delta=100, got {mov.get('current_delta')}")
        return False, None
    
    print_pass("Opening balance ledger entry verified")
    
    # Test duplicate insert (should return 409)
    print_info("Testing duplicate insert...")
    resp = requests.post(f"{BASE_URL}/components", json=payload, headers=headers)
    
    if resp.status_code != 409:
        print_fail(f"Expected 409 for duplicate, got {resp.status_code}")
        return False, None
    
    print_pass("Duplicate insert correctly rejected with 409")
    
    # Test invalid category (should return 422)
    print_info("Testing invalid category...")
    invalid_payload = {**payload, "component_code": f"TEST-INVALID-{timestamp}", "component_category": "InvalidCategory"}
    resp = requests.post(f"{BASE_URL}/components", json=invalid_payload, headers=headers)
    
    if resp.status_code != 422:
        print_fail(f"Expected 422 for invalid category, got {resp.status_code}")
        return False, None
    
    print_pass("Invalid category correctly rejected with 422")
    
    # Test negative current_stock (should return 400)
    print_info("Testing negative current_stock...")
    negative_payload = {**payload, "component_code": f"TEST-NEGATIVE-{timestamp}", "current_stock": -10}
    resp = requests.post(f"{BASE_URL}/components", json=negative_payload, headers=headers)
    
    if resp.status_code != 400:
        print_fail(f"Expected 400 for negative stock, got {resp.status_code}")
        return False, None
    
    print_pass("Negative current_stock correctly rejected with 400")
    
    return True, component_id

# ============================================================================
# TEST 2: GET /api/components - list with filters
# ============================================================================
def test_list_components(headers, component_id):
    print_test("TEST 2: GET /api/components - list with filters")
    
    # Get the component we created
    resp = requests.get(f"{BASE_URL}/components", headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print_fail(f"Expected 200, got {resp.status_code}")
        return False
    
    components = resp.json()
    
    if not isinstance(components, list):
        print_fail(f"Expected list response, got {type(components)}")
        return False
    
    # Find our component
    our_comp = None
    for c in components:
        if c.get("id") == component_id:
            our_comp = c
            break
    
    if not our_comp:
        print_fail(f"Component {component_id} not found in list")
        return False
    
    # Verify available_stock is derived correctly
    if our_comp.get("available_stock") != (our_comp.get("current_stock", 0) - our_comp.get("reserved_stock", 0)):
        print_fail(f"available_stock not computed correctly")
        return False
    
    print_pass("Component list retrieved successfully with derived available_stock")
    
    # Test filter by code
    print_info("Testing filter by code...")
    resp = requests.get(f"{BASE_URL}/components?code={our_comp['component_code']}", headers=headers)
    
    if resp.status_code != 200:
        print_fail(f"Filter by code failed: {resp.status_code}")
        return False
    
    filtered = resp.json()
    if len(filtered) == 0:
        print_fail("Filter by code returned no results")
        return False
    
    print_pass("Filter by code works")
    
    # Test filter by category
    print_info("Testing filter by category...")
    resp = requests.get(f"{BASE_URL}/components?category=Upper", headers=headers)
    
    if resp.status_code != 200:
        print_fail(f"Filter by category failed: {resp.status_code}")
        return False
    
    print_pass("Filter by category works")
    
    # Test search (should match component_code, component_name, vendor)
    print_info("Testing search...")
    resp = requests.get(f"{BASE_URL}/components?search=Test", headers=headers)
    
    if resp.status_code != 200:
        print_fail(f"Search failed: {resp.status_code}")
        return False
    
    print_pass("Search works")
    
    # Test low_stock filter
    # For this, we need a component where minimum_stock > 0 AND available_stock <= minimum_stock
    # Our component has minimum_stock=20 and available_stock=100, so it should NOT appear
    print_info("Testing low_stock filter...")
    resp = requests.get(f"{BASE_URL}/components?low_stock=true", headers=headers)
    
    if resp.status_code != 200:
        print_fail(f"low_stock filter failed: {resp.status_code}")
        return False
    
    low_stock_comps = resp.json()
    # Our component should NOT be in this list
    found = any(c.get("id") == component_id for c in low_stock_comps)
    if found:
        print_fail("Component with high stock incorrectly included in low_stock filter")
        return False
    
    print_pass("low_stock filter works correctly")
    
    return True

# ============================================================================
# TEST 3: PUT /api/components/{id} - metadata update only
# ============================================================================
def test_update_component(headers, component_id):
    print_test("TEST 3: PUT /api/components/{id} - metadata update")
    
    # Get current state
    resp = requests.get(f"{BASE_URL}/components", headers=headers)
    components = resp.json()
    our_comp = next((c for c in components if c.get("id") == component_id), None)
    
    if not our_comp:
        print_fail(f"Component {component_id} not found")
        return False
    
    current_stock_before = our_comp.get("current_stock")
    reserved_stock_before = our_comp.get("reserved_stock")
    
    # Update metadata only
    payload = {
        "component_name": "Updated Component Name",
        "vendor": "Updated Vendor",
        "reorder_level": 60
    }
    
    resp = requests.put(f"{BASE_URL}/components/{component_id}", json=payload, headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:500]}")
    
    if resp.status_code != 200:
        print_fail(f"Expected 200, got {resp.status_code}")
        return False
    
    data = resp.json()
    
    # Verify metadata updated
    if data.get("component_name") != "Updated Component Name":
        print_fail(f"component_name not updated")
        return False
    
    if data.get("vendor") != "Updated Vendor":
        print_fail(f"vendor not updated")
        return False
    
    if data.get("reorder_level") != 60:
        print_fail(f"reorder_level not updated")
        return False
    
    # Verify stock counters unchanged
    if data.get("current_stock") != current_stock_before:
        print_fail(f"current_stock changed after metadata update: {current_stock_before} → {data.get('current_stock')}")
        return False
    
    if data.get("reserved_stock") != reserved_stock_before:
        print_fail(f"reserved_stock changed after metadata update: {reserved_stock_before} → {data.get('reserved_stock')}")
        return False
    
    print_pass("Metadata updated successfully, stock counters unchanged")
    
    # Test non-existent id (should return 404)
    print_info("Testing non-existent id...")
    resp = requests.put(f"{BASE_URL}/components/000000000000000000000000", json=payload, headers=headers)
    
    if resp.status_code != 404:
        print_fail(f"Expected 404 for non-existent id, got {resp.status_code}")
        return False
    
    print_pass("Non-existent id correctly rejected with 404")
    
    return True

# ============================================================================
# TEST 4: POST /api/components/bulk-matrix - bulk create
# ============================================================================
def test_bulk_matrix(headers):
    print_test("TEST 4: POST /api/components/bulk-matrix - bulk create")
    
    timestamp = int(time.time())
    
    payload = {
        "component_code": f"BULK-COMP-{timestamp}",
        "component_name": "Bulk Test Component",
        "component_category": "Sole",
        "vendor": "Bulk Vendor",
        "unit": "pair",
        "reorder_level": 100,
        "minimum_stock": 50,
        "lead_time_days": 10,
        "rows": [
            {"color": "Red", "size": "S", "opening_qty": 50},
            {"color": "Red", "size": "M", "opening_qty": 60},
            {"color": "Blue", "size": "S", "opening_qty": 40},
            {"color": "Blue", "size": "M", "opening_qty": 0},  # Zero opening
            {"color": "Green", "size": "L", "opening_qty": 70}
        ]
    }
    
    resp = requests.post(f"{BASE_URL}/components/bulk-matrix", json=payload, headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:1000]}")
    
    if resp.status_code not in [200, 201]:
        print_fail(f"Expected 200/201, got {resp.status_code}")
        return False, None
    
    data = resp.json()
    
    if data.get("created") != 5:
        print_fail(f"Expected created=5, got {data.get('created')}")
        return False, None
    
    if data.get("skipped") != 0:
        print_fail(f"Expected skipped=0, got {data.get('skipped')}")
        return False, None
    
    results = data.get("results", [])
    if len(results) != 5:
        print_fail(f"Expected 5 results, got {len(results)}")
        return False, None
    
    # All should have status="created"
    for r in results:
        if r.get("status") != "created":
            print_fail(f"Expected status='created', got {r.get('status')} for {r}")
            return False, None
    
    print_pass("Bulk matrix created 5 rows successfully")
    
    # Verify opening balance ledger entries for rows with opening_qty > 0
    print_info("Verifying opening balance ledger entries...")
    
    # Get all components with this code
    resp = requests.get(f"{BASE_URL}/components?code={payload['component_code']}", headers=headers)
    components = resp.json()
    
    if len(components) != 5:
        print_fail(f"Expected 5 components, got {len(components)}")
        return False, None
    
    # Check ledger for each component with opening_qty > 0
    expected_openings = [
        ("Red", "S", 50),
        ("Red", "M", 60),
        ("Blue", "S", 40),
        ("Green", "L", 70)
    ]
    
    for color, size, qty in expected_openings:
        comp = next((c for c in components if c.get("color") == color and c.get("size") == size), None)
        if not comp:
            print_fail(f"Component {color}/{size} not found")
            return False, None
        
        # Check movements
        resp = requests.get(f"{BASE_URL}/components/movements?component_id={comp['id']}", headers=headers)
        movements = resp.json()
        
        if len(movements) != 1:
            print_fail(f"Expected 1 movement for {color}/{size}, got {len(movements)}")
            return False, None
        
        mov = movements[0]
        if mov.get("reference_type") != "opening_balance":
            print_fail(f"Expected reference_type='opening_balance' for {color}/{size}")
            return False, None
        
        if mov.get("current_delta") != qty:
            print_fail(f"Expected current_delta={qty} for {color}/{size}, got {mov.get('current_delta')}")
            return False, None
    
    print_pass("Opening balance ledger entries verified for all rows with opening_qty > 0")
    
    # Test duplicate insert (should skip existing rows)
    print_info("Testing duplicate insert (should skip existing rows)...")
    
    duplicate_payload = {
        **payload,
        "rows": [
            {"color": "Red", "size": "S", "opening_qty": 100},  # Existing
            {"color": "Yellow", "size": "XL", "opening_qty": 80}  # New
        ]
    }
    
    resp = requests.post(f"{BASE_URL}/components/bulk-matrix", json=duplicate_payload, headers=headers)
    
    if resp.status_code not in [200, 201]:
        print_fail(f"Expected 200/201, got {resp.status_code}")
        return False, None
    
    data = resp.json()
    
    if data.get("created") != 1:
        print_fail(f"Expected created=1 (only new row), got {data.get('created')}")
        return False, None
    
    if data.get("skipped") != 1:
        print_fail(f"Expected skipped=1 (existing row), got {data.get('skipped')}")
        return False, None
    
    results = data.get("results", [])
    # First should be "exists", second should be "created"
    if results[0].get("status") != "exists":
        print_fail(f"Expected status='exists' for duplicate row, got {results[0].get('status')}")
        return False, None
    
    if results[1].get("status") != "created":
        print_fail(f"Expected status='created' for new row, got {results[1].get('status')}")
        return False, None
    
    print_pass("Duplicate rows correctly skipped, new rows created")
    
    # Get one component_id for later tests
    test_component_id = components[0]["id"]
    
    return True, test_component_id

# ============================================================================
# TEST 5: POST /api/components/movements - all 8 movement types
# ============================================================================
def test_component_movements(headers, component_id):
    print_test("TEST 5: POST /api/components/movements - all 8 movement types")
    
    # Get initial state
    resp = requests.get(f"{BASE_URL}/components", headers=headers)
    components = resp.json()
    comp = next((c for c in components if c.get("id") == component_id), None)
    
    if not comp:
        print_fail(f"Component {component_id} not found")
        return False
    
    initial_current = comp.get("current_stock", 0)
    initial_reserved = comp.get("reserved_stock", 0)
    
    print_info(f"Initial state: current={initial_current}, reserved={initial_reserved}")
    
    # Movement 1: purchase_in (qty=100)
    print_info("Testing purchase_in...")
    payload = {
        "component_id": component_id,
        "movement_type": "purchase_in",
        "quantity": 100,
        "reference_type": "manual",
        "notes": "Test purchase"
    }
    
    resp = requests.post(f"{BASE_URL}/components/movements", json=payload, headers=headers)
    
    if resp.status_code not in [200, 201]:
        print_fail(f"purchase_in failed: {resp.status_code} - {resp.text[:500]}")
        return False
    
    data = resp.json()
    ledger = data.get("ledger", {})
    component = data.get("component", {})
    
    if ledger.get("current_delta") != 100:
        print_fail(f"Expected current_delta=100, got {ledger.get('current_delta')}")
        return False
    
    if component.get("current_stock") != initial_current + 100:
        print_fail(f"Expected current_stock={initial_current + 100}, got {component.get('current_stock')}")
        return False
    
    print_pass("purchase_in: current+100 ✓")
    
    # Update tracking
    current_stock = component.get("current_stock")
    reserved_stock = component.get("reserved_stock")
    
    # Movement 2: return_in (qty=20)
    print_info("Testing return_in...")
    payload = {
        "component_id": component_id,
        "movement_type": "return_in",
        "quantity": 20,
        "reference_type": "manual",
        "notes": "Test return"
    }
    
    resp = requests.post(f"{BASE_URL}/components/movements", json=payload, headers=headers)
    
    if resp.status_code not in [200, 201]:
        print_fail(f"return_in failed: {resp.status_code}")
        return False
    
    data = resp.json()
    component = data.get("component", {})
    
    if component.get("current_stock") != current_stock + 20:
        print_fail(f"Expected current_stock={current_stock + 20}, got {component.get('current_stock')}")
        return False
    
    print_pass("return_in: current+20 ✓")
    current_stock = component.get("current_stock")
    
    # Movement 3: adjustment increase (qty=30)
    print_info("Testing adjustment increase...")
    payload = {
        "component_id": component_id,
        "movement_type": "adjustment",
        "quantity": 30,
        "adjustment_dir": "increase",
        "reference_type": "manual",
        "notes": "Test adjustment increase"
    }
    
    resp = requests.post(f"{BASE_URL}/components/movements", json=payload, headers=headers)
    
    if resp.status_code not in [200, 201]:
        print_fail(f"adjustment increase failed: {resp.status_code}")
        return False
    
    data = resp.json()
    component = data.get("component", {})
    
    if component.get("current_stock") != current_stock + 30:
        print_fail(f"Expected current_stock={current_stock + 30}, got {component.get('current_stock')}")
        return False
    
    print_pass("adjustment increase: current+30 ✓")
    current_stock = component.get("current_stock")
    
    # Movement 4: adjustment decrease (qty=10)
    print_info("Testing adjustment decrease...")
    payload = {
        "component_id": component_id,
        "movement_type": "adjustment",
        "quantity": 10,
        "adjustment_dir": "decrease",
        "reference_type": "manual",
        "notes": "Test adjustment decrease"
    }
    
    resp = requests.post(f"{BASE_URL}/components/movements", json=payload, headers=headers)
    
    if resp.status_code not in [200, 201]:
        print_fail(f"adjustment decrease failed: {resp.status_code}")
        return False
    
    data = resp.json()
    component = data.get("component", {})
    
    if component.get("current_stock") != current_stock - 10:
        print_fail(f"Expected current_stock={current_stock - 10}, got {component.get('current_stock')}")
        return False
    
    print_pass("adjustment decrease: current-10 ✓")
    current_stock = component.get("current_stock")
    
    # Movement 5: adjustment without adjustment_dir (should fail with 400)
    print_info("Testing adjustment without adjustment_dir (should fail)...")
    payload = {
        "component_id": component_id,
        "movement_type": "adjustment",
        "quantity": 5,
        "reference_type": "manual"
    }
    
    resp = requests.post(f"{BASE_URL}/components/movements", json=payload, headers=headers)
    
    if resp.status_code != 400:
        print_fail(f"Expected 400 for adjustment without adjustment_dir, got {resp.status_code}")
        return False
    
    print_pass("adjustment without adjustment_dir correctly rejected with 400 ✓")
    
    # Movement 6: production_reserve (qty=50)
    print_info("Testing production_reserve...")
    payload = {
        "component_id": component_id,
        "movement_type": "production_reserve",
        "quantity": 50,
        "reference_type": "manual",
        "notes": "Test production reserve"
    }
    
    resp = requests.post(f"{BASE_URL}/components/movements", json=payload, headers=headers)
    
    if resp.status_code not in [200, 201]:
        print_fail(f"production_reserve failed: {resp.status_code}")
        return False
    
    data = resp.json()
    component = data.get("component", {})
    
    if component.get("reserved_stock") != reserved_stock + 50:
        print_fail(f"Expected reserved_stock={reserved_stock + 50}, got {component.get('reserved_stock')}")
        return False
    
    if component.get("current_stock") != current_stock:
        print_fail(f"current_stock should not change on reserve, was {current_stock}, got {component.get('current_stock')}")
        return False
    
    print_pass("production_reserve: reserved+50, current unchanged ✓")
    reserved_stock = component.get("reserved_stock")
    
    # Movement 7: online_reserve (qty=30)
    print_info("Testing online_reserve...")
    payload = {
        "component_id": component_id,
        "movement_type": "online_reserve",
        "quantity": 30,
        "reference_type": "manual",
        "notes": "Test online reserve"
    }
    
    resp = requests.post(f"{BASE_URL}/components/movements", json=payload, headers=headers)
    
    if resp.status_code not in [200, 201]:
        print_fail(f"online_reserve failed: {resp.status_code}")
        return False
    
    data = resp.json()
    component = data.get("component", {})
    
    if component.get("reserved_stock") != reserved_stock + 30:
        print_fail(f"Expected reserved_stock={reserved_stock + 30}, got {component.get('reserved_stock')}")
        return False
    
    print_pass("online_reserve: reserved+30 ✓")
    reserved_stock = component.get("reserved_stock")
    
    # Movement 8: unreserve (qty=20)
    print_info("Testing unreserve...")
    payload = {
        "component_id": component_id,
        "movement_type": "unreserve",
        "quantity": 20,
        "reference_type": "manual",
        "notes": "Test unreserve"
    }
    
    resp = requests.post(f"{BASE_URL}/components/movements", json=payload, headers=headers)
    
    if resp.status_code not in [200, 201]:
        print_fail(f"unreserve failed: {resp.status_code}")
        return False
    
    data = resp.json()
    component = data.get("component", {})
    
    if component.get("reserved_stock") != reserved_stock - 20:
        print_fail(f"Expected reserved_stock={reserved_stock - 20}, got {component.get('reserved_stock')}")
        return False
    
    print_pass("unreserve: reserved-20 ✓")
    reserved_stock = component.get("reserved_stock")
    
    # Movement 9: production_issue (qty=15) - consumes reservation
    print_info("Testing production_issue...")
    payload = {
        "component_id": component_id,
        "movement_type": "production_issue",
        "quantity": 15,
        "reference_type": "manual",
        "notes": "Test production issue"
    }
    
    resp = requests.post(f"{BASE_URL}/components/movements", json=payload, headers=headers)
    
    if resp.status_code not in [200, 201]:
        print_fail(f"production_issue failed: {resp.status_code}")
        return False
    
    data = resp.json()
    component = data.get("component", {})
    
    if component.get("current_stock") != current_stock - 15:
        print_fail(f"Expected current_stock={current_stock - 15}, got {component.get('current_stock')}")
        return False
    
    if component.get("reserved_stock") != reserved_stock - 15:
        print_fail(f"Expected reserved_stock={reserved_stock - 15}, got {component.get('reserved_stock')}")
        return False
    
    print_pass("production_issue: current-15 AND reserved-15 ✓")
    current_stock = component.get("current_stock")
    reserved_stock = component.get("reserved_stock")
    
    # Movement 10: online_issue (qty=5)
    print_info("Testing online_issue...")
    payload = {
        "component_id": component_id,
        "movement_type": "online_issue",
        "quantity": 5,
        "reference_type": "manual",
        "notes": "Test online issue"
    }
    
    resp = requests.post(f"{BASE_URL}/components/movements", json=payload, headers=headers)
    
    if resp.status_code not in [200, 201]:
        print_fail(f"online_issue failed: {resp.status_code}")
        return False
    
    data = resp.json()
    component = data.get("component", {})
    
    if component.get("current_stock") != current_stock - 5:
        print_fail(f"Expected current_stock={current_stock - 5}, got {component.get('current_stock')}")
        return False
    
    if component.get("reserved_stock") != reserved_stock - 5:
        print_fail(f"Expected reserved_stock={reserved_stock - 5}, got {component.get('reserved_stock')}")
        return False
    
    print_pass("online_issue: current-5 AND reserved-5 ✓")
    current_stock = component.get("current_stock")
    reserved_stock = component.get("reserved_stock")
    
    # Test over-reserve (should fail with 400)
    print_info("Testing over-reserve (should fail)...")
    payload = {
        "component_id": component_id,
        "movement_type": "production_reserve",
        "quantity": current_stock + 100,  # More than current_stock
        "reference_type": "manual"
    }
    
    resp = requests.post(f"{BASE_URL}/components/movements", json=payload, headers=headers)
    
    if resp.status_code != 400:
        print_fail(f"Expected 400 for over-reserve, got {resp.status_code}")
        return False
    
    detail = resp.json().get("detail", "")
    if "over-reserve" not in detail.lower():
        print_fail(f"Expected error message mentioning 'over-reserve', got: {detail}")
        return False
    
    print_pass("Over-reserve correctly rejected with 400 ✓")
    
    # Test unreserve more than reserved (should fail with 400)
    print_info("Testing unreserve more than reserved (should fail)...")
    payload = {
        "component_id": component_id,
        "movement_type": "unreserve",
        "quantity": reserved_stock + 100,
        "reference_type": "manual"
    }
    
    resp = requests.post(f"{BASE_URL}/components/movements", json=payload, headers=headers)
    
    if resp.status_code != 400:
        print_fail(f"Expected 400 for unreserve > reserved, got {resp.status_code}")
        return False
    
    print_pass("Unreserve more than reserved correctly rejected with 400 ✓")
    
    # Test production_issue more than reserved (should fail with 400)
    print_info("Testing production_issue more than reserved (should fail)...")
    payload = {
        "component_id": component_id,
        "movement_type": "production_issue",
        "quantity": reserved_stock + 100,
        "reference_type": "manual"
    }
    
    resp = requests.post(f"{BASE_URL}/components/movements", json=payload, headers=headers)
    
    if resp.status_code != 400:
        print_fail(f"Expected 400 for production_issue > reserved, got {resp.status_code}")
        return False
    
    print_pass("production_issue more than reserved correctly rejected with 400 ✓")
    
    # Verify ledger reconciliation
    print_info("Verifying ledger reconciliation...")
    resp = requests.get(f"{BASE_URL}/components/movements?component_id={component_id}", headers=headers)
    
    if resp.status_code != 200:
        print_fail(f"Failed to fetch movements: {resp.status_code}")
        return False
    
    movements = resp.json()
    
    # Sum up all current_delta and reserved_delta
    total_current_delta = sum(m.get("current_delta", 0) for m in movements)
    total_reserved_delta = sum(m.get("reserved_delta", 0) for m in movements)
    
    # Should match current component state (starting from 0)
    if current_stock != initial_current + total_current_delta:
        print_fail(f"Ledger reconciliation failed for current_stock: expected {initial_current + total_current_delta}, got {current_stock}")
        return False
    
    if reserved_stock != initial_reserved + total_reserved_delta:
        print_fail(f"Ledger reconciliation failed for reserved_stock: expected {initial_reserved + total_reserved_delta}, got {reserved_stock}")
        return False
    
    print_pass("Ledger reconciliation verified: current_stock and reserved_stock match sum of deltas ✓")
    
    # Verify ledger row structure
    print_info("Verifying ledger row structure...")
    if len(movements) == 0:
        print_fail("No movements found")
        return False
    
    mov = movements[0]
    required_fields = [
        "component_id", "component_code", "color", "size", "movement_type",
        "quantity", "current_delta", "reserved_delta", "current_before", "current_after",
        "reserved_before", "reserved_after", "reference_type", "reference_id",
        "style_id", "notes", "created_at", "by"
    ]
    
    for field in required_fields:
        if field not in mov:
            print_fail(f"Ledger row missing required field: {field}")
            return False
    
    print_pass("Ledger row structure verified with all required fields ✓")
    
    return True

# ============================================================================
# TEST 6: GET /api/components/movements - ledger listing
# ============================================================================
def test_list_movements(headers, component_id):
    print_test("TEST 6: GET /api/components/movements - ledger listing")
    
    # Get all movements
    resp = requests.get(f"{BASE_URL}/components/movements", headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print_fail(f"Expected 200, got {resp.status_code}")
        return False
    
    movements = resp.json()
    
    if not isinstance(movements, list):
        print_fail(f"Expected list response, got {type(movements)}")
        return False
    
    print_pass(f"Retrieved {len(movements)} movements")
    
    # Test filter by component_id
    print_info("Testing filter by component_id...")
    resp = requests.get(f"{BASE_URL}/components/movements?component_id={component_id}", headers=headers)
    
    if resp.status_code != 200:
        print_fail(f"Filter by component_id failed: {resp.status_code}")
        return False
    
    filtered = resp.json()
    
    # All should have matching component_id
    for m in filtered:
        if m.get("component_id") != component_id:
            print_fail(f"Filter by component_id returned wrong component: {m.get('component_id')}")
            return False
    
    print_pass("Filter by component_id works")
    
    # Test filter by movement_type
    print_info("Testing filter by movement_type...")
    resp = requests.get(f"{BASE_URL}/components/movements?movement_type=purchase_in", headers=headers)
    
    if resp.status_code != 200:
        print_fail(f"Filter by movement_type failed: {resp.status_code}")
        return False
    
    filtered = resp.json()
    
    # All should have movement_type=purchase_in
    for m in filtered:
        if m.get("movement_type") != "purchase_in":
            print_fail(f"Filter by movement_type returned wrong type: {m.get('movement_type')}")
            return False
    
    print_pass("Filter by movement_type works")
    
    # Verify sort order (DESC by created_at)
    print_info("Verifying sort order (DESC by created_at)...")
    resp = requests.get(f"{BASE_URL}/components/movements?component_id={component_id}", headers=headers)
    movements = resp.json()
    
    if len(movements) > 1:
        for i in range(len(movements) - 1):
            if movements[i].get("created_at", "") < movements[i+1].get("created_at", ""):
                print_fail("Movements not sorted DESC by created_at")
                return False
    
    print_pass("Movements sorted DESC by created_at ✓")
    
    return True

# ============================================================================
# TEST 7: POST /api/style-component-mapping - BOM link
# ============================================================================
def test_create_bom_mapping(headers, style_id, component_id):
    print_test("TEST 7: POST /api/style-component-mapping - BOM link")
    
    payload = {
        "style_id": style_id,
        "component_id": component_id,
        "quantity_per_pair": 2.0,
        "wastage_percent": 5.0,
        "active": True
    }
    
    resp = requests.post(f"{BASE_URL}/style-component-mapping", json=payload, headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:1000]}")
    
    if resp.status_code not in [200, 201]:
        print_fail(f"Expected 200/201, got {resp.status_code}")
        return False, None
    
    data = resp.json()
    
    if not data.get("id"):
        print_fail("Response missing 'id' field")
        return False, None
    
    if data.get("style_id") != style_id:
        print_fail(f"Expected style_id={style_id}, got {data.get('style_id')}")
        return False, None
    
    if data.get("component_id") != component_id:
        print_fail(f"Expected component_id={component_id}, got {data.get('component_id')}")
        return False, None
    
    # Verify component_category is denormalised
    if not data.get("component_category"):
        print_fail("component_category not denormalised in mapping")
        return False, None
    
    mapping_id = data["id"]
    print_pass(f"BOM mapping created successfully with id={mapping_id}")
    
    # Test duplicate (should return 409)
    print_info("Testing duplicate mapping...")
    resp = requests.post(f"{BASE_URL}/style-component-mapping", json=payload, headers=headers)
    
    if resp.status_code != 409:
        print_fail(f"Expected 409 for duplicate, got {resp.status_code}")
        return False, None
    
    print_pass("Duplicate mapping correctly rejected with 409")
    
    # Test missing style (should return 404)
    print_info("Testing missing style...")
    invalid_payload = {**payload, "style_id": "000000000000000000000000"}
    resp = requests.post(f"{BASE_URL}/style-component-mapping", json=invalid_payload, headers=headers)
    
    if resp.status_code != 404:
        print_fail(f"Expected 404 for missing style, got {resp.status_code}")
        return False, None
    
    print_pass("Missing style correctly rejected with 404")
    
    # Test missing component (should return 404)
    print_info("Testing missing component...")
    invalid_payload = {**payload, "component_id": "000000000000000000000000"}
    resp = requests.post(f"{BASE_URL}/style-component-mapping", json=invalid_payload, headers=headers)
    
    if resp.status_code != 404:
        print_fail(f"Expected 404 for missing component, got {resp.status_code}")
        return False, None
    
    print_pass("Missing component correctly rejected with 404")
    
    return True, mapping_id

# ============================================================================
# TEST 8: GET /api/style-component-mapping - list
# ============================================================================
def test_list_bom_mapping(headers, style_id, component_id):
    print_test("TEST 8: GET /api/style-component-mapping - list")
    
    # Get all mappings
    resp = requests.get(f"{BASE_URL}/style-component-mapping", headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print_fail(f"Expected 200, got {resp.status_code}")
        return False
    
    mappings = resp.json()
    
    if not isinstance(mappings, list):
        print_fail(f"Expected list response, got {type(mappings)}")
        return False
    
    print_pass(f"Retrieved {len(mappings)} mappings")
    
    # Test filter by style_id
    print_info("Testing filter by style_id...")
    resp = requests.get(f"{BASE_URL}/style-component-mapping?style_id={style_id}", headers=headers)
    
    if resp.status_code != 200:
        print_fail(f"Filter by style_id failed: {resp.status_code}")
        return False
    
    filtered = resp.json()
    
    if len(filtered) == 0:
        print_fail("Filter by style_id returned no results")
        return False
    
    # Verify denormalised fields
    mapping = filtered[0]
    required_fields = [
        "style_code", "style_name", "component_code", "component_name",
        "component_category", "component_color", "component_size",
        "current_stock", "reserved_stock", "available_stock"
    ]
    
    for field in required_fields:
        if field not in mapping:
            print_fail(f"Mapping missing denormalised field: {field}")
            return False
    
    # Verify available_stock is computed correctly
    if mapping.get("available_stock") != (mapping.get("current_stock", 0) - mapping.get("reserved_stock", 0)):
        print_fail("available_stock not computed correctly in mapping")
        return False
    
    print_pass("Filter by style_id works with all denormalised fields")
    
    # Test filter by component_id (reverse join)
    print_info("Testing filter by component_id (reverse join)...")
    resp = requests.get(f"{BASE_URL}/style-component-mapping?component_id={component_id}", headers=headers)
    
    if resp.status_code != 200:
        print_fail(f"Filter by component_id failed: {resp.status_code}")
        return False
    
    filtered = resp.json()
    
    # Should return all styles that use this component
    if len(filtered) == 0:
        print_fail("Filter by component_id returned no results")
        return False
    
    print_pass("Filter by component_id works (reverse join)")
    
    return True

# ============================================================================
# TEST 9: PUT /api/style-component-mapping/{id} - update
# ============================================================================
def test_update_bom_mapping(headers, mapping_id):
    print_test("TEST 9: PUT /api/style-component-mapping/{id} - update")
    
    payload = {
        "quantity_per_pair": 3.0,
        "wastage_percent": 10.0,
        "active": False
    }
    
    resp = requests.put(f"{BASE_URL}/style-component-mapping/{mapping_id}", json=payload, headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:500]}")
    
    if resp.status_code != 200:
        print_fail(f"Expected 200, got {resp.status_code}")
        return False
    
    print_pass("BOM mapping updated successfully")
    
    # Test non-existent id (should return 404)
    print_info("Testing non-existent id...")
    resp = requests.put(f"{BASE_URL}/style-component-mapping/000000000000000000000000", json=payload, headers=headers)
    
    if resp.status_code != 404:
        print_fail(f"Expected 404 for non-existent id, got {resp.status_code}")
        return False
    
    print_pass("Non-existent id correctly rejected with 404")
    
    return True

# ============================================================================
# TEST 10: DELETE /api/style-component-mapping/{id} - delete
# ============================================================================
def test_delete_bom_mapping(headers, mapping_id):
    print_test("TEST 10: DELETE /api/style-component-mapping/{id} - delete")
    
    resp = requests.delete(f"{BASE_URL}/style-component-mapping/{mapping_id}", headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:500]}")
    
    if resp.status_code != 200:
        print_fail(f"Expected 200, got {resp.status_code}")
        return False
    
    print_pass("BOM mapping deleted successfully")
    
    # Verify it's gone
    print_info("Verifying deletion...")
    resp = requests.get(f"{BASE_URL}/style-component-mapping", headers=headers)
    mappings = resp.json()
    
    found = any(m.get("id") == mapping_id for m in mappings)
    if found:
        print_fail("Mapping still exists after deletion")
        return False
    
    print_pass("Mapping verified deleted")
    
    # Test non-existent id (should return 404)
    print_info("Testing non-existent id...")
    resp = requests.delete(f"{BASE_URL}/style-component-mapping/000000000000000000000000", headers=headers)
    
    if resp.status_code != 404:
        print_fail(f"Expected 404 for non-existent id, got {resp.status_code}")
        return False
    
    print_pass("Non-existent id correctly rejected with 404")
    
    return True

# ============================================================================
# TEST 11: DELETE /api/components/{id} - soft delete with stock validation
# ============================================================================
def test_delete_component(headers):
    print_test("TEST 11: DELETE /api/components/{id} - soft delete with stock validation")
    
    # Create a component with zero stock
    timestamp = int(time.time())
    payload = {
        "component_code": f"DELETE-TEST-{timestamp}",
        "component_name": "Delete Test Component",
        "component_category": "Other",
        "color": "White",
        "size": "L",
        "current_stock": 0,
        "active": True
    }
    
    resp = requests.post(f"{BASE_URL}/components", json=payload, headers=headers)
    
    if resp.status_code not in [200, 201]:
        print_fail(f"Failed to create test component: {resp.status_code}")
        return False
    
    component_id = resp.json()["id"]
    print_info(f"Created test component: {component_id}")
    
    # Try to delete (should succeed since stock is zero)
    resp = requests.delete(f"{BASE_URL}/components/{component_id}", headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print_fail(f"Expected 200, got {resp.status_code}")
        return False
    
    print_pass("Component with zero stock deleted successfully")
    
    # Create another component with non-zero stock
    payload2 = {
        "component_code": f"DELETE-TEST-2-{timestamp}",
        "component_name": "Delete Test Component 2",
        "component_category": "Other",
        "color": "Black",
        "size": "M",
        "current_stock": 50,
        "active": True
    }
    
    resp = requests.post(f"{BASE_URL}/components", json=payload2, headers=headers)
    component_id2 = resp.json()["id"]
    
    # Try to delete (should fail with 400)
    print_info("Testing delete with non-zero stock (should fail)...")
    resp = requests.delete(f"{BASE_URL}/components/{component_id2}", headers=headers)
    
    if resp.status_code != 400:
        print_fail(f"Expected 400 for delete with non-zero stock, got {resp.status_code}")
        return False
    
    print_pass("Delete with non-zero stock correctly rejected with 400")
    
    # Zero out the stock via adjustment
    print_info("Zeroing out stock via adjustment...")
    adj_payload = {
        "component_id": component_id2,
        "movement_type": "adjustment",
        "quantity": 50,
        "adjustment_dir": "decrease",
        "reference_type": "manual",
        "notes": "Zero out for deletion"
    }
    
    resp = requests.post(f"{BASE_URL}/components/movements", json=adj_payload, headers=headers)
    
    if resp.status_code not in [200, 201]:
        print_fail(f"Failed to zero out stock: {resp.status_code}")
        return False
    
    # Now try to delete again (should succeed)
    print_info("Retrying delete after zeroing stock...")
    resp = requests.delete(f"{BASE_URL}/components/{component_id2}", headers=headers)
    
    if resp.status_code != 200:
        print_fail(f"Expected 200 after zeroing stock, got {resp.status_code}")
        return False
    
    print_pass("Delete succeeded after zeroing stock via adjustment")
    
    return True

# ============================================================================
# TEST 12: Regression smoke - previously-passing endpoints
# ============================================================================
def test_regression_smoke(headers, style_id):
    print_test("TEST 12: Regression smoke - previously-passing endpoints")
    
    # Test 1: GET /api/styles
    print_info("Testing GET /api/styles...")
    resp = requests.get(f"{BASE_URL}/styles", headers=headers)
    
    if resp.status_code != 200:
        print_fail(f"GET /api/styles failed: {resp.status_code}")
        return False
    
    print_pass("GET /api/styles works")
    
    # Test 2: GET /api/fg-inventory
    print_info("Testing GET /api/fg-inventory...")
    resp = requests.get(f"{BASE_URL}/fg-inventory", headers=headers)
    
    if resp.status_code != 200:
        print_fail(f"GET /api/fg-inventory failed: {resp.status_code}")
        return False
    
    print_pass("GET /api/fg-inventory works")
    
    # Test 3: GET /api/sku-map
    print_info("Testing GET /api/sku-map...")
    resp = requests.get(f"{BASE_URL}/sku-map", headers=headers)
    
    if resp.status_code != 200:
        print_fail(f"GET /api/sku-map failed: {resp.status_code}")
        return False
    
    print_pass("GET /api/sku-map works")
    
    # Test 4: GET /api/style-lifecycle/{style_id}
    print_info("Testing GET /api/style-lifecycle/{style_id}...")
    resp = requests.get(f"{BASE_URL}/style-lifecycle/{style_id}", headers=headers)
    
    if resp.status_code != 200:
        print_fail(f"GET /api/style-lifecycle failed: {resp.status_code}")
        return False
    
    print_pass("GET /api/style-lifecycle works")
    
    # Test 5: GET /api/styles/online
    print_info("Testing GET /api/styles/online...")
    resp = requests.get(f"{BASE_URL}/styles/online", headers=headers)
    
    if resp.status_code != 200:
        print_fail(f"GET /api/styles/online failed: {resp.status_code}")
        return False
    
    print_pass("GET /api/styles/online works")
    
    print_pass("All regression smoke tests passed")
    return True

# ============================================================================
# MAIN TEST RUNNER
# ============================================================================
def main():
    print("\n" + "="*80)
    print("BACKEND PHASE 6.1 COMPONENT INVENTORY TEST SUITE")
    print("="*80)
    print(f"Backend URL: {BASE_URL}")
    print(f"Test credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print("="*80)
    
    # Login
    access_token = login()
    if not access_token:
        print("\n❌ CRITICAL: Login failed, cannot continue")
        sys.exit(1)
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # Get or create a style
    style_id, style_code = get_or_create_style(headers)
    if not style_id:
        print("\n❌ CRITICAL: Failed to get/create style, cannot continue")
        sys.exit(1)
    
    # Run tests
    results = {}
    
    # Test 1: Create component
    success, component_id = test_create_component(headers)
    results["test_1_create_component"] = success
    if not success:
        print("\n❌ CRITICAL: Component creation failed, cannot continue")
        sys.exit(1)
    
    # Test 2: List components
    results["test_2_list_components"] = test_list_components(headers, component_id)
    
    # Test 3: Update component
    results["test_3_update_component"] = test_update_component(headers, component_id)
    
    # Test 4: Bulk matrix
    success, bulk_component_id = test_bulk_matrix(headers)
    results["test_4_bulk_matrix"] = success
    if not success:
        print("\n❌ WARNING: Bulk matrix failed, using original component for movement tests")
        bulk_component_id = component_id
    
    # Test 5: Component movements (all 8 types)
    results["test_5_component_movements"] = test_component_movements(headers, bulk_component_id)
    
    # Test 6: List movements
    results["test_6_list_movements"] = test_list_movements(headers, bulk_component_id)
    
    # Test 7: Create BOM mapping
    success, mapping_id = test_create_bom_mapping(headers, style_id, component_id)
    results["test_7_create_bom_mapping"] = success
    if not success:
        print("\n❌ WARNING: BOM mapping creation failed, skipping mapping tests")
        mapping_id = None
    
    # Test 8: List BOM mapping
    if mapping_id:
        results["test_8_list_bom_mapping"] = test_list_bom_mapping(headers, style_id, component_id)
    
    # Test 9: Update BOM mapping
    if mapping_id:
        results["test_9_update_bom_mapping"] = test_update_bom_mapping(headers, mapping_id)
    
    # Test 10: Delete BOM mapping
    if mapping_id:
        results["test_10_delete_bom_mapping"] = test_delete_bom_mapping(headers, mapping_id)
    
    # Test 11: Delete component
    results["test_11_delete_component"] = test_delete_component(headers)
    
    # Test 12: Regression smoke
    results["test_12_regression_smoke"] = test_regression_smoke(headers, style_id)
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print("="*80)
    print(f"TOTAL: {passed}/{total} tests passed")
    print("="*80)
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
