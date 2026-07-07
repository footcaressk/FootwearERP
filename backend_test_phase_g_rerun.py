#!/usr/bin/env python3
"""
Phase G — Re-run of failed test after FLL→FL bug fix.

Tests the new known_sku_prefix_replacements field and apply_prefix_replacements() helper.
"""
import os
import sys
import requests
import io
import csv
from datetime import datetime

# Backend URL from environment
BACKEND_URL = os.getenv("REACT_APP_BACKEND_URL", "https://0a21f0e6-1b8f-4e57-80f2-927e6ec8a7dc.preview.emergentagent.com")
BASE_URL = f"{BACKEND_URL}/api"

# Admin credentials
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"

# Global session
session = requests.Session()
access_token = None


def login():
    """Login as admin and store access token."""
    global access_token
    resp = session.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    access_token = data.get("access_token")
    assert access_token, "No access_token in login response"
    session.headers.update({"Authorization": f"Bearer {access_token}"})
    print("✅ Logged in as admin")


def test_1_get_myntra_config():
    """Test 1: GET /api/order-import-format-configs/myntra — should return known_sku_prefixes_to_strip=[] and known_sku_prefix_replacements={'FLL':'FL'}"""
    print("\n=== TEST 1: GET /api/order-import-format-configs/myntra ===")
    resp = session.get(f"{BASE_URL}/order-import-format-configs/myntra")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    
    # Check is_picklist
    assert data.get("is_picklist") == True, f"Expected is_picklist=true, got {data.get('is_picklist')}"
    print(f"✅ is_picklist: {data.get('is_picklist')}")
    
    # Check known_sku_prefixes_to_strip is empty
    strip_list = data.get("known_sku_prefixes_to_strip", [])
    assert strip_list == [], f"Expected known_sku_prefixes_to_strip=[], got {strip_list}"
    print(f"✅ known_sku_prefixes_to_strip: {strip_list} (empty as expected)")
    
    # Check known_sku_prefix_replacements has FLL→FL
    replacements = data.get("known_sku_prefix_replacements", {})
    assert replacements.get("FLL") == "FL", f"Expected known_sku_prefix_replacements={{'FLL':'FL'}}, got {replacements}"
    print(f"✅ known_sku_prefix_replacements: {replacements}")
    
    print("✅ TEST 1 PASSED")
    return data


def test_2_get_flipkart_config():
    """Test 2: GET /api/order-import-format-configs/flipkart — should return known_sku_prefixes_to_strip=['TH'] and known_sku_prefix_replacements={}"""
    print("\n=== TEST 2: GET /api/order-import-format-configs/flipkart ===")
    resp = session.get(f"{BASE_URL}/order-import-format-configs/flipkart")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    
    # Check is_picklist
    assert data.get("is_picklist") == False, f"Expected is_picklist=false, got {data.get('is_picklist')}"
    print(f"✅ is_picklist: {data.get('is_picklist')}")
    
    # Check known_sku_prefixes_to_strip has TH
    strip_list = data.get("known_sku_prefixes_to_strip", [])
    assert "TH" in strip_list, f"Expected 'TH' in known_sku_prefixes_to_strip, got {strip_list}"
    print(f"✅ known_sku_prefixes_to_strip: {strip_list}")
    
    # Check known_sku_prefix_replacements is empty
    replacements = data.get("known_sku_prefix_replacements", {})
    assert replacements == {}, f"Expected known_sku_prefix_replacements={{}}, got {replacements}"
    print(f"✅ known_sku_prefix_replacements: {replacements} (empty as expected)")
    
    print("✅ TEST 2 PASSED")
    return data


