#!/usr/bin/env python3
"""
Phase H — Myntra Daily Dispatch Import Testing
Tests the role-based order_import_format_configs extension and dispatch-import endpoint.
"""

import requests
import sys
import io
from typing import Dict, Any

# Backend URL from environment
BASE_URL = "https://footwear-hub-565.preview.emergentagent.com/api"

# Admin credentials
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"

# Global session with auth token
session = requests.Session()


def login() -> str:
    """Login and return access token."""
    resp = session.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    token = data.get("access_token")
    assert token, "No access_token in login response"
    session.headers.update({"Authorization": f"Bearer {token}"})
    return token


def test_1_get_all_configs_with_role():
    """Test 1: GET /api/order-import-format-configs should return configs with role field."""
    print("\n=== TEST 1: GET all configs with role field ===")
    resp = session.get(f"{BASE_URL}/order-import-format-configs")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    configs = resp.json()
    assert isinstance(configs, list), "Expected list of configs"
    assert len(configs) >= 3, f"Expected at least 3 configs (flipkart/order, myntra/order, myntra/dispatch), got {len(configs)}"
    
    # Check that all configs have role field
    for cfg in configs:
        assert "role" in cfg, f"Config {cfg.get('platform')} missing 'role' field"
        assert cfg["role"] in ["order", "dispatch"], f"Invalid role: {cfg['role']}"
    
    # Find the expected configs
    platforms_roles = [(c["platform"], c["role"]) for c in configs]
    print(f"Found configs: {platforms_roles}")
    
    assert ("flipkart", "order") in platforms_roles, "Missing flipkart/order config"
    assert ("myntra", "order") in platforms_roles, "Missing myntra/order config"
    assert ("myntra", "dispatch") in platforms_roles, "Missing myntra/dispatch config"
    
    print("✅ TEST 1 PASSED: All configs have role field, minimum required configs present")
    return configs


def test_2_get_configs_role_dispatch_filter():
    """Test 2: GET /api/order-import-format-configs?role=dispatch should only return dispatch configs."""
    print("\n=== TEST 2: GET configs with role=dispatch filter ===")
    resp = session.get(f"{BASE_URL}/order-import-format-configs?role=dispatch")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    configs = resp.json()
    assert isinstance(configs, list), "Expected list of configs"
    assert len(configs) >= 1, "Expected at least 1 dispatch config (myntra/dispatch)"
    
    # All should be dispatch role
    for cfg in configs:
        assert cfg["role"] == "dispatch", f"Expected role=dispatch, got {cfg['role']} for {cfg['platform']}"
    
    # Should include myntra/dispatch
    platforms = [c["platform"] for c in configs]
    assert "myntra" in platforms, "Missing myntra in dispatch configs"
    
    print(f"✅ TEST 2 PASSED: Found {len(configs)} dispatch config(s): {platforms}")
    return configs


def test_3_get_configs_role_order_filter():
    """Test 3: GET /api/order-import-format-configs?role=order should NOT include dispatch configs."""
    print("\n=== TEST 3: GET configs with role=order filter ===")
    resp = session.get(f"{BASE_URL}/order-import-format-configs?role=order")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    configs = resp.json()
    assert isinstance(configs, list), "Expected list of configs"
    
    # All should be order role
    for cfg in configs:
        assert cfg["role"] == "order", f"Expected role=order, got {cfg['role']} for {cfg['platform']}"
    
    # Should NOT include myntra/dispatch
    platforms_roles = [(c["platform"], c["role"]) for c in configs]
    assert ("myntra", "dispatch") not in platforms_roles, "myntra/dispatch should not be in order-role filter"
    
    # Should include myntra/order
    platforms = [c["platform"] for c in configs]
    assert "myntra" in platforms, "Missing myntra in order configs"
    
    print(f"✅ TEST 3 PASSED: Found {len(configs)} order config(s), myntra/dispatch correctly excluded")


