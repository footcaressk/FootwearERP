#!/usr/bin/env python3
"""
Phase G — Order/Picklist config-driven import regression test
Tests all order-import-format-configs CRUD endpoints and the
/online-orders/import-configured endpoint with both Flipkart (order mode)
and Myntra (picklist mode) CSV imports.
"""
import requests
import sys
import io
import csv
from typing import Dict, Any

# Backend URL from frontend/.env
BASE_URL = "https://0a21f0e6-1b8f-4e57-80f2-927e6ec8a7dc.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"

session = requests.Session()
access_token = None


def login():
    """Login as admin and store access token."""
    global access_token
    resp = session.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        print(f"❌ LOGIN FAILED: {resp.status_code} {resp.text}")
        sys.exit(1)
    data = resp.json()
    access_token = data.get("access_token")
    if not access_token:
        print(f"❌ LOGIN FAILED: No access_token in response")
        sys.exit(1)
    print(f"✅ Logged in as {ADMIN_EMAIL}")


def headers():
    """Return auth headers."""
    return {"Authorization": f"Bearer {access_token}"}


def test_1_get_all_configs():
    """Test 1: GET /api/order-import-format-configs should return seeded flipkart + myntra."""
    print("\n" + "="*80)
    print("TEST 1: GET /api/order-import-format-configs (list all)")
    print("="*80)
    
    resp = session.get(f"{BASE_URL}/order-import-format-configs", headers=headers())
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}")
        print(f"Response: {resp.text}")
        return False
    
    data = resp.json()
    print(f"Response: {len(data)} configs returned")
    
    # Should have at least 2 seeded configs: flipkart and myntra
    if len(data) < 2:
        print(f"❌ FAILED: Expected at least 2 configs, got {len(data)}")
        return False
    
    platforms = [c.get("platform") for c in data]
    print(f"Platforms: {platforms}")
    
    if "flipkart" not in platforms:
        print(f"❌ FAILED: 'flipkart' config not found")
        return False
    
    if "myntra" not in platforms:
        print(f"❌ FAILED: 'myntra' config not found")
        return False
    
    print(f"✅ TEST 1 PASSED: Found seeded flipkart and myntra configs")
    return True


def test_2_get_canonical_fields():
    """Test 2: GET /api/order-import-format-configs/_meta/canonical-fields."""
    print("\n" + "="*80)
    print("TEST 2: GET /api/order-import-format-configs/_meta/canonical-fields")
    print("="*80)
    
    resp = session.get(f"{BASE_URL}/order-import-format-configs/_meta/canonical-fields", headers=headers())
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}")
        print(f"Response: {resp.text}")
        return False
    
    data = resp.json()
    fields = data.get("canonical_fields", [])
    print(f"Canonical fields ({len(fields)}): {fields}")
    
    required_fields = [
        "order_id", "order_item_id", "shipment_id", "order_date", "dispatch_by_date",
        "leaf_sku", "myntra_sku_code", "product_title", "qty", "selling_price",
        "invoice_amount", "order_state", "tracking_id", "buyer_name", "city",
        "state", "pincode", "bin_barcode"
    ]
    
    for field in required_fields:
        if field not in fields:
            print(f"❌ FAILED: Required field '{field}' not in canonical_fields")
            return False
    
    print(f"✅ TEST 2 PASSED: All required canonical fields present")
    return True