def test_3_myntra_picklist_dry_run():
    """Test 3: POST /api/online-orders/import-configured?platform=myntra&dry_run=true — THE CRITICAL FIX TEST"""
    print("\n=== TEST 3: POST /api/online-orders/import-configured (Myntra picklist dry_run) ===")
    print("This is the CRITICAL test that failed before the fix.")
    
    # Create CSV with Myntra picklist format
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=[
        "myntraSkuCode", "sellerSkuCode", "productDescription", "quantity", "binBarcode"
    ])
    writer.writeheader()
    writer.writerow({
        "myntraSkuCode": "MYN001",
        "sellerSkuCode": "FLL_AK_005_SL-7",
        "productDescription": "Test Product A",
        "quantity": "2",
        "binBarcode": "BIN001"
    })
    writer.writerow({
        "myntraSkuCode": "MYN002",
        "sellerSkuCode": "FL_AK_27_LV-5",
        "productDescription": "Test Product B",
        "quantity": "1",
        "binBarcode": "BIN002"
    })
    
    csv_content = csv_buffer.getvalue()
    
    # Upload with filename OP20625445.csv
    files = {
        "file": ("OP20625445.csv", csv_content, "text/csv")
    }
    
    resp = session.post(
        f"{BASE_URL}/online-orders/import-configured",
        params={"platform": "myntra", "dry_run": "true"},
        files=files
    )
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    
    # Check picklist_batch_id
    assert data.get("picklist_batch_id") == "OP20625445", f"Expected picklist_batch_id='OP20625445', got {data.get('picklist_batch_id')}"
    print(f"✅ picklist_batch_id: {data.get('picklist_batch_id')}")
    
    # Check is_picklist
    assert data.get("is_picklist") == True, f"Expected is_picklist=true, got {data.get('is_picklist')}"
    print(f"✅ is_picklist: {data.get('is_picklist')}")
    
    # Check dry_run
    assert data.get("dry_run") == True, f"Expected dry_run=true, got {data.get('dry_run')}"
    print(f"✅ dry_run: {data.get('dry_run')}")
    
    # Check rows
    rows = data.get("rows", [])
    assert len(rows) >= 2, f"Expected at least 2 rows, got {len(rows)}"
    print(f"✅ rows count: {len(rows)}")
    
    # Row 0: FLL_AK_005_SL-7 → should become FL_AK_005_SL-7
    row0 = rows[0]
    print(f"\n--- Row 0 (FLL prefix test) ---")
    print(f"  leaf_sku_raw: {row0.get('leaf_sku_raw')}")
    print(f"  leaf_sku_replaced_prefix: {row0.get('leaf_sku_replaced_prefix')}")
    print(f"  leaf_sku_stripped_prefix: {row0.get('leaf_sku_stripped_prefix')}")
    print(f"  leaf_sku: {row0.get('leaf_sku')}")
    print(f"  qty: {row0.get('qty')}")
    
    assert row0.get("leaf_sku_raw") == "FLL_AK_005_SL-7", f"Expected leaf_sku_raw='FLL_AK_005_SL-7', got {row0.get('leaf_sku_raw')}"
    assert row0.get("leaf_sku_replaced_prefix") == "FLL", f"Expected leaf_sku_replaced_prefix='FLL', got {row0.get('leaf_sku_replaced_prefix')}"
    assert row0.get("leaf_sku") == "FL_AK_005_SL-7", f"❌ CRITICAL: Expected leaf_sku='FL_AK_005_SL-7', got {row0.get('leaf_sku')}"
    assert row0.get("qty") == 2, f"Expected qty=2, got {row0.get('qty')}"
    print(f"✅ Row 0: FLL_AK_005_SL-7 → FL_AK_005_SL-7 (FLL replaced with FL)")
    
    # Row 1: FL_AK_27_LV-5 → should remain FL_AK_27_LV-5
    row1 = rows[1]
    print(f"\n--- Row 1 (no replacement needed) ---")
    print(f"  leaf_sku_raw: {row1.get('leaf_sku_raw')}")
    print(f"  leaf_sku_replaced_prefix: {row1.get('leaf_sku_replaced_prefix')}")
    print(f"  leaf_sku_stripped_prefix: {row1.get('leaf_sku_stripped_prefix')}")
    print(f"  leaf_sku: {row1.get('leaf_sku')}")
    print(f"  qty: {row1.get('qty')}")
    
    assert row1.get("leaf_sku_raw") == "FL_AK_27_LV-5", f"Expected leaf_sku_raw='FL_AK_27_LV-5', got {row1.get('leaf_sku_raw')}"
    assert row1.get("leaf_sku_replaced_prefix") in [None, ""], f"Expected leaf_sku_replaced_prefix=null/empty, got {row1.get('leaf_sku_replaced_prefix')}"
    assert row1.get("leaf_sku") == "FL_AK_27_LV-5", f"Expected leaf_sku='FL_AK_27_LV-5', got {row1.get('leaf_sku')}"
    assert row1.get("qty") == 1, f"Expected qty=1, got {row1.get('qty')}"
    print(f"✅ Row 1: FL_AK_27_LV-5 → FL_AK_27_LV-5 (no replacement)")
    
    print("\n✅ TEST 3 PASSED — THE CRITICAL FIX IS WORKING!")
    return data