def test_4_get_canonical_fields_dispatch():
    """Test 4: GET /api/order-import-format-configs/_meta/canonical-fields?role=dispatch."""
    print("\n=== TEST 4: GET canonical fields for dispatch role ===")
    resp = session.get(f"{BASE_URL}/order-import-format-configs/_meta/canonical-fields?role=dispatch")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    assert data["role"] == "dispatch", f"Expected role=dispatch, got {data['role']}"
    
    fields = data["canonical_fields"]
    assert isinstance(fields, list), "Expected list of canonical fields"
    
    # Check for required dispatch fields
    required_fields = [
        "order_id", "order_release_id", "leaf_sku", "channel_sku",
        "packed_on", "status", "mrp", "selling_value",
        "cgst", "sgst", "igst", "tracking_id",
        "destination_city", "destination_state", "destination_pincode",
        "store_packet_id"
    ]
    
    for field in required_fields:
        assert field in fields, f"Missing required dispatch field: {field}"
    
    print(f"✅ TEST 4 PASSED: Dispatch canonical fields include all {len(required_fields)} required fields")


def test_5_get_canonical_fields_order_default():
    """Test 5: GET /api/order-import-format-configs/_meta/canonical-fields (no role, defaults to order)."""
    print("\n=== TEST 5: GET canonical fields with no role param (defaults to order) ===")
    resp = session.get(f"{BASE_URL}/order-import-format-configs/_meta/canonical-fields")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    # Should default to order role
    assert data["role"] == "order", f"Expected role=order (default), got {data['role']}"
    
    fields = data["canonical_fields"]
    assert isinstance(fields, list), "Expected list of canonical fields"
    
    # Check for some order fields (18 total)
    required_order_fields = [
        "order_id", "order_item_id", "shipment_id", "leaf_sku"
    ]
    
    for field in required_order_fields:
        assert field in fields, f"Missing required order field: {field}"
    
    print(f"✅ TEST 5 PASSED: Order canonical fields returned by default (no role param)")


def test_6_get_myntra_order_config():
    """Test 6: GET /api/order-import-format-configs/myntra (no role, defaults to order)."""
    print("\n=== TEST 6: GET myntra config without role param (should return order config) ===")
    resp = session.get(f"{BASE_URL}/order-import-format-configs/myntra")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    cfg = resp.json()
    assert cfg["platform"] == "myntra", f"Expected platform=myntra, got {cfg['platform']}"
    assert cfg["role"] == "order", f"Expected role=order, got {cfg['role']}"
    assert cfg.get("is_picklist") == True, f"Expected is_picklist=true for myntra/order"
    
    # Check known_sku_prefix_replacements
    replacements = cfg.get("known_sku_prefix_replacements", {})
    assert "FLL" in replacements, "Missing FLL in known_sku_prefix_replacements"
    assert replacements["FLL"] == "FL", f"Expected FLL->FL, got FLL->{replacements['FLL']}"
    
    print(f"✅ TEST 6 PASSED: myntra/order config returned with is_picklist=true, FLL->FL replacement")


def test_7_get_myntra_dispatch_config():
    """Test 7: GET /api/order-import-format-configs/myntra?role=dispatch."""
    print("\n=== TEST 7: GET myntra dispatch config ===")
    resp = session.get(f"{BASE_URL}/order-import-format-configs/myntra?role=dispatch")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    cfg = resp.json()
    assert cfg["platform"] == "myntra", f"Expected platform=myntra, got {cfg['platform']}"
    assert cfg["role"] == "dispatch", f"Expected role=dispatch, got {cfg['role']}"
    assert cfg.get("is_picklist") == False, f"Expected is_picklist=false for dispatch config"
    
    # Check column_map
    column_map = cfg.get("column_map", {})
    expected_mappings = {
        "leaf_sku": "Seller_sku_code",
        "packed_on": "Packed On",
        "order_release_id": "Order_release_id",
        "order_id": "Order id",
        "channel_sku": "Myntra SKU code",
        "tracking_id": "Tracking_id",
        "destination_city": "Destination City",
        "mrp": "MRP",
        "selling_value": "Selling value"
    }
    
    for canon_field, excel_col in expected_mappings.items():
        assert canon_field in column_map, f"Missing {canon_field} in column_map"
        assert column_map[canon_field] == excel_col, \
            f"Expected column_map.{canon_field}='{excel_col}', got '{column_map[canon_field]}'"
    
    # Check known_sku_prefix_replacements
    replacements = cfg.get("known_sku_prefix_replacements", {})
    assert "FLL" in replacements, "Missing FLL in known_sku_prefix_replacements"
    assert replacements["FLL"] == "FL", f"Expected FLL->FL, got FLL->{replacements['FLL']}"
    
    # Check seeded and active
    assert cfg.get("seeded") == True, "Expected seeded=true"
    assert cfg.get("active") == True, "Expected active=true"
    
    print(f"✅ TEST 7 PASSED: myntra/dispatch config has correct column_map, FLL->FL replacement, seeded=true, active=true")