def test_3_get_flipkart_config():
    """Test 3: GET /api/order-import-format-configs/flipkart."""
    print("\n" + "="*80)
    print("TEST 3: GET /api/order-import-format-configs/flipkart")
    print("="*80)
    
    resp = session.get(f"{BASE_URL}/order-import-format-configs/flipkart", headers=headers())
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}")
        print(f"Response: {resp.text}")
        return False
    
    data = resp.json()
    print(f"Platform: {data.get('platform')}")
    print(f"is_picklist: {data.get('is_picklist')}")
    print(f"known_sku_prefixes_to_strip: {data.get('known_sku_prefixes_to_strip')}")
    print(f"active: {data.get('active')}")
    print(f"seeded: {data.get('seeded')}")
    
    # Verify Flipkart config structure
    if data.get("platform") != "flipkart":
        print(f"❌ FAILED: Expected platform='flipkart', got '{data.get('platform')}'")
        return False
    
    if data.get("is_picklist") != False:
        print(f"❌ FAILED: Expected is_picklist=false for Flipkart")
        return False
    
    prefixes = data.get("known_sku_prefixes_to_strip", [])
    if "TH" not in prefixes:
        print(f"❌ FAILED: Expected 'TH' in known_sku_prefixes_to_strip, got {prefixes}")
        return False
    
    if data.get("active") != True:
        print(f"❌ FAILED: Expected active=true")
        return False
    
    if data.get("seeded") != True:
        print(f"❌ FAILED: Expected seeded=true")
        return False
    
    column_map = data.get("column_map", {})
    if column_map.get("leaf_sku") != "SKU":
        print(f"❌ FAILED: Expected column_map.leaf_sku='SKU', got '{column_map.get('leaf_sku')}'")
        return False
    
    if column_map.get("order_id") != "Order Id":
        print(f"❌ FAILED: Expected column_map.order_id='Order Id', got '{column_map.get('order_id')}'")
        return False
    
    if column_map.get("order_item_id") != "ORDER ITEM ID":
        print(f"❌ FAILED: Expected column_map.order_item_id='ORDER ITEM ID', got '{column_map.get('order_item_id')}'")
        return False
    
    print(f"✅ TEST 3 PASSED: Flipkart config structure correct")
    return True


def test_4_get_myntra_config():
    """Test 4: GET /api/order-import-format-configs/myntra."""
    print("\n" + "="*80)
    print("TEST 4: GET /api/order-import-format-configs/myntra")
    print("="*80)
    
    resp = session.get(f"{BASE_URL}/order-import-format-configs/myntra", headers=headers())
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}")
        print(f"Response: {resp.text}")
        return False
    
    data = resp.json()
    print(f"Platform: {data.get('platform')}")
    print(f"is_picklist: {data.get('is_picklist')}")
    print(f"known_sku_prefixes_to_strip: {data.get('known_sku_prefixes_to_strip')}")
    print(f"active: {data.get('active')}")
    print(f"seeded: {data.get('seeded')}")
    
    # Verify Myntra config structure
    if data.get("platform") != "myntra":
        print(f"❌ FAILED: Expected platform='myntra', got '{data.get('platform')}'")
        return False
    
    if data.get("is_picklist") != True:
        print(f"❌ FAILED: Expected is_picklist=true for Myntra")
        return False
    
    prefixes = data.get("known_sku_prefixes_to_strip", [])
    if "FLL" not in prefixes:
        print(f"❌ FAILED: Expected 'FLL' in known_sku_prefixes_to_strip, got {prefixes}")
        return False
    
    if data.get("active") != True:
        print(f"❌ FAILED: Expected active=true")
        return False
    
    if data.get("seeded") != True:
        print(f"❌ FAILED: Expected seeded=true")
        return False
    
    column_map = data.get("column_map", {})
    if column_map.get("leaf_sku") != "sellerSkuCode":
        print(f"❌ FAILED: Expected column_map.leaf_sku='sellerSkuCode', got '{column_map.get('leaf_sku')}'")
        return False
    
    if column_map.get("order_id") is not None:
        print(f"❌ FAILED: Expected column_map.order_id=null for picklist, got '{column_map.get('order_id')}'")
        return False
    
    if column_map.get("qty") != "quantity":
        print(f"❌ FAILED: Expected column_map.qty='quantity', got '{column_map.get('qty')}'")
        return False
    
    print(f"✅ TEST 4 PASSED: Myntra config structure correct")
    return True