def test_4_flipkart_regression_dry_run():
    """Test 4: Regression — POST /api/online-orders/import-configured?platform=flipkart&dry_run=true — TH stripping must still work"""
    print("\n=== TEST 4: POST /api/online-orders/import-configured (Flipkart regression dry_run) ===")
    
    # Create CSV with Flipkart format
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=[
        "Order Id", "ORDER ITEM ID", "Shipment ID", "Ordered On", "SKU", 
        "Product", "Quantity", "Selling Price Per Item", "Invoice Amount",
        "Order State", "Tracking ID", "Dispatch by date", "Buyer name",
        "City", "State", "PIN Code"
    ])
    writer.writeheader()
    writer.writerow({
        "Order Id": "FK001",
        "ORDER ITEM ID": "'438019315969082100",  # Note the apostrophe
        "Shipment ID": "SHIP001",
        "Ordered On": "2024-01-01",
        "SKU": "THFL_AK_048_BG_37",  # TH prefix should be stripped
        "Product": "Test Product",
        "Quantity": "1",
        "Selling Price Per Item": "1000",
        "Invoice Amount": "1000",
        "Order State": "Approved",
        "Tracking ID": "TRACK001",
        "Dispatch by date": "2024-01-05",
        "Buyer name": "Test Buyer",
        "City": "Mumbai",
        "State": "Maharashtra",
        "PIN Code": "400001"
    })
    
    csv_content = csv_buffer.getvalue()
    
    files = {
        "file": ("flipkart_orders.csv", csv_content, "text/csv")
    }
    
    resp = session.post(
        f"{BASE_URL}/online-orders/import-configured",
        params={"platform": "flipkart", "dry_run": "true"},
        files=files
    )
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    
    # Check is_picklist
    assert data.get("is_picklist") == False, f"Expected is_picklist=false, got {data.get('is_picklist')}"
    print(f"✅ is_picklist: {data.get('is_picklist')}")
    
    # Check picklist_batch_id is null
    assert data.get("picklist_batch_id") in [None, ""], f"Expected picklist_batch_id=null, got {data.get('picklist_batch_id')}"
    print(f"✅ picklist_batch_id: {data.get('picklist_batch_id')} (null as expected)")
    
    # Check rows
    rows = data.get("rows", [])
    assert len(rows) >= 1, f"Expected at least 1 row, got {len(rows)}"
    
    row0 = rows[0]
    print(f"\n--- Row 0 (TH stripping test) ---")
    print(f"  order_id: {row0.get('order_id')}")
    print(f"  order_item_id: {row0.get('order_item_id')}")
    print(f"  leaf_sku_raw: {row0.get('leaf_sku_raw')}")
    print(f"  leaf_sku_replaced_prefix: {row0.get('leaf_sku_replaced_prefix')}")
    print(f"  leaf_sku_stripped_prefix: {row0.get('leaf_sku_stripped_prefix')}")
    print(f"  leaf_sku: {row0.get('leaf_sku')}")
    
    # Check order_item_id apostrophe stripped
    assert row0.get("order_item_id") == "438019315969082100", f"Expected order_item_id='438019315969082100' (apostrophe stripped), got {row0.get('order_item_id')}"
    print(f"✅ order_item_id apostrophe stripped: {row0.get('order_item_id')}")
    
    # Check TH prefix stripped
    assert row0.get("leaf_sku_stripped_prefix") == "TH", f"Expected leaf_sku_stripped_prefix='TH', got {row0.get('leaf_sku_stripped_prefix')}"
    assert row0.get("leaf_sku") == "FL_AK_048_BG_37", f"Expected leaf_sku='FL_AK_048_BG_37', got {row0.get('leaf_sku')}"
    print(f"✅ TH prefix stripped: THFL_AK_048_BG_37 → FL_AK_048_BG_37")
    
    # Check leaf_sku_replaced_prefix is null (no replacements for Flipkart)
    assert row0.get("leaf_sku_replaced_prefix") in [None, ""], f"Expected leaf_sku_replaced_prefix=null, got {row0.get('leaf_sku_replaced_prefix')}"
    print(f"✅ leaf_sku_replaced_prefix: {row0.get('leaf_sku_replaced_prefix')} (null as expected)")
    
    print("\n✅ TEST 4 PASSED — Flipkart TH stripping still works")
    return data