def test_8_create_flipkart_dispatch_config():
    """Test 8: POST /api/order-import-format-configs to create flipkart/dispatch (should not conflict with flipkart/order)."""
    print("\n=== TEST 8: POST new flipkart/dispatch config ===")
    
    payload = {
        "platform": "flipkart",
        "role": "dispatch",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "column_map": {
            "order_id": "Order Id",
            "leaf_sku": "Seller SKU",
            "packed_on": "Packed Date",
            "qty": "Qty"
        },
        "is_picklist": False,
        "active": True
    }
    
    resp = session.post(f"{BASE_URL}/order-import-format-configs", json=payload)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    assert "id" in data, "Expected 'id' in response"
    flipkart_dispatch_id = data["id"]
    
    # Verify by GET
    resp2 = session.get(f"{BASE_URL}/order-import-format-configs/flipkart?role=dispatch")
    assert resp2.status_code == 200, f"Expected 200 on GET, got {resp2.status_code}: {resp2.text}"
    
    cfg = resp2.json()
    assert cfg["platform"] == "flipkart", f"Expected platform=flipkart"
    assert cfg["role"] == "dispatch", f"Expected role=dispatch"
    assert cfg["column_map"]["leaf_sku"] == "Seller SKU", "Column map mismatch"
    
    print(f"✅ TEST 8 PASSED: Created flipkart/dispatch config (id={flipkart_dispatch_id}), no conflict with flipkart/order")
    return flipkart_dispatch_id


def test_9_duplicate_flipkart_dispatch():
    """Test 9: POST duplicate flipkart/dispatch should return 409."""
    print("\n=== TEST 9: POST duplicate flipkart/dispatch (expect 409) ===")
    
    payload = {
        "platform": "flipkart",
        "role": "dispatch",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "column_map": {
            "order_id": "Order Id",
            "leaf_sku": "Seller SKU",
            "packed_on": "Packed Date",
            "qty": "Qty"
        },
        "is_picklist": False,
        "active": True
    }
    
    resp = session.post(f"{BASE_URL}/order-import-format-configs", json=payload)
    assert resp.status_code == 409, f"Expected 409 (duplicate), got {resp.status_code}: {resp.text}"
    
    print(f"✅ TEST 9 PASSED: Duplicate flipkart/dispatch correctly rejected with 409")


def test_10_update_flipkart_dispatch_active():
    """Test 10: PUT /api/order-import-format-configs/flipkart?role=dispatch with active=false."""
    print("\n=== TEST 10: PUT flipkart/dispatch to set active=false ===")
    
    payload = {"active": False}
    resp = session.put(f"{BASE_URL}/order-import-format-configs/flipkart?role=dispatch", json=payload)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    # Verify
    resp2 = session.get(f"{BASE_URL}/order-import-format-configs/flipkart?role=dispatch")
    assert resp2.status_code == 200, f"Expected 200 on GET, got {resp2.status_code}"
    
    cfg = resp2.json()
    assert cfg["active"] == False, f"Expected active=false, got {cfg['active']}"
    
    print(f"✅ TEST 10 PASSED: flipkart/dispatch active set to false")


def test_11_get_flipkart_dispatch_still_exists():
    """Test 11: GET /api/order-import-format-configs/flipkart?role=dispatch should still return doc (regardless of active)."""
    print("\n=== TEST 11: GET flipkart/dispatch (should exist even with active=false) ===")
    
    resp = session.get(f"{BASE_URL}/order-import-format-configs/flipkart?role=dispatch")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    cfg = resp.json()
    assert cfg["platform"] == "flipkart"
    assert cfg["role"] == "dispatch"
    assert cfg["active"] == False  # from previous test
    
    # Also verify flipkart/order is unaffected
    resp2 = session.get(f"{BASE_URL}/order-import-format-configs/flipkart")
    assert resp2.status_code == 200, f"Expected 200 for flipkart/order, got {resp2.status_code}"
    cfg2 = resp2.json()
    assert cfg2["role"] == "order", "flipkart/order should still exist"
    
    print(f"✅ TEST 11 PASSED: flipkart/dispatch still exists, flipkart/order unaffected")