def test_5_get_nonexistent_config():
    """Test 5: GET /api/order-import-format-configs/does-not-exist should return 404."""
    print("\n" + "="*80)
    print("TEST 5: GET /api/order-import-format-configs/does-not-exist (404)")
    print("="*80)
    
    resp = session.get(f"{BASE_URL}/order-import-format-configs/does-not-exist", headers=headers())
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 404:
        print(f"❌ FAILED: Expected 404, got {resp.status_code}")
        print(f"Response: {resp.text}")
        return False
    
    print(f"✅ TEST 5 PASSED: 404 returned for nonexistent config")
    return True


def test_6_create_nykaa_config():
    """Test 6: POST /api/order-import-format-configs to create nykaa config."""
    print("\n" + "="*80)
    print("TEST 6: POST /api/order-import-format-configs (create nykaa)")
    print("="*80)
    
    payload = {
        "platform": "nykaa",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 0,
        "column_map": {
            "leaf_sku": "Nykaa SKU",
            "qty": "Qty",
            "order_id": "Nykaa Order Id"
        },
        "known_sku_prefixes_to_strip": ["NK"],
        "is_picklist": False,
        "active": True,
        "notes": "Nykaa order import config"
    }
    
    resp = session.post(f"{BASE_URL}/order-import-format-configs", json=payload, headers=headers())
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}")
        print(f"Response: {resp.text}")
        return False
    
    data = resp.json()
    print(f"Created config: platform={data.get('platform')}, id={data.get('id')}")
    
    if data.get("platform") != "nykaa":
        print(f"❌ FAILED: Expected platform='nykaa', got '{data.get('platform')}'")
        return False
    
    if not data.get("id"):
        print(f"❌ FAILED: No id in response")
        return False
    
    print(f"✅ TEST 6 PASSED: Nykaa config created successfully")
    return True


def test_7_create_duplicate_config():
    """Test 7: POST /api/order-import-format-configs with duplicate platform should return 409."""
    print("\n" + "="*80)
    print("TEST 7: POST /api/order-import-format-configs (duplicate nykaa - 409)")
    print("="*80)
    
    payload = {
        "platform": "nykaa",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 0,
        "column_map": {
            "leaf_sku": "Nykaa SKU",
            "qty": "Qty"
        },
        "known_sku_prefixes_to_strip": [],
        "is_picklist": False,
        "active": True
    }
    
    resp = session.post(f"{BASE_URL}/order-import-format-configs", json=payload, headers=headers())
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 409:
        print(f"❌ FAILED: Expected 409, got {resp.status_code}")
        print(f"Response: {resp.text}")
        return False
    
    print(f"✅ TEST 7 PASSED: 409 returned for duplicate platform")
    return True


def test_8_update_nykaa_config():
    """Test 8: PUT /api/order-import-format-configs/nykaa to update active flag."""
    print("\n" + "="*80)
    print("TEST 8: PUT /api/order-import-format-configs/nykaa (update active=false)")
    print("="*80)
    
    payload = {
        "active": False
    }
    
    resp = session.put(f"{BASE_URL}/order-import-format-configs/nykaa", json=payload, headers=headers())
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}")
        print(f"Response: {resp.text}")
        return False
    
    data = resp.json()
    print(f"Updated config: active={data.get('active')}")
    
    if data.get("active") != False:
        print(f"❌ FAILED: Expected active=false, got {data.get('active')}")
        return False
    
    print(f"✅ TEST 8 PASSED: Nykaa config updated successfully")
    return True


def test_9_create_config_missing_leaf_sku():
    """Test 9: POST /api/order-import-format-configs with missing leaf_sku should return 422."""
    print("\n" + "="*80)
    print("TEST 9: POST /api/order-import-format-configs (missing leaf_sku - 422)")
    print("="*80)
    
    payload = {
        "platform": "amazon",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 0,
        "column_map": {
            "order_id": "Amazon Order Id",
            "qty": "Quantity"
            # Missing leaf_sku
        },
        "known_sku_prefixes_to_strip": [],
        "is_picklist": False,
        "active": True
    }
    
    resp = session.post(f"{BASE_URL}/order-import-format-configs", json=payload, headers=headers())
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 422:
        print(f"❌ FAILED: Expected 422, got {resp.status_code}")
        print(f"Response: {resp.text}")
        return False
    
    resp_text = resp.text.lower()
    if "leaf_sku" not in resp_text:
        print(f"❌ FAILED: Error message should mention 'leaf_sku'")
        print(f"Response: {resp.text}")
        return False
    
    print(f"✅ TEST 9 PASSED: 422 returned with leaf_sku error message")
    return True