def test_5_flipkart_commit_mode():
    """Test 5: Regression — POST /api/online-orders/import-configured?platform=flipkart&dry_run=false — commit mode"""
    print("\n=== TEST 5: POST /api/online-orders/import-configured (Flipkart commit mode) ===")
    
    # Create CSV with Flipkart format
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=[
        "Order Id", "ORDER ITEM ID", "Shipment ID", "Ordered On", "SKU", 
        "Product", "Quantity", "Selling Price Per Item", "Invoice Amount",
        "Order State", "Tracking ID", "Dispatch by date", "Buyer name",
        "City", "State", "PIN Code"
    ])
    writer.writeheader()
    writer.writerow({
        "Order Id": f"FK_COMMIT_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "ORDER ITEM ID": f"ITEM_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "Shipment ID": "SHIP_COMMIT",
        "Ordered On": "2024-01-01",
        "SKU": "THFL_AK_048_BG_37",
        "Product": "Test Product Commit",
        "Quantity": "1",
        "Selling Price Per Item": "1000",
        "Invoice Amount": "1000",
        "Order State": "Approved",
        "Tracking ID": "TRACK_COMMIT",
        "Dispatch by date": "2024-01-05",
        "Buyer name": "Test Buyer",
        "City": "Mumbai",
        "State": "Maharashtra",
        "PIN Code": "400001"
    })
    
    csv_content = csv_buffer.getvalue()
    
    files = {
        "file": ("flipkart_commit.csv", csv_content, "text/csv")
    }
    
    resp = session.post(
        f"{BASE_URL}/online-orders/import-configured",
        params={"platform": "flipkart", "dry_run": "false"},
        files=files
    )
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    
    # Check dry_run is false
    assert data.get("dry_run") == False, f"Expected dry_run=false, got {data.get('dry_run')}"
    print(f"✅ dry_run: {data.get('dry_run')}")
    
    # Check import_batch_id exists
    import_batch_id = data.get("import_batch_id")
    assert import_batch_id, f"Expected import_batch_id, got {import_batch_id}"
    assert import_batch_id.startswith("IMP_flipkart_"), f"Expected import_batch_id to start with 'IMP_flipkart_', got {import_batch_id}"
    print(f"✅ import_batch_id: {import_batch_id}")
    
    # Check committed stats
    committed = data.get("committed", {})
    print(f"✅ committed.orders_created: {committed.get('orders_created')}")
    print(f"✅ committed.items_created: {committed.get('items_created')}")
    print(f"✅ committed.exceptions_queued: {committed.get('exceptions_queued')}")
    
    assert committed.get("orders_created") >= 1, f"Expected orders_created >= 1, got {committed.get('orders_created')}"
    assert committed.get("items_created") >= 1, f"Expected items_created >= 1, got {committed.get('items_created')}"
    
    print("\n✅ TEST 5 PASSED — Flipkart commit mode still works")
    return data