def test_12_dispatch_import_unknown_platform():
    """Test 12: POST /api/online-orders/dispatch-import?platform=doesnotexist should return 400."""
    print("\n=== TEST 12: POST dispatch-import with unknown platform (expect 400) ===")
    
    # Create a minimal CSV
    csv_content = "col1,col2\nval1,val2\n"
    files = {"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    
    resp = session.post(
        f"{BASE_URL}/online-orders/dispatch-import?platform=doesnotexist&dry_run=true",
        files=files
    )
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    assert "dispatch-import config" in data.get("detail", "").lower(), \
        f"Expected helpful error message about missing config, got: {data.get('detail')}"
    
    print(f"✅ TEST 12 PASSED: Unknown platform correctly rejected with 400 and helpful message")


def test_13_dispatch_import_myntra_dry_run():
    """Test 13: POST /api/online-orders/dispatch-import?platform=myntra&dry_run=true with realistic CSV."""
    print("\n=== TEST 13: POST dispatch-import myntra dry_run=true ===")
    
    csv_content = """Packed On,Order id,Order_release_id,Destination City,Destination state,Destination pincode,Status,MRP,Myntra SKU code,Seller_sku_code,Store Packet ID,Selling value,CGST,SGST,IGST,Tracking_id
2026-07-05,BX10001,201234567,Mumbai,MH,400001,PACKED,2999,MYN-A1,FL_AK_005_SL-7,SP001,1899,50.5,50.5,0,TR9001
2026-07-05,BX10002,201234568,Delhi,DL,110001,PACKED,2999,MYN-A2,FLL_AK_005_SL-7,SP002,1899,50.5,50.5,0,TR9002
2026-07-05,BX10003,201234569,Bengaluru,KA,560001,PACKED,2500,MYN-B1,,SP003,1699,45,45,0,TR9003"""
    
    files = {"file": ("Packed_order_data.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    
    resp = session.post(
        f"{BASE_URL}/online-orders/dispatch-import?platform=myntra&dry_run=true",
        files=files
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    
    # Check top-level fields
    assert data["platform"] == "myntra", f"Expected platform=myntra"
    assert data["role"] == "dispatch", f"Expected role=dispatch"
    assert data["dry_run"] == True, f"Expected dry_run=true"
    assert data["filename"] == "Packed_order_data.csv", f"Expected filename=Packed_order_data.csv"
    
    # Check stats
    stats = data["stats"]
    assert stats["total_rows_read"] == 3, f"Expected 3 rows, got {stats['total_rows_read']}"
    assert stats["empty_leaf_sku"] == 1, f"Expected 1 empty_leaf_sku, got {stats['empty_leaf_sku']}"
    assert stats["distinct_order_releases"] == 3, f"Expected 3 distinct order_releases, got {stats['distinct_order_releases']}"
    # matched will likely be 0 (no sku_map seeded for these values) - that's expected
    
    # Check committed is null in dry_run
    assert data["committed"] is None, "Expected committed=null in dry_run mode"
    
    # Check rows
    rows = data["rows"]
    assert len(rows) == 3, f"Expected 3 rows, got {len(rows)}"
    
    # Row 0 (row 2 in CSV): FL_AK_005_SL-7 (no prefix replacement)
    row0 = rows[0]
    assert row0["order_id"] == "BX10001", f"Row 0: Expected order_id=BX10001"
    assert row0["order_release_id"] == "201234567", f"Row 0: Expected order_release_id=201234567"
    assert row0["leaf_sku_raw"] == "FL_AK_005_SL-7", f"Row 0: Expected leaf_sku_raw=FL_AK_005_SL-7"
    assert row0["leaf_sku"] == "FL_AK_005_SL-7", f"Row 0: Expected leaf_sku=FL_AK_005_SL-7"
    assert row0["leaf_sku_replaced_prefix"] is None, f"Row 0: Expected no prefix replacement"
    assert row0["packed_on"] == "2026-07-05", f"Row 0: Expected packed_on=2026-07-05"
    assert row0["tracking_id"] == "TR9001", f"Row 0: Expected tracking_id=TR9001"
    assert row0["destination_city"] == "Mumbai", f"Row 0: Expected destination_city=Mumbai"
    assert row0["destination_state"] == "MH", f"Row 0: Expected destination_state=MH"
    assert row0["destination_pincode"] == "400001", f"Row 0: Expected destination_pincode=400001"
    assert row0["mrp"] == 2999.0, f"Row 0: Expected mrp=2999.0"
    assert row0["selling_value"] == 1899.0, f"Row 0: Expected selling_value=1899.0"
    assert row0["channel_sku"] == "MYN-A1", f"Row 0: Expected channel_sku=MYN-A1"
    assert row0["store_packet_id"] == "SP001", f"Row 0: Expected store_packet_id=SP001"
    assert row0["qty"] == 1, f"Row 0: Expected qty=1"
    
    # Row 1 (row 3 in CSV): FLL_AK_005_SL-7 (FLL->FL replacement)
    row1 = rows[1]
    assert row1["leaf_sku_raw"] == "FLL_AK_005_SL-7", f"Row 1: Expected leaf_sku_raw=FLL_AK_005_SL-7"
    assert row1["leaf_sku_replaced_prefix"] == "FLL", f"Row 1: Expected leaf_sku_replaced_prefix=FLL"
    assert row1["leaf_sku"] == "FL_AK_005_SL-7", f"Row 1: Expected leaf_sku=FL_AK_005_SL-7 (after FLL->FL replacement)"
    
    # Row 2 (row 4 in CSV): empty leaf_sku
    row2 = rows[2]
    assert row2["leaf_sku_raw"] == "", f"Row 2: Expected empty leaf_sku_raw"
    flags = row2.get("flags", [])
    assert "empty_leaf_sku" in flags, f"Row 2: Expected 'empty_leaf_sku' in flags"
    assert row2.get("exception_reason") == "leaf_sku column is empty", f"Row 2: Expected exception_reason about empty leaf_sku"
    # But other fields should still be populated
    assert row2["tracking_id"] == "TR9003", f"Row 2: Expected tracking_id=TR9003"
    assert row2["destination_city"] == "Bengaluru", f"Row 2: Expected destination_city=Bengaluru"
    assert row2["mrp"] == 2500.0, f"Row 2: Expected mrp=2500.0"
    
    print(f"✅ TEST 13 PASSED: Myntra dispatch dry_run parsed correctly with all canonical fields, FLL->FL replacement, empty_leaf_sku flagged")


def test_14_dispatch_import_myntra_commit():
    """Test 14: POST /api/online-orders/dispatch-import?platform=myntra&dry_run=false (commit mode)."""
    print("\n=== TEST 14: POST dispatch-import myntra dry_run=false (commit) ===")
    
    csv_content = """Packed On,Order id,Order_release_id,Destination City,Destination state,Destination pincode,Status,MRP,Myntra SKU code,Seller_sku_code,Store Packet ID,Selling value,CGST,SGST,IGST,Tracking_id
2026-07-05,BX10001,201234567,Mumbai,MH,400001,PACKED,2999,MYN-A1,FL_AK_005_SL-7,SP001,1899,50.5,50.5,0,TR9001
2026-07-05,BX10002,201234568,Delhi,DL,110001,PACKED,2999,MYN-A2,FLL_AK_005_SL-7,SP002,1899,50.5,50.5,0,TR9002
2026-07-05,BX10003,201234569,Bengaluru,KA,560001,PACKED,2500,MYN-B1,,SP003,1699,45,45,0,TR9003"""
    
    files = {"file": ("Packed_order_data.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    
    resp = session.post(
        f"{BASE_URL}/online-orders/dispatch-import?platform=myntra&dry_run=false",
        files=files
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    
    # Check top-level fields
    assert data["dry_run"] == False, f"Expected dry_run=false"
    assert "import_batch_id" in data, "Expected import_batch_id"
    assert data["import_batch_id"].startswith("DISP_myntra_"), f"Expected import_batch_id to start with DISP_myntra_"
    
    # Check committed object
    committed = data["committed"]
    assert committed is not None, "Expected committed object in commit mode"
    assert isinstance(committed, dict), "Expected committed to be a dict"
    
    # Check committed keys
    expected_keys = ["movements_posted", "implicit_reserves", "orders_upserted", "items_upserted", "already_dispatched", "exceptions_queued"]
    for key in expected_keys:
        assert key in committed, f"Missing key '{key}' in committed"
    
    # Since no seed data exists, ALL 3 rows should end up as exceptions
    # (2 with unmatched SKUs, 1 with empty leaf_sku)
    assert committed["exceptions_queued"] >= 3, \
        f"Expected at least 3 exceptions (no seed data), got {committed['exceptions_queued']}"
    assert committed["movements_posted"] == 0, \
        f"Expected 0 movements_posted (no seed data), got {committed['movements_posted']}"
    
    print(f"✅ TEST 14 PASSED: Myntra dispatch commit mode created import_batch_id, all rows went to exceptions (no seed data)")


def test_15_regression_order_import():
    """Test 15: Regression - POST /api/online-orders/import-configured?platform=myntra&dry_run=true (order-import path)."""
    print("\n=== TEST 15: REGRESSION - Order-import path still works after role migration ===")
    
    # Myntra picklist CSV format
    csv_content = """myntraSkuCode,sellerSkuCode,productDescription,quantity,binBarcode
MYN-TEST-001,FLL_AK_005_SL-7,Test Product,2,BIN001"""
    
    files = {"file": ("OP20625445.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    
    resp = session.post(
        f"{BASE_URL}/online-orders/import-configured?platform=myntra&dry_run=true",
        files=files
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    
    # Check that it's using the order/picklist config
    assert data.get("picklist_batch_id") == "OP20625445", f"Expected picklist_batch_id=OP20625445"
    assert data.get("is_picklist") == True, f"Expected is_picklist=true"
    
    # Check rows
    rows = data.get("rows", [])
    assert len(rows) >= 1, "Expected at least 1 row"
    
    row0 = rows[0]
    # Check FLL->FL replacement
    assert row0.get("leaf_sku_replaced_prefix") == "FLL", f"Expected leaf_sku_replaced_prefix=FLL"
    assert row0.get("leaf_sku") == "FL_AK_005_SL-7", f"Expected leaf_sku=FL_AK_005_SL-7 (after FLL->FL replacement)"
    assert row0.get("qty") == 2, f"Expected qty=2"
    
    print(f"✅ TEST 15 PASSED: Order-import regression successful - picklist_batch_id=OP20625445, is_picklist=true, FLL->FL replacement working, qty=2")


def run_all_tests():
    """Run all Phase H tests in sequence."""
    print("=" * 80)
    print("PHASE H — MYNTRA DAILY DISPATCH IMPORT TESTING")
    print("=" * 80)
    
    try:
        # Login
        print("\n=== LOGGING IN ===")
        login()
        print("✅ Login successful")
        
        # PART A — Config CRUD with role
        print("\n" + "=" * 80)
        print("PART A — CONFIG CRUD WITH ROLE")
        print("=" * 80)
        
        test_1_get_all_configs_with_role()
        test_2_get_configs_role_dispatch_filter()
        test_3_get_configs_role_order_filter()
        test_4_get_canonical_fields_dispatch()
        test_5_get_canonical_fields_order_default()
        test_6_get_myntra_order_config()
        test_7_get_myntra_dispatch_config()
        test_8_create_flipkart_dispatch_config()
        test_9_duplicate_flipkart_dispatch()
        test_10_update_flipkart_dispatch_active()
        test_11_get_flipkart_dispatch_still_exists()
        
        # PART B — Dispatch import endpoint
        print("\n" + "=" * 80)
        print("PART B — DISPATCH IMPORT ENDPOINT")
        print("=" * 80)
        
        test_12_dispatch_import_unknown_platform()
        test_13_dispatch_import_myntra_dry_run()
        test_14_dispatch_import_myntra_commit()
        
        # PART C — Regression
        print("\n" + "=" * 80)
        print("PART C — REGRESSION")
        print("=" * 80)
        
        test_15_regression_order_import()
        
        # Summary
        print("\n" + "=" * 80)
        print("✅ ALL 15 TESTS PASSED")
        print("=" * 80)
        print("\nCRITICAL ASSERTS VERIFIED:")
        print("  ✅ #7: Dispatch config has correct column_map")
        print("  ✅ #13: Dispatch dry_run canonical row structure with all descriptive fields + FLL→FL replacement")
        print("  ✅ #14: Dispatch commit creates exceptions instead of crashing (no seed data)")
        print("  ✅ #15: Order-import regression (role-based lookup didn't break existing flow)")
        print("\nNO ISSUES FOUND.")
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