def test_10_import_flipkart_dry_run():
    """Test 10: POST /api/online-orders/import-configured with Flipkart CSV (dry_run=true)."""
    print("\n" + "="*80)
    print("TEST 10: POST /api/online-orders/import-configured (Flipkart dry_run)")
    print("="*80)
    
    # Create Flipkart CSV with 3 rows as specified
    csv_content = io.StringIO()
    writer = csv.writer(csv_content)
    
    # Header row matching Flipkart column_map
    writer.writerow([
        "Order Id", "ORDER ITEM ID", "Shipment ID", "Ordered On", "SKU",
        "Product", "Quantity", "Selling Price Per Item", "Invoice Amount",
        "Order State", "Tracking ID", "Dispatch by date", "Buyer name",
        "City", "State", "PIN Code"
    ])
    
    # Row A: Order Id="FK001", ORDER ITEM ID with leading apostrophe, SKU with TH prefix
    writer.writerow([
        "FK001", "'438019315969082100", "SHIP001", "2024-01-15", "THFL_AK_048_BG_37",
        "Test Product A", "1", "1999", "1999", "Confirmed", "TRACK001",
        "2024-01-20", "John Doe", "Mumbai", "Maharashtra", "400001"
    ])
    
    # Row B: Order Id="FK002", plain SSK format, qty=2
    writer.writerow([
        "FK002", "438019315969082101", "SHIP002", "2024-01-16", "CC-050-BE-8",
        "Test Product B", "2", "2499", "4998", "Confirmed", "TRACK002",
        "2024-01-21", "Jane Smith", "Delhi", "Delhi", "110001"
    ])
    
    # Row C: Order Id="FK003", empty SKU (should produce empty_leaf_sku flag)
    writer.writerow([
        "FK003", "438019315969082102", "SHIP003", "2024-01-17", "",
        "Test Product C", "1", "1499", "1499", "Confirmed", "TRACK003",
        "2024-01-22", "Bob Johnson", "Bangalore", "Karnataka", "560001"
    ])
    
    csv_bytes = csv_content.getvalue().encode('utf-8')
    
    files = {'file': ('flipkart_orders.csv', csv_bytes, 'text/csv')}
    params = {'platform': 'flipkart', 'dry_run': 'true'}
    
    resp = session.post(
        f"{BASE_URL}/online-orders/import-configured",
        files=files,
        params=params,
        headers=headers()
    )
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}")
        print(f"Response: {resp.text}")
        return False
    
    data = resp.json()
    print(f"Platform: {data.get('platform')}")
    print(f"is_picklist: {data.get('is_picklist')}")
    print(f"picklist_batch_id: {data.get('picklist_batch_id')}")
    print(f"dry_run: {data.get('dry_run')}")
    
    stats = data.get('stats', {})
    print(f"Stats: total_rows_read={stats.get('total_rows_read')}, "
          f"order_style_rows={stats.get('order_style_rows')}, "
          f"picklist_rows={stats.get('picklist_rows')}, "
          f"empty_leaf_sku={stats.get('empty_leaf_sku')}")
    
    # Verify response structure
    if data.get('platform') != 'flipkart':
        print(f"❌ FAILED: Expected platform='flipkart', got '{data.get('platform')}'")
        return False
    
    if data.get('is_picklist') != False:
        print(f"❌ FAILED: Expected is_picklist=false")
        return False
    
    if data.get('picklist_batch_id') is not None:
        print(f"❌ FAILED: Expected picklist_batch_id=null for order mode")
        return False
    
    if data.get('dry_run') != True:
        print(f"❌ FAILED: Expected dry_run=true")
        return False
    
    # Verify stats
    if stats.get('total_rows_read') != 3:
        print(f"❌ FAILED: Expected total_rows_read=3, got {stats.get('total_rows_read')}")
        return False
    
    if stats.get('order_style_rows') != 3:
        print(f"❌ FAILED: Expected order_style_rows=3, got {stats.get('order_style_rows')}")
        return False
    
    if stats.get('picklist_rows') != 0:
        print(f"❌ FAILED: Expected picklist_rows=0, got {stats.get('picklist_rows')}")
        return False
    
    if stats.get('empty_leaf_sku') < 1:
        print(f"❌ FAILED: Expected empty_leaf_sku >= 1, got {stats.get('empty_leaf_sku')}")
        return False
    
    # Verify rows array
    rows = data.get('rows', [])
    if len(rows) != 3:
        print(f"❌ FAILED: Expected 3 rows, got {len(rows)}")
        return False
    
    # Row 0: FK001 with apostrophe stripped, TH prefix stripped
    row0 = rows[0]
    print(f"\nRow 0: order_id={row0.get('order_id')}, "
          f"order_item_id={row0.get('order_item_id')}, "
          f"leaf_sku_stripped_prefix={row0.get('leaf_sku_stripped_prefix')}, "
          f"leaf_sku={row0.get('leaf_sku')}, "
          f"qty={row0.get('qty')}")
    
    if row0.get('order_id') != 'FK001':
        print(f"❌ FAILED: Row 0 order_id should be 'FK001', got '{row0.get('order_id')}'")
        return False
    
    if row0.get('order_item_id') != '438019315969082100':
        print(f"❌ FAILED: Row 0 order_item_id should have apostrophe stripped, got '{row0.get('order_item_id')}'")
        return False
    
    if row0.get('leaf_sku_stripped_prefix') != 'TH':
        print(f"❌ FAILED: Row 0 leaf_sku_stripped_prefix should be 'TH', got '{row0.get('leaf_sku_stripped_prefix')}'")
        return False
    
    if row0.get('leaf_sku') != 'FL_AK_048_BG_37':
        print(f"❌ FAILED: Row 0 leaf_sku should be 'FL_AK_048_BG_37' (TH stripped), got '{row0.get('leaf_sku')}'")
        return False
    
    if row0.get('qty') != 1:
        print(f"❌ FAILED: Row 0 qty should be 1, got {row0.get('qty')}")
        return False
    
    # Row 1: FK002 with plain SKU, qty=2
    row1 = rows[1]
    print(f"\nRow 1: order_id={row1.get('order_id')}, "
          f"leaf_sku={row1.get('leaf_sku')}, "
          f"qty={row1.get('qty')}, "
          f"leaf_sku_stripped_prefix={row1.get('leaf_sku_stripped_prefix')}")
    
    if row1.get('order_id') != 'FK002':
        print(f"❌ FAILED: Row 1 order_id should be 'FK002', got '{row1.get('order_id')}'")
        return False
    
    if row1.get('leaf_sku') != 'CC-050-BE-8':
        print(f"❌ FAILED: Row 1 leaf_sku should be 'CC-050-BE-8', got '{row1.get('leaf_sku')}'")
        return False
    
    if row1.get('qty') != 2:
        print(f"❌ FAILED: Row 1 qty should be 2, got {row1.get('qty')}")
        return False
    
    if row1.get('leaf_sku_stripped_prefix') is not None and row1.get('leaf_sku_stripped_prefix') != '':
        print(f"❌ FAILED: Row 1 leaf_sku_stripped_prefix should be null/empty, got '{row1.get('leaf_sku_stripped_prefix')}'")
        return False
    
    # Row 2: FK003 with empty SKU (should have empty_leaf_sku flag)
    row2 = rows[2]
    print(f"\nRow 2: order_id={row2.get('order_id')}, "
          f"flags={row2.get('flags')}")
    
    if row2.get('order_id') != 'FK003':
        print(f"❌ FAILED: Row 2 order_id should be 'FK003', got '{row2.get('order_id')}'")
        return False
    
    flags = row2.get('flags', [])
    if 'empty_leaf_sku' not in flags:
        print(f"❌ FAILED: Row 2 should have 'empty_leaf_sku' flag, got {flags}")
        return False
    
    print(f"✅ TEST 10 PASSED: Flipkart dry_run import working correctly")
    return True