def test_6_new_endpoint_capability():
    """Test 6: POST /api/order-import-format-configs with known_sku_prefix_replacements, then PUT to modify"""
    print("\n=== TEST 6: POST /api/order-import-format-configs (new endpoint capability) ===")
    
    # Create a test platform with replacements (use 'other' as platform since it's an enum)
    test_platform = "other"
    
    # First, delete if exists
    try:
        session.delete(f"{BASE_URL}/order-import-format-configs/{test_platform}")
    except:
        pass
    
    create_body = {
        "platform": test_platform,
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 0,
        "column_map": {
            "leaf_sku": "SKU",
            "order_id": "Order ID",
            "qty": "Quantity"
        },
        "known_sku_prefixes_to_strip": [],
        "known_sku_prefix_replacements": {"XXX": "YY"},
        "is_picklist": False,
        "active": True,
        "notes": "Test platform for known_sku_prefix_replacements"
    }
    
    resp = session.post(f"{BASE_URL}/order-import-format-configs", json=create_body)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    
    print(f"✅ Created test platform: {test_platform}")
    print(f"  known_sku_prefix_replacements: {data.get('known_sku_prefix_replacements')}")
    
    # Verify the field round-trips correctly
    assert data.get("known_sku_prefix_replacements") == {"XXX": "YY"}, f"Expected {{'XXX':'YY'}}, got {data.get('known_sku_prefix_replacements')}"
    
    # Now PUT to modify it
    update_body = {
        "known_sku_prefix_replacements": {"AAA": "BB", "CCC": "DD"}
    }
    
    resp = session.put(f"{BASE_URL}/order-import-format-configs/{test_platform}", json=update_body)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    
    print(f"✅ Updated test platform: {test_platform}")
    print(f"  known_sku_prefix_replacements: {data.get('known_sku_prefix_replacements')}")
    
    # Verify the update
    assert data.get("known_sku_prefix_replacements") == {"AAA": "BB", "CCC": "DD"}, f"Expected {{'AAA':'BB','CCC':'DD'}}, got {data.get('known_sku_prefix_replacements')}"
    
    # GET to verify persistence
    resp = session.get(f"{BASE_URL}/order-import-format-configs/{test_platform}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    
    assert data.get("known_sku_prefix_replacements") == {"AAA": "BB", "CCC": "DD"}, f"Expected {{'AAA':'BB','CCC':'DD'}}, got {data.get('known_sku_prefix_replacements')}"
    print(f"✅ GET verified persistence: {data.get('known_sku_prefix_replacements')}")
    
    print("\n✅ TEST 6 PASSED — New endpoint capability works")
    return data


def main():
    """Run all tests."""
    print("=" * 80)
    print("Phase G — Re-run of failed test after FLL→FL bug fix")
    print("=" * 80)
    
    try:
        login()
        
        test_1_get_myntra_config()
        test_2_get_flipkart_config()
        test_3_myntra_picklist_dry_run()
        test_4_flipkart_regression_dry_run()
        test_5_flipkart_commit_mode()
        test_6_new_endpoint_capability()
        
        print("\n" + "=" * 80)
        print("✅ ALL 6/6 TESTS PASSED")
        print("=" * 80)
        print("\nSUMMARY:")
        print("✅ Test 1: GET /api/order-import-format-configs/myntra — known_sku_prefixes_to_strip=[], known_sku_prefix_replacements={'FLL':'FL'}")
        print("✅ Test 2: GET /api/order-import-format-configs/flipkart — known_sku_prefixes_to_strip=['TH'], known_sku_prefix_replacements={}")
        print("✅ Test 3: Myntra picklist dry_run — FLL_AK_005_SL-7 → FL_AK_005_SL-7 (THE CRITICAL FIX WORKS!)")
        print("✅ Test 4: Flipkart regression dry_run — TH stripping still works, apostrophe stripping still works")
        print("✅ Test 5: Flipkart commit mode — creates online_orders/online_order_items/online_order_exceptions with import_batch_id")
        print("✅ Test 6: New endpoint capability — known_sku_prefix_replacements field round-trips correctly via POST/PUT/GET")
        print("\n🎉 THE BUG FIX IS COMPLETE AND VERIFIED!")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
