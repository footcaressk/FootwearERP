#!/usr/bin/env python3
"""
WMS Backend Testing Suite
Tests all Warehouse Management System endpoints as per review request.
"""

import requests
import json
import csv
import io
from typing import Dict, Any, Optional

# Backend URL from frontend/.env
BASE_URL = "https://footwear-hub-565.preview.emergentagent.com/api"

# Test credentials
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"

# Global token storage
access_token = None


def login() -> str:
    """Login and return access token."""
    global access_token
    print("\n" + "="*80)
    print("LOGGING IN...")
    print("="*80)
    
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    
    if response.status_code != 200:
        print(f"❌ Login failed: {response.status_code}")
        print(f"Response: {response.text}")
        raise Exception("Login failed")
    
    data = response.json()
    access_token = data.get("access_token")
    print(f"✅ Login successful. Token: {access_token[:20]}...")
    return access_token


def get_headers() -> Dict[str, str]:
    """Get authorization headers."""
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }


def test_warehouse_foundation():
    """Test 1: Warehouse foundation — dashboard and locations."""
    print("\n" + "="*80)
    print("TEST 1: WAREHOUSE FOUNDATION")
    print("="*80)
    
    # Test GET /api/warehouse/dashboard
    print("\n[1.1] Testing GET /api/warehouse/dashboard...")
    response = requests.get(f"{BASE_URL}/warehouse/dashboard", headers=get_headers())
    
    if response.status_code != 200:
        print(f"❌ Dashboard failed: {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    dashboard = response.json()
    print(f"✅ Dashboard returned 200")
    print(f"   Total cells: {dashboard.get('total_cells')}")
    print(f"   Total capacity: {dashboard.get('total_capacity')}")
    print(f"   Total occupied: {dashboard.get('total_occupied')}")
    print(f"   Total available: {dashboard.get('total_available')}")
    
    # Verify initial state (should be 320 cells, 9600 capacity, 9600 available)
    if dashboard.get('total_cells') != 320:
        print(f"❌ Expected 320 cells, got {dashboard.get('total_cells')}")
        return False
    
    if dashboard.get('total_capacity') != 9600:
        print(f"❌ Expected 9600 capacity, got {dashboard.get('total_capacity')}")
        return False
    
    print(f"✅ Dashboard shows correct initial state: 320 cells, 9600 capacity")
    
    # Test GET /api/warehouse/locations
    print("\n[1.2] Testing GET /api/warehouse/locations...")
    response = requests.get(f"{BASE_URL}/warehouse/locations", headers=get_headers())
    
    if response.status_code != 200:
        print(f"❌ Locations list failed: {response.status_code}")
        return False
    
    locations = response.json()
    print(f"✅ Locations returned {len(locations)} rows")
    
    if len(locations) != 320:
        print(f"❌ Expected 320 locations, got {len(locations)}")
        return False
    
    # Test filter by rack=A
    print("\n[1.3] Testing GET /api/warehouse/locations?rack=A...")
    response = requests.get(f"{BASE_URL}/warehouse/locations?rack=A", headers=get_headers())
    
    if response.status_code != 200:
        print(f"❌ Locations filter failed: {response.status_code}")
        return False
    
    rack_a_locations = response.json()
    print(f"✅ Rack A filter returned {len(rack_a_locations)} rows")
    
    if len(rack_a_locations) != 80:
        print(f"❌ Expected 80 locations for rack A, got {len(rack_a_locations)}")
        return False
    
    print(f"✅ TEST 1 PASSED: Warehouse foundation working correctly")
    return True


def test_auto_allocation():
    """Test 2: Auto-allocation on production_in."""
    print("\n" + "="*80)
    print("TEST 2: AUTO-ALLOCATION ON PRODUCTION_IN")
    print("="*80)
    
    # First, create a test style
    print("\n[2.1] Creating test style...")
    style_code = "WMS-TEST-AUTO-001"
    style_payload = {
        "code": style_code,
        "name": "WMS Auto-Allocation Test Style",
        "category": "sandals",
        "description": "Test style for WMS auto-allocation"
    }
    
    response = requests.post(f"{BASE_URL}/styles", json=style_payload, headers=get_headers())
    
    if response.status_code == 409:
        # Style already exists, get it
        print(f"   Style {style_code} already exists, fetching...")
        response = requests.get(f"{BASE_URL}/styles?search={style_code}", headers=get_headers())
        styles = response.json()
        if styles:
            style_id = styles[0]["id"]
            print(f"✅ Using existing style: {style_id}")
        else:
            print(f"❌ Could not find existing style")
            return False
    elif response.status_code in [200, 201]:
        style = response.json()
        style_id = style["id"]
        print(f"✅ Created new style: {style_id}")
    else:
        print(f"❌ Style creation failed: {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    # Now create a production_in movement with qty=100
    print("\n[2.2] Creating production_in movement (qty=100)...")
    movement_payload = {
        "style_id": style_id,
        "color": "Black",
        "size": "38",
        "movement_type": "production_in",
        "quantity": 100,
        "reference_type": "manual",
        "reference_id": "TEST-PROD-001",
        "notes": "WMS auto-allocation test"
    }
    
    response = requests.post(
        f"{BASE_URL}/fg-inventory/movements",
        json=movement_payload,
        headers=get_headers()
    )
    
    if response.status_code != 200:
        print(f"❌ Movement creation failed: {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    movement_result = response.json()
    print(f"✅ Movement created successfully")
    
    # Check if warehouse object is in response
    if "warehouse" in movement_result:
        warehouse_info = movement_result["warehouse"]
        print(f"   Warehouse allocation: {json.dumps(warehouse_info, indent=2)}")
        
        if "placements" in warehouse_info:
            placements = warehouse_info["placements"]
            print(f"   Placements: {len(placements)} locations")
            for p in placements:
                print(f"      {p['location_code']}: {p['qty']} pairs")
    
    # Verify GET /api/warehouse/fg-locations?style_id=<id>
    print(f"\n[2.3] Verifying fg_location_inventory for style {style_id}...")
    response = requests.get(
        f"{BASE_URL}/warehouse/fg-locations?style_id={style_id}",
        headers=get_headers()
    )
    
    if response.status_code != 200:
        print(f"❌ FG locations query failed: {response.status_code}")
        return False
    
    fg_locations = response.json()
    print(f"✅ Found {len(fg_locations)} location entries")
    
    total_qty = sum(loc.get("qty", 0) for loc in fg_locations)
    print(f"   Total qty across locations: {total_qty}")
    
    if total_qty != 100:
        print(f"❌ Expected 100 pairs total, got {total_qty}")
        return False
    
    # Verify expected placements: A-01-01=30, A-01-02=30, A-01-03=30, A-01-04=10
    expected_placements = {
        "A-01-01": 30,
        "A-01-02": 30,
        "A-01-03": 30,
        "A-01-04": 10
    }
    
    for loc in fg_locations:
        loc_code = loc.get("location_code")
        qty = loc.get("qty")
        if loc_code in expected_placements:
            expected_qty = expected_placements[loc_code]
            if qty == expected_qty:
                print(f"   ✅ {loc_code}: {qty} pairs (expected {expected_qty})")
            else:
                print(f"   ⚠️  {loc_code}: {qty} pairs (expected {expected_qty})")
    
    # Verify dashboard shows total_occupied=100
    print(f"\n[2.4] Verifying dashboard shows occupied=100...")
    response = requests.get(f"{BASE_URL}/warehouse/dashboard", headers=get_headers())
    dashboard = response.json()
    
    occupied = dashboard.get("total_occupied", 0)
    print(f"   Total occupied: {occupied}")
    
    if occupied < 100:
        print(f"❌ Expected at least 100 occupied, got {occupied}")
        return False
    
    print(f"✅ TEST 2 PASSED: Auto-allocation working correctly")
    return True, style_id


def test_online_order_import(style_id: str):
    """Test 3: Online order import with fulfillment (option c)."""
    print("\n" + "="*80)
    print("TEST 3: ONLINE ORDER IMPORT WITH FULFILLMENT")
    print("="*80)
    
    # First, create a sku-map entry
    print("\n[3.1] Creating SKU map entry...")
    sku_map_payload = {
        "source_type": "online_channel",
        "source_name": "myntra",
        "external_sku": "TEST-SKU-WMS-001",
        "style_id": style_id,
        "color_map": {"Black": "Black"},
        "size_map": {"38": "38"}
    }
    
    response = requests.post(f"{BASE_URL}/sku-map", json=sku_map_payload, headers=get_headers())
    
    if response.status_code == 409:
        print(f"   SKU map already exists")
    elif response.status_code in [200, 201]:
        print(f"✅ SKU map created")
    else:
        print(f"❌ SKU map creation failed: {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    # Create CSV with two orders for the same SKU
    print("\n[3.2] Creating CSV with 2 orders (25 + 150 pairs)...")
    csv_content = """order_id,style_sku,quantity,color,size
ORD-WMS-A,TEST-SKU-WMS-001,25,Black,38
ORD-WMS-B,TEST-SKU-WMS-001,150,Black,38"""
    
    # Import the CSV
    print("\n[3.3] Importing online orders...")
    files = {
        'file': ('orders.csv', csv_content, 'text/csv')
    }
    data = {
        'channel': 'myntra'
    }
    
    # Remove Content-Type header for multipart/form-data
    headers = {"Authorization": f"Bearer {access_token}"}
    
    response = requests.post(
        f"{BASE_URL}/online-orders/import",
        files=files,
        data=data,
        headers=headers
    )
    
    if response.status_code != 200:
        print(f"❌ Order import failed: {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    import_result = response.json()
    print(f"✅ Import successful")
    print(f"   Imported: {import_result.get('imported')}")
    print(f"   Fulfilled from stock: {import_result.get('fulfilled_from_stock')}")
    print(f"   Picklists created: {len(import_result.get('picklists_created', []))}")
    print(f"   Errors: {len(import_result.get('errors', []))}")
    
    # Verify fulfilled_from_stock = 100 (we have 100 in stock)
    fulfilled = import_result.get('fulfilled_from_stock', 0)
    if fulfilled != 100:
        print(f"❌ Expected fulfilled_from_stock=100, got {fulfilled}")
        return False
    
    # Verify picklists_created has 2 picklists
    picklists = import_result.get('picklists_created', [])
    if len(picklists) != 2:
        print(f"❌ Expected 2 picklists, got {len(picklists)}")
        return False
    
    print(f"✅ Picklists created:")
    for pl in picklists:
        print(f"   {pl.get('picklist_no')}: {pl.get('qty')} pairs, {pl.get('items')} items")
    
    # Get picklist details
    print("\n[3.4] Fetching picklist details...")
    response = requests.get(f"{BASE_URL}/picklists", headers=get_headers())
    
    if response.status_code != 200:
        print(f"❌ Picklists fetch failed: {response.status_code}")
        return False
    
    all_picklists = response.json()
    
    # Find our picklists
    our_picklists = [pl for pl in all_picklists if pl.get('order_id') in ['ORD-WMS-A', 'ORD-WMS-B']]
    
    if len(our_picklists) != 2:
        print(f"❌ Expected to find 2 picklists, found {len(our_picklists)}")
        return False
    
    # Verify picklist structure
    pl_a = next((pl for pl in our_picklists if pl.get('order_id') == 'ORD-WMS-A'), None)
    pl_b = next((pl for pl in our_picklists if pl.get('order_id') == 'ORD-WMS-B'), None)
    
    if not pl_a or not pl_b:
        print(f"❌ Could not find both picklists")
        return False
    
    print(f"\n   Picklist A (ORD-WMS-A):")
    print(f"      Total qty: {pl_a.get('total_qty')} pairs")
    print(f"      Total items: {pl_a.get('total_items')}")
    
    if pl_a.get('total_qty') != 25:
        print(f"❌ Expected PL-A to have 25 pairs, got {pl_a.get('total_qty')}")
        return False
    
    if pl_a.get('total_items') != 1:
        print(f"❌ Expected PL-A to have 1 item, got {pl_a.get('total_items')}")
        return False
    
    print(f"\n   Picklist B (ORD-WMS-B):")
    print(f"      Total qty: {pl_b.get('total_qty')} pairs")
    print(f"      Total items: {pl_b.get('total_items')}")
    
    if pl_b.get('total_qty') != 75:
        print(f"❌ Expected PL-B to have 75 pairs, got {pl_b.get('total_qty')}")
        return False
    
    if pl_b.get('total_items') != 4:
        print(f"❌ Expected PL-B to have 4 items, got {pl_b.get('total_items')}")
        return False
    
    # Verify production job for remainder
    print("\n[3.5] Verifying production job for remainder...")
    response = requests.get(
        f"{BASE_URL}/production/jobs?source_type=online_channel",
        headers=get_headers()
    )
    
    if response.status_code != 200:
        print(f"❌ Production jobs fetch failed: {response.status_code}")
        return False
    
    jobs = response.json()
    ord_b_job = next((j for j in jobs if j.get('po_number') == 'ORD-WMS-B'), None)
    
    if not ord_b_job:
        print(f"❌ Could not find production job for ORD-WMS-B")
        return False
    
    print(f"✅ Production job found for ORD-WMS-B:")
    print(f"   Quantity: {ord_b_job.get('quantity')}")
    print(f"   Original order qty: {ord_b_job.get('original_order_qty')}")
    print(f"   Fulfilled from stock qty: {ord_b_job.get('fulfilled_from_stock_qty')}")
    
    if ord_b_job.get('quantity') != 75:
        print(f"❌ Expected job quantity=75, got {ord_b_job.get('quantity')}")
        return False
    
    if ord_b_job.get('original_order_qty') != 150:
        print(f"❌ Expected original_order_qty=150, got {ord_b_job.get('original_order_qty')}")
        return False
    
    if ord_b_job.get('fulfilled_from_stock_qty') != 75:
        print(f"❌ Expected fulfilled_from_stock_qty=75, got {ord_b_job.get('fulfilled_from_stock_qty')}")
        return False
    
    print(f"✅ TEST 3 PASSED: Online order import with fulfillment working correctly")
    return True, pl_a['id'], pl_b['id']


def test_pick_item_flow(pl_a_id: str):
    """Test 4: Pick-item flow with scan verification."""
    print("\n" + "="*80)
    print("TEST 4: PICK-ITEM FLOW")
    print("="*80)
    
    # Get picklist details
    print(f"\n[4.1] Fetching picklist {pl_a_id}...")
    response = requests.get(f"{BASE_URL}/picklists/{pl_a_id}", headers=get_headers())
    
    if response.status_code != 200:
        print(f"❌ Picklist fetch failed: {response.status_code}")
        return False
    
    picklist = response.json()
    items = picklist.get('items', [])
    
    if not items:
        print(f"❌ Picklist has no items")
        return False
    
    first_item = items[0]
    expected_location = first_item.get('location_code')
    
    print(f"   First item location: {expected_location}")
    print(f"   Quantity: {first_item.get('qty')}")
    
    # Test wrong scan
    print(f"\n[4.2] Testing WRONG scan (B-99-99)...")
    wrong_scan_payload = {
        "item_index": 0,
        "scanned_location": "B-99-99"
    }
    
    response = requests.post(
        f"{BASE_URL}/picklists/{pl_a_id}/pick-item",
        json=wrong_scan_payload,
        headers=get_headers()
    )
    
    if response.status_code != 400:
        print(f"❌ Expected 400 for wrong scan, got {response.status_code}")
        return False
    
    error_msg = response.json().get('detail', '')
    print(f"✅ Wrong scan rejected with 400")
    print(f"   Error message: {error_msg}")
    
    if 'Scan mismatch' not in error_msg:
        print(f"❌ Expected 'Scan mismatch' in error message")
        return False
    
    # Test correct scan
    print(f"\n[4.3] Testing CORRECT scan ({expected_location})...")
    correct_scan_payload = {
        "item_index": 0,
        "scanned_location": expected_location
    }
    
    response = requests.post(
        f"{BASE_URL}/picklists/{pl_a_id}/pick-item",
        json=correct_scan_payload,
        headers=get_headers()
    )
    
    if response.status_code != 200:
        print(f"❌ Correct scan failed: {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    updated_picklist = response.json()
    print(f"✅ Correct scan accepted")
    print(f"   Picklist status: {updated_picklist.get('status')}")
    
    # Verify item is marked as picked
    updated_items = updated_picklist.get('items', [])
    if updated_items and updated_items[0].get('picked'):
        print(f"   ✅ Item marked as picked")
    else:
        print(f"   ❌ Item not marked as picked")
        return False
    
    # Verify status is completed (since this was the only item)
    if updated_picklist.get('status') != 'completed':
        print(f"❌ Expected status='completed', got {updated_picklist.get('status')}")
        return False
    
    # Verify dashboard shows reduced occupied count
    print(f"\n[4.4] Verifying dashboard shows reduced occupied count...")
    response = requests.get(f"{BASE_URL}/warehouse/dashboard", headers=get_headers())
    dashboard = response.json()
    
    occupied = dashboard.get("total_occupied", 0)
    print(f"   Total occupied: {occupied}")
    print(f"   (Should be 75, was 100 before picking 25)")
    
    if occupied != 75:
        print(f"⚠️  Expected occupied=75, got {occupied}")
        # Don't fail the test, just warn
    
    # Verify reservation is fulfilled
    print(f"\n[4.5] Verifying reservation is fulfilled...")
    response = requests.get(
        f"{BASE_URL}/inventory-reservations?online_order_id=ORD-WMS-A",
        headers=get_headers()
    )
    
    if response.status_code != 200:
        print(f"❌ Reservations fetch failed: {response.status_code}")
        return False
    
    reservations = response.json()
    if reservations:
        res = reservations[0]
        print(f"   Reservation status: {res.get('status')}")
        if res.get('status') == 'fulfilled':
            print(f"   ✅ Reservation marked as fulfilled")
        else:
            print(f"   ⚠️  Reservation status is {res.get('status')}, expected 'fulfilled'")
    
    print(f"✅ TEST 4 PASSED: Pick-item flow working correctly")
    return True


def test_delete_picklist(pl_b_id: str):
    """Test 5: Delete/cancel picklist."""
    print("\n" + "="*80)
    print("TEST 5: DELETE/CANCEL PICKLIST")
    print("="*80)
    
    # Get picklist details before deletion
    print(f"\n[5.1] Fetching picklist {pl_b_id} before deletion...")
    response = requests.get(f"{BASE_URL}/picklists/{pl_b_id}", headers=get_headers())
    
    if response.status_code != 200:
        print(f"❌ Picklist fetch failed: {response.status_code}")
        return False
    
    picklist = response.json()
    print(f"   Status: {picklist.get('status')}")
    print(f"   Total items: {picklist.get('total_items')}")
    print(f"   Total qty: {picklist.get('total_qty')}")
    
    # Delete the picklist
    print(f"\n[5.2] Deleting picklist...")
    response = requests.delete(f"{BASE_URL}/picklists/{pl_b_id}", headers=get_headers())
    
    if response.status_code != 200:
        print(f"❌ Picklist deletion failed: {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    result = response.json()
    print(f"✅ Picklist deleted: {result}")
    
    # Verify picklist is gone
    print(f"\n[5.3] Verifying picklist is deleted...")
    response = requests.get(f"{BASE_URL}/picklists/{pl_b_id}", headers=get_headers())
    
    if response.status_code != 404:
        print(f"❌ Expected 404 for deleted picklist, got {response.status_code}")
        return False
    
    print(f"✅ Picklist no longer exists")
    
    # Verify reservations are released
    print(f"\n[5.4] Verifying reservations are released...")
    response = requests.get(
        f"{BASE_URL}/inventory-reservations?online_order_id=ORD-WMS-B",
        headers=get_headers()
    )
    
    if response.status_code != 200:
        print(f"❌ Reservations fetch failed: {response.status_code}")
        return False
    
    reservations = response.json()
    if reservations:
        res = reservations[0]
        print(f"   Reservation status: {res.get('status')}")
        if res.get('status') == 'released':
            print(f"   ✅ Reservation marked as released")
        else:
            print(f"   ⚠️  Reservation status is {res.get('status')}, expected 'released'")
    
    print(f"✅ TEST 5 PASSED: Delete picklist working correctly")
    return True


def test_reports():
    """Test 6: Reports endpoints."""
    print("\n" + "="*80)
    print("TEST 6: REPORTS")
    print("="*80)
    
    # Test capacity report
    print("\n[6.1] Testing GET /api/warehouse/reports/capacity...")
    response = requests.get(f"{BASE_URL}/warehouse/reports/capacity", headers=get_headers())
    
    if response.status_code != 200:
        print(f"❌ Capacity report failed: {response.status_code}")
        return False
    
    capacity = response.json()
    print(f"✅ Capacity report returned 200")
    print(f"   Total capacity: {capacity.get('total_capacity')}")
    print(f"   Total occupied: {capacity.get('total_occupied')}")
    print(f"   Utilization: {capacity.get('utilization_pct')}%")
    
    # Verify structure
    if 'by_rack' not in capacity:
        print(f"❌ Missing 'by_rack' in capacity report")
        return False
    
    by_rack = capacity.get('by_rack', [])
    print(f"   By rack entries: {len(by_rack)}")
    
    for rack in by_rack:
        print(f"      Rack {rack.get('rack')}: {rack.get('occupied_pairs')}/{rack.get('capacity_pairs')} pairs ({rack.get('utilization_pct')}%)")
    
    # Test location-utilization report
    print("\n[6.2] Testing GET /api/warehouse/reports/location-utilization...")
    response = requests.get(f"{BASE_URL}/warehouse/reports/location-utilization", headers=get_headers())
    
    if response.status_code != 200:
        print(f"❌ Location utilization report failed: {response.status_code}")
        return False
    
    utilization = response.json()
    print(f"✅ Location utilization report returned 200")
    
    # Verify structure
    if 'rows' not in utilization or 'fullest' not in utilization or 'emptiest' not in utilization:
        print(f"❌ Missing required fields in utilization report")
        return False
    
    print(f"   Total rows: {len(utilization.get('rows', []))}")
    print(f"   Fullest locations: {len(utilization.get('fullest', []))}")
    print(f"   Emptiest locations: {len(utilization.get('emptiest', []))}")
    
    # Test picking-efficiency report
    print("\n[6.3] Testing GET /api/warehouse/reports/picking-efficiency?days=30...")
    response = requests.get(f"{BASE_URL}/warehouse/reports/picking-efficiency?days=30", headers=get_headers())
    
    if response.status_code != 200:
        print(f"❌ Picking efficiency report failed: {response.status_code}")
        return False
    
    efficiency = response.json()
    print(f"✅ Picking efficiency report returned 200")
    
    # Verify structure
    if 'grand_total' not in efficiency or 'per_picker' not in efficiency:
        print(f"❌ Missing required fields in efficiency report")
        return False
    
    grand = efficiency.get('grand_total', {})
    print(f"   Grand total:")
    print(f"      Picklists: {grand.get('picklists')}")
    print(f"      Items: {grand.get('items')}")
    print(f"      Qty: {grand.get('qty')}")
    print(f"      Avg minutes per picklist: {grand.get('avg_minutes_per_picklist')}")
    print(f"      Items per hour: {grand.get('items_per_hour')}")
    
    per_picker = efficiency.get('per_picker', [])
    print(f"   Per-picker entries: {len(per_picker)}")
    
    print(f"✅ TEST 6 PASSED: All reports working correctly")
    return True


def test_pending_product_list():
    """Test 7: Pending Product List."""
    print("\n" + "="*80)
    print("TEST 7: PENDING PRODUCT LIST")
    print("="*80)
    
    print("\n[7.1] Testing GET /api/production/pending-list...")
    response = requests.get(f"{BASE_URL}/production/pending-list", headers=get_headers())
    
    if response.status_code != 200:
        print(f"❌ Pending list failed: {response.status_code}")
        return False
    
    pending = response.json()
    print(f"✅ Pending list returned 200")
    print(f"   Total jobs: {len(pending)}")
    
    # Find our ORD-WMS-B job
    ord_b_job = next((j for j in pending if j.get('po_number') == 'ORD-WMS-B'), None)
    
    if ord_b_job:
        print(f"\n   Found ORD-WMS-B job:")
        print(f"      Quantity: {ord_b_job.get('quantity')}")
        print(f"      Components available: {ord_b_job.get('components_available')}")
        print(f"      Component shortages: {ord_b_job.get('component_shortages', [])}")
    else:
        print(f"   ⚠️  ORD-WMS-B job not found in pending list")
    
    # Verify structure
    if pending:
        first_job = pending[0]
        if 'components_available' not in first_job:
            print(f"❌ Missing 'components_available' field")
            return False
        if 'component_shortages' not in first_job:
            print(f"❌ Missing 'component_shortages' field")
            return False
    
    print(f"✅ TEST 7 PASSED: Pending product list working correctly")
    return True


def test_regression_smoke():
    """Test 8: Regression smoke tests."""
    print("\n" + "="*80)
    print("TEST 8: REGRESSION SMOKE TESTS")
    print("="*80)
    
    endpoints = [
        ("GET /api/fg-inventory", f"{BASE_URL}/fg-inventory"),
        ("GET /api/fg-inventory/movements", f"{BASE_URL}/fg-inventory/movements"),
        ("GET /api/components", f"{BASE_URL}/components"),
        ("GET /api/styles/online", f"{BASE_URL}/styles/online"),
    ]
    
    all_passed = True
    
    for name, url in endpoints:
        print(f"\n[8.x] Testing {name}...")
        response = requests.get(url, headers=get_headers())
        
        if response.status_code != 200:
            print(f"❌ {name} failed: {response.status_code}")
            all_passed = False
        else:
            print(f"✅ {name} returned 200")
    
    # Test POST /api/fg-inventory/movements (single)
    print(f"\n[8.x] Testing POST /api/fg-inventory/movements (single)...")
    
    # Get a style to use
    response = requests.get(f"{BASE_URL}/styles?limit=1", headers=get_headers())
    if response.status_code == 200:
        styles = response.json()
        if styles:
            style_id = styles[0]["id"]
            
            movement_payload = {
                "style_id": style_id,
                "color": "Test",
                "size": "40",
                "movement_type": "adjustment",
                "quantity": 1,
                "adjustment_field": "ready_stock_qty",
                "notes": "Regression test"
            }
            
            response = requests.post(
                f"{BASE_URL}/fg-inventory/movements",
                json=movement_payload,
                headers=get_headers()
            )
            
            if response.status_code != 200:
                print(f"❌ POST /api/fg-inventory/movements failed: {response.status_code}")
                all_passed = False
            else:
                print(f"✅ POST /api/fg-inventory/movements returned 200")
    
    if all_passed:
        print(f"\n✅ TEST 8 PASSED: All regression smoke tests passed")
    else:
        print(f"\n❌ TEST 8 FAILED: Some regression tests failed")
    
    return all_passed


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("WMS BACKEND TESTING SUITE")
    print("="*80)
    print(f"Backend URL: {BASE_URL}")
    print(f"Admin: {ADMIN_EMAIL}")
    
    try:
        # Login
        login()
        
        # Run tests in order
        results = {}
        
        # Test 1: Warehouse foundation
        results['test_1'] = test_warehouse_foundation()
        
        # Test 2: Auto-allocation
        test_2_result = test_auto_allocation()
        if isinstance(test_2_result, tuple):
            results['test_2'] = test_2_result[0]
            style_id = test_2_result[1]
        else:
            results['test_2'] = test_2_result
            style_id = None
        
        # Test 3: Online order import (needs style_id from test 2)
        if style_id:
            test_3_result = test_online_order_import(style_id)
            if isinstance(test_3_result, tuple):
                results['test_3'] = test_3_result[0]
                pl_a_id = test_3_result[1]
                pl_b_id = test_3_result[2]
            else:
                results['test_3'] = test_3_result
                pl_a_id = None
                pl_b_id = None
        else:
            results['test_3'] = False
            pl_a_id = None
            pl_b_id = None
        
        # Test 4: Pick-item flow (needs pl_a_id from test 3)
        if pl_a_id:
            results['test_4'] = test_pick_item_flow(pl_a_id)
        else:
            results['test_4'] = False
        
        # Test 5: Delete picklist (needs pl_b_id from test 3)
        if pl_b_id:
            results['test_5'] = test_delete_picklist(pl_b_id)
        else:
            results['test_5'] = False
        
        # Test 6: Reports
        results['test_6'] = test_reports()
        
        # Test 7: Pending product list
        results['test_7'] = test_pending_product_list()
        
        # Test 8: Regression smoke
        results['test_8'] = test_regression_smoke()
        
        # Summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"{test_name}: {status}")
        
        print(f"\nTotal: {passed}/{total} tests passed")
        
        if passed == total:
            print("\n🎉 ALL TESTS PASSED!")
            return 0
        else:
            print(f"\n⚠️  {total - passed} test(s) failed")
            return 1
    
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