def test_11_import_myntra_dry_run():
    """Test 11: POST /api/online-orders/import-configured with Myntra CSV (dry_run=true)."""
    print("\n" + "="*80)
    print("TEST 11: POST /api/online-orders/import-configured (Myntra picklist dry_run)")
    print("="*80)
    
    # Create Myntra picklist CSV
    csv_content = io.StringIO()
    writer = csv.writer(csv_content)
    
    # Header row matching Myntra column_map
    writer.writerow([
        "myntraSkuCode", "sellerSkuCode", "productDescription", "quantity", "binBarcode"
    ])
    
    # Row 1: FLL prefix (should strip to FL), qty=2
    writer.writerow([
        "MYN001", "FLL_AK_005_SL-7", "Test shoe", "2", "B01"
    ])
    
    # Row 2: No prefix, size 5, qty=1
    writer.writerow([
        "MYN002", "FL_AK_27_LV-5", "Another shoe", "1", "B02"
    ])
    
    csv_bytes = csv_content.getvalue().encode('utf-8')
    
    files = {'file': ('OP20625445.csv', csv_bytes, 'text/csv')}
    params = {'platform': 'myntra', 'dry_run': 'true'}
    
    resp = session.post(
        f"{BASE_URL}/online-orders/import-configured",
        files=files,
        params=params,
        headers=headers()
    )
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}")
        print(f"Response: {resp.text}")
        return False
    
    data = resp.json()
    print(f"Platform: {data.get('platform')}")
    print(f"is_picklist: {data.get('is_picklist')}")
    print(f"picklist_batch_id: {data.get('picklist_batch_id')}")
    print(f"dry_run: {data.get('dry_run')}")
    
    stats = data.get('stats', {})
    print(f"Stats: total_rows_read={stats.get('total_rows_read')}, "
          f"picklist_rows={stats.get('picklist_rows')}, "
          f"order_style_rows={stats.get('order_style_rows')}")
    
    # Verify response structure
    if data.get('platform') != 'myntra':
        print(f"❌ FAILED: Expected platform='myntra', got '{data.get('platform')}'")
        return False
    
    if data.get('is_picklist') != True:
        print(f"❌ FAILED: Expected is_picklist=true")
        return False
    
    if data.get('picklist_batch_id') != 'OP20625445':
        print(f"❌ FAILED: Expected picklist_batch_id='OP20625445' (from filename), got '{data.get('picklist_batch_id')}'")
        return False
    
    if data.get('dry_run') != True:
        print(f"❌ FAILED: Expected dry_run=true")
        return False
    
    # Verify stats
    if stats.get('picklist_rows') != 2:
        print(f"❌ FAILED: Expected picklist_rows=2, got {stats.get('picklist_rows')}")
        return False
    
    if stats.get('order_style_rows') != 0:
        print(f"❌ FAILED: Expected order_style_rows=0, got {stats.get('order_style_rows')}")
        return False
    
    # Verify rows array
    rows = data.get('rows', [])
    if len(rows) != 2:
        print(f"❌ FAILED: Expected 2 rows, got {len(rows)}")
        return False
    
    # Row 0: FLL prefix stripped, qty=2
    row0 = rows[0]
    print(f"\nRow 0: leaf_sku_stripped_prefix={row0.get('leaf_sku_stripped_prefix')}, "
          f"leaf_sku={row0.get('leaf_sku')}, "
          f"qty={row0.get('qty')}, "
          f"picklist_batch_id={row0.get('picklist_batch_id')}")
    
    if row0.get('leaf_sku_stripped_prefix') != 'FLL':
        print(f"❌ FAILED: Row 0 leaf_sku_stripped_prefix should be 'FLL', got '{row0.get('leaf_sku_stripped_prefix')}'")
        return False
    
    if row0.get('leaf_sku') != 'FL_AK_005_SL-7':
        print(f"❌ FAILED: Row 0 leaf_sku should be 'FL_AK_005_SL-7' (FLL stripped), got '{row0.get('leaf_sku')}'")
        return False
    
    if row0.get('qty') != 2:
        print(f"❌ FAILED: Row 0 qty should be 2 (not defaulted to 1!), got {row0.get('qty')}")
        return False
    
    if row0.get('picklist_batch_id') != 'OP20625445':
        print(f"❌ FAILED: Row 0 picklist_batch_id should be 'OP20625445', got '{row0.get('picklist_batch_id')}'")
        return False
    
    # Row 1: No prefix, size 5
    row1 = rows[1]
    print(f"\nRow 1: leaf_sku={row1.get('leaf_sku')}, "
          f"qty={row1.get('qty')}, "
          f"derived_size={row1.get('derived_size')}")
    
    if row1.get('leaf_sku') != 'FL_AK_27_LV-5':
        print(f"❌ FAILED: Row 1 leaf_sku should be 'FL_AK_27_LV-5', got '{row1.get('leaf_sku')}'")
        return False
    
    if row1.get('qty') != 1:
        print(f"❌ FAILED: Row 1 qty should be 1, got {row1.get('qty')}")
        return False
    
    if row1.get('derived_size') != '5':
        print(f"❌ FAILED: Row 1 derived_size should be '5', got '{row1.get('derived_size')}'")
        return False
    
    print(f"✅ TEST 11 PASSED: Myntra picklist dry_run import working correctly")
    return True


def test_12_import_nonexistent_platform():
    """Test 12: POST /api/online-orders/import-configured with nonexistent platform should return 400."""
    print("\n" + "="*80)
    print("TEST 12: POST /api/online-orders/import-configured (nonexistent platform - 400)")
    print("="*80)
    
    # Create a dummy CSV
    csv_content = io.StringIO()
    writer = csv.writer(csv_content)
    writer.writerow(["SKU", "Qty"])
    writer.writerow(["TEST-SKU-1", "1"])
    csv_bytes = csv_content.getvalue().encode('utf-8')
    
    files = {'file': ('test.csv', csv_bytes, 'text/csv')}
    params = {'platform': 'doesnotexist', 'dry_run': 'true'}
    
    resp = session.post(
        f"{BASE_URL}/online-orders/import-configured",
        files=files,
        params=params,
        headers=headers()
    )
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 400:
        print(f"❌ FAILED: Expected 400, got {resp.status_code}")
        print(f"Response: {resp.text}")
        return False
    
    resp_text = resp.text.lower()
    if "no order-import config" not in resp_text and "doesnotexist" not in resp_text:
        print(f"❌ FAILED: Error message should mention missing config")
        print(f"Response: {resp.text}")
        return False
    
    print(f"✅ TEST 12 PASSED: 400 returned for nonexistent platform")
    return True


def test_13_import_flipkart_commit():
    """Test 13: POST /api/online-orders/import-configured with Flipkart CSV (dry_run=false - commit mode)."""
    print("\n" + "="*80)
    print("TEST 13: POST /api/online-orders/import-configured (Flipkart commit mode)")
    print("="*80)
    
    # Create Flipkart CSV with 3 rows (same as test 10)
    csv_content = io.StringIO()
    writer = csv.writer(csv_content)
    
    # Header row
    writer.writerow([
        "Order Id", "ORDER ITEM ID", "Shipment ID", "Ordered On", "SKU",
        "Product", "Quantity", "Selling Price Per Item", "Invoice Amount",
        "Order State", "Tracking ID", "Dispatch by date", "Buyer name",
        "City", "State", "PIN Code"
    ])
    
    # 3 rows
    writer.writerow([
        "FK001_COMMIT", "'438019315969082100", "SHIP001", "2024-01-15", "THFL_AK_048_BG_37",
        "Test Product A", "1", "1999", "1999", "Confirmed", "TRACK001",
        "2024-01-20", "John Doe", "Mumbai", "Maharashtra", "400001"
    ])
    
    writer.writerow([
        "FK002_COMMIT", "438019315969082101", "SHIP002", "2024-01-16", "CC-050-BE-8",
        "Test Product B", "2", "2499", "4998", "Confirmed", "TRACK002",
        "2024-01-21", "Jane Smith", "Delhi", "Delhi", "110001"
    ])
    
    writer.writerow([
        "FK003_COMMIT", "438019315969082102", "SHIP003", "2024-01-17", "",
        "Test Product C", "1", "1499", "1499", "Confirmed", "TRACK003",
        "2024-01-22", "Bob Johnson", "Bangalore", "Karnataka", "560001"
    ])
    
    csv_bytes = csv_content.getvalue().encode('utf-8')
    
    files = {'file': ('flipkart_orders_commit.csv', csv_bytes, 'text/csv')}
    params = {'platform': 'flipkart', 'dry_run': 'false'}
    
    resp = session.post(
        f"{BASE_URL}/online-orders/import-configured",
        files=files,
        params=params,
        headers=headers()
    )
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}")
        print(f"Response: {resp.text}")
        return False
    
    data = resp.json()
    print(f"dry_run: {data.get('dry_run')}")
    print(f"import_batch_id: {data.get('import_batch_id')}")
    
    committed = data.get('committed', {})
    print(f"Committed: orders_created={committed.get('orders_created')}, "
          f"items_created={committed.get('items_created')}, "
          f"exceptions_queued={committed.get('exceptions_queued')}")
    
    # Verify response structure
    if data.get('dry_run') != False:
        print(f"❌ FAILED: Expected dry_run=false")
        return False
    
    import_batch_id = data.get('import_batch_id')
    if not import_batch_id:
        print(f"❌ FAILED: Expected import_batch_id to be populated")
        return False
    
    if not import_batch_id.startswith('IMP_flipkart_'):
        print(f"❌ FAILED: Expected import_batch_id to start with 'IMP_flipkart_', got '{import_batch_id}'")
        return False
    
    # Verify committed stats
    if committed.get('orders_created') < 3:
        print(f"❌ FAILED: Expected orders_created >= 3, got {committed.get('orders_created')}")
        return False
    
    if committed.get('items_created') < 3:
        print(f"❌ FAILED: Expected items_created >= 3, got {committed.get('items_created')}")
        return False
    
    print(f"✅ TEST 13 PASSED: Flipkart commit mode working correctly")
    return True


def main():
    """Run all Phase G tests."""
    print("="*80)
    print("PHASE G — ORDER/PICKLIST CONFIG-DRIVEN IMPORT REGRESSION TEST")
    print("="*80)
    
    login()
    
    tests = [
        test_1_get_all_configs,
        test_2_get_canonical_fields,
        test_3_get_flipkart_config,
        test_4_get_myntra_config,
        test_5_get_nonexistent_config,
        test_6_create_nykaa_config,
        test_7_create_duplicate_config,
        test_8_update_nykaa_config,
        test_9_create_config_missing_leaf_sku,
        test_10_import_flipkart_dry_run,
        test_11_import_myntra_dry_run,
        test_12_import_nonexistent_platform,
        test_13_import_flipkart_commit,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ TEST EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "="*80)
    print(f"PHASE G TEST SUMMARY: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("="*80)
    
    if failed == 0:
        print("✅ ALL TESTS PASSED")
        sys.exit(0)
    else:
        print(f"❌ {failed} TEST(S) FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
