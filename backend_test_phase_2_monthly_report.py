#!/usr/bin/env python3
"""
Phase 2 — Monthly Report Import & Inventory Reconciliation Testing
Tests the role='monthly_report' config, classification logic, and reconciliation endpoints.
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


def test_1_canonical_fields_monthly_report():
    """Test 1: GET /api/order-import-format-configs/_meta/canonical-fields?role=monthly_report"""
    print("\n=== TEST 1: Config discovery - canonical fields for monthly_report ===")
    resp = session.get(f"{BASE_URL}/order-import-format-configs/_meta/canonical-fields?role=monthly_report")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    assert "role" in data, "Missing 'role' field in response"
    assert data["role"] == "monthly_report", f"Expected role='monthly_report', got {data['role']}"
    
    assert "canonical_fields" in data, "Missing 'canonical_fields' in response"
    fields = data["canonical_fields"]
    
    # Verify required fields from spec
    required_fields = [
        "order_id", "order_release_id", "leaf_sku", "size", "order_status",
        "packed_on", "delivered_on", "cancelled_on", "rto_creation_date",
        "return_creation_date", "final_amount", "total_mrp", "discount", "seller_price"
    ]
    
    for field in required_fields:
        assert field in fields, f"Missing required canonical field: {field}"
    
    print(f"✅ TEST 1 PASSED: canonical_fields contains all {len(required_fields)} required fields")
    print(f"   Fields: {fields}")
    return data


def test_2_myntra_monthly_report_seed_config():
    """Test 2: GET /api/order-import-format-configs/myntra?role=monthly_report - verify seed config"""
    print("\n=== TEST 2: Myntra seed config for monthly_report ===")
    resp = session.get(f"{BASE_URL}/order-import-format-configs/myntra?role=monthly_report")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    config = resp.json()
    
    # Verify basic structure
    assert config["role"] == "monthly_report", f"Expected role='monthly_report', got {config['role']}"
    assert config["seeded"] == True, "Expected seeded=true"
    assert config["active"] == True, "Expected active=true"
    assert config["is_picklist"] == False, "Expected is_picklist=false for monthly_report"
    
    # Verify column_map has correct mappings from spec
    column_map = config["column_map"]
    expected_mappings = {
        "leaf_sku": "seller sku code",
        "order_release_id": "order release id",
        "order_id": "order id fk",
        "rto_creation_date": "rto creation date",
        "return_creation_date": "return creation date",
        "order_status": "order status",
        "packed_on": "packed on",
        "cancelled_on": "cancelled on",
        "delivered_on": "delivered on",
        "final_amount": "final amount",
        "total_mrp": "total mrp",
        "discount": "discount",
        "seller_price": "seller price"
    }
    
    for canonical, actual in expected_mappings.items():
        assert canonical in column_map, f"Missing column_map entry for {canonical}"
        assert column_map[canonical] == actual, f"Expected column_map.{canonical}='{actual}', got '{column_map[canonical]}'"
    
    # Verify known_sku_prefix_replacements
    assert "known_sku_prefix_replacements" in config, "Missing known_sku_prefix_replacements"
    assert config["known_sku_prefix_replacements"] == {"FLL": "FL"}, \
        f"Expected known_sku_prefix_replacements={{'FLL':'FL'}}, got {config['known_sku_prefix_replacements']}"
    
    print("✅ TEST 2 PASSED: Myntra monthly_report config has correct structure and column_map")
    print(f"   Column mappings verified: {len(expected_mappings)} fields")
    return config


def test_3_missing_config_400():
    """Test 3: POST with unknown platform should return 400"""
    print("\n=== TEST 3: Missing config → 400 ===")
    
    # Create a minimal CSV
    csv_content = "order id fk,order release id\nMO1,301001\n"
    files = {"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    
    resp = session.post(
        f"{BASE_URL}/online-orders/monthly-report-import?platform=doesnotexist&dry_run=true",
        files=files
    )
    
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    assert "detail" in data or "message" in data, "Expected error message in response"
    error_msg = data.get("detail") or data.get("message")
    assert "doesnotexist" in error_msg.lower() or "monthly-report" in error_msg.lower(), \
        f"Expected error message about missing config, got: {error_msg}"
    
    print(f"✅ TEST 3 PASSED: Unknown platform correctly returns 400 with message: {error_msg}")


def test_4_classification_logic_critical():
    """Test 4: CRITICAL - Classification logic with 7 rows covering all branches"""
    print("\n=== TEST 4: CRITICAL - Classification logic (7 rows) ===")
    
    # Build CSV with exactly 7 rows as specified in the review request
    csv_content = """order id fk,order release id,seller sku code,size,order status,packed on,delivered on,cancelled on,rto creation date,return creation date,final amount,total mrp,discount,seller price
MO1,301001,FL_AK_005_SL-7,7,C,2026-06-01,2026-06-05,,,,1899,2999,1100,1699
MO2,301002,FLL_AK_005_SL-7,7,C,2026-06-02,2026-06-07,,,2026-06-15,1899,2999,1100,1699
MO3,301003,FL_AK_005_SL-8,8,F,2026-06-03,,2026-06-04,,,0,2999,0,0
MO4,301004,FL_AK_005_SL-9,9,F,,,2026-06-03,,,0,2999,0,0
MO5,301005,FL_AK_005_SL-10,10,RTO,2026-06-04,,,2026-06-10,,0,2999,0,0
MO6,301006,FL_AK_005_SL-6,6,SH,2026-06-05,,,,,1899,2999,1100,1699
MO7,301007,FL_AK_005_SL-5,5,PK,2026-06-06,,,,,1899,2999,1100,1699"""
    
    files = {"file": ("monthly_report.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    
    resp = session.post(
        f"{BASE_URL}/online-orders/monthly-report-import?platform=myntra&dry_run=true",
        files=files
    )
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    
    # Response-level asserts
    assert data["platform"] == "myntra", f"Expected platform='myntra', got {data['platform']}"
    assert data["role"] == "monthly_report", f"Expected role='monthly_report', got {data['role']}"
    assert data["dry_run"] == True, f"Expected dry_run=true, got {data['dry_run']}"
    
    stats = data["stats"]
    assert stats["total_rows"] == 7, f"Expected total_rows=7, got {stats['total_rows']}"
    assert stats["packed"] == 6, f"Expected packed=6, got {stats['packed']}"
    assert stats["never_touched_inventory"] == 1, f"Expected never_touched_inventory=1, got {stats['never_touched_inventory']}"
    assert stats["returned_to_stock"] == 3, f"Expected returned_to_stock=3, got {stats['returned_to_stock']}"
    assert stats["pending"] == 2, f"Expected pending=2, got {stats['pending']}"
    assert stats["net_sold"] == 1, f"Expected net_sold=1, got {stats['net_sold']}"
    
    reason_breakdown = stats["reason_breakdown"]
    assert reason_breakdown["rto"] == 1, f"Expected reason_breakdown.rto=1, got {reason_breakdown['rto']}"
    assert reason_breakdown["customer_return"] == 1, f"Expected reason_breakdown.customer_return=1, got {reason_breakdown['customer_return']}"
    assert reason_breakdown["cancelled_after_pack"] == 1, f"Expected reason_breakdown.cancelled_after_pack=1, got {reason_breakdown['cancelled_after_pack']}"
    
    print("✅ Response-level stats verified:")
    print(f"   total_rows=7, packed=6, never_touched=1, returned=3, pending=2, net_sold=1")
    print(f"   reason_breakdown: rto=1, customer_return=1, cancelled_after_pack=1")
    
    # Per-row asserts
    rows = data["rows"]
    assert len(rows) == 7, f"Expected 7 rows, got {len(rows)}"
    
    # MO1: net sold
    row0 = rows[0]
    assert row0["was_packed"] == True, f"MO1: Expected was_packed=true"
    assert row0["was_returned_to_stock"] == False, f"MO1: Expected was_returned_to_stock=false"
    assert row0["is_pending"] == False, f"MO1: Expected is_pending=false"
    assert row0["is_net_sold"] == True, f"MO1: Expected is_net_sold=true"
    assert row0["never_touched_inventory"] == False, f"MO1: Expected never_touched_inventory=false"
    assert row0["return_reason"] == None or row0["return_reason"] == "", f"MO1: Expected return_reason=null"
    print("✅ MO1: is_net_sold=true (packed, no returns, not pending)")
    
    # MO2: customer return + FLL→FL replacement
    row1 = rows[1]
    assert row1["was_packed"] == True, f"MO2: Expected was_packed=true"
    assert row1["was_returned_to_stock"] == True, f"MO2: Expected was_returned_to_stock=true"
    assert row1["is_net_sold"] == False, f"MO2: Expected is_net_sold=false"
    assert row1["return_reason"] == "customer_return", f"MO2: Expected return_reason='customer_return', got {row1['return_reason']}"
    assert row1["leaf_sku_raw"] == "FLL_AK_005_SL-7", f"MO2: Expected leaf_sku_raw='FLL_AK_005_SL-7'"
    assert row1["leaf_sku_replaced_prefix"] == "FLL", f"MO2: Expected leaf_sku_replaced_prefix='FLL'"
    assert row1["leaf_sku"] == "FL_AK_005_SL-7", f"MO2: Expected leaf_sku='FL_AK_005_SL-7' (FLL→FL replacement)"
    print("✅ MO2: return_reason='customer_return', FLL→FL replacement working")
    
    # MO3: cancelled after pack
    row2 = rows[2]
    assert row2["was_packed"] == True, f"MO3: Expected was_packed=true"
    assert row2["was_returned_to_stock"] == True, f"MO3: Expected was_returned_to_stock=true"
    assert row2["is_net_sold"] == False, f"MO3: Expected is_net_sold=false"
    assert row2["return_reason"] == "cancelled_after_pack", f"MO3: Expected return_reason='cancelled_after_pack'"
    assert row2["order_status"] == "F", f"MO3: Expected order_status='F'"
    print("✅ MO3: return_reason='cancelled_after_pack' (status=F, packed)")
    
    # MO4: never touched inventory
    row3 = rows[3]
    assert row3["was_packed"] == False, f"MO4: Expected was_packed=false"
    assert row3["never_touched_inventory"] == True, f"MO4: Expected never_touched_inventory=true"
    assert row3["is_net_sold"] == False, f"MO4: Expected is_net_sold=false"
    assert row3["was_returned_to_stock"] == False, f"MO4: Expected was_returned_to_stock=false"
    assert row3["return_reason"] == None or row3["return_reason"] == "", f"MO4: Expected return_reason=null"
    print("✅ MO4: never_touched_inventory=true (not packed)")
    
    # MO5: RTO
    row4 = rows[4]
    assert row4["was_packed"] == True, f"MO5: Expected was_packed=true"
    assert row4["was_returned_to_stock"] == True, f"MO5: Expected was_returned_to_stock=true"
    assert row4["is_net_sold"] == False, f"MO5: Expected is_net_sold=false"
    assert row4["return_reason"] == "rto", f"MO5: Expected return_reason='rto'"
    assert row4["order_status"] == "RTO", f"MO5: Expected order_status='RTO'"
    print("✅ MO5: return_reason='rto' (status=RTO, has rto_creation_date)")
    
    # MO6: pending (SH)
    row5 = rows[5]
    assert row5["is_pending"] == True, f"MO6: Expected is_pending=true"
    assert row5["is_net_sold"] == False, f"MO6: Expected is_net_sold=false"
    assert row5["was_returned_to_stock"] == False, f"MO6: Expected was_returned_to_stock=false"
    assert row5["order_status"] == "SH", f"MO6: Expected order_status='SH'"
    print("✅ MO6: is_pending=true (status=SH)")
    
    # MO7: pending (PK)
    row6 = rows[6]
    assert row6["is_pending"] == True, f"MO7: Expected is_pending=true"
    assert row6["is_net_sold"] == False, f"MO7: Expected is_net_sold=false"
    assert row6["was_returned_to_stock"] == False, f"MO7: Expected was_returned_to_stock=false"
    assert row6["order_status"] == "PK", f"MO7: Expected order_status='PK'"
    print("✅ MO7: is_pending=true (status=PK)")
    
    print("\n✅ TEST 4 PASSED: All 7 rows classified correctly across all 6 branches")
    return data


def test_5_commit_path_exceptions():
    """Test 5: Commit path - unmatched rows go to exceptions"""
    print("\n=== TEST 5: Commit path (unmatched rows → exceptions) ===")
    
    # Use same 7-row CSV
    csv_content = """order id fk,order release id,seller sku code,size,order status,packed on,delivered on,cancelled on,rto creation date,return creation date,final amount,total mrp,discount,seller price
MO1,301001,FL_AK_005_SL-7,7,C,2026-06-01,2026-06-05,,,,1899,2999,1100,1699
MO2,301002,FLL_AK_005_SL-7,7,C,2026-06-02,2026-06-07,,,2026-06-15,1899,2999,1100,1699
MO3,301003,FL_AK_005_SL-8,8,F,2026-06-03,,2026-06-04,,,0,2999,0,0
MO4,301004,FL_AK_005_SL-9,9,F,,,2026-06-03,,,0,2999,0,0
MO5,301005,FL_AK_005_SL-10,10,RTO,2026-06-04,,,2026-06-10,,0,2999,0,0
MO6,301006,FL_AK_005_SL-6,6,SH,2026-06-05,,,,,1899,2999,1100,1699
MO7,301007,FL_AK_005_SL-5,5,PK,2026-06-06,,,,,1899,2999,1100,1699"""
    
    files = {"file": ("monthly_report.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    
    resp = session.post(
        f"{BASE_URL}/online-orders/monthly-report-import?platform=myntra&dry_run=false",
        files=files
    )
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    
    assert data["dry_run"] == False, f"Expected dry_run=false, got {data['dry_run']}"
    assert "import_batch_id" in data, "Missing import_batch_id"
    assert data["import_batch_id"].startswith("MREP_myntra_"), \
        f"Expected import_batch_id to start with 'MREP_myntra_', got {data['import_batch_id']}"
    
    # Verify committed structure
    assert "committed" in data, "Missing 'committed' in response"
    committed = data["committed"]
    
    required_keys = ["items_upserted", "orders_upserted", "returns_posted", 
                     "returns_skipped", "return_damaged_posted", "exceptions_queued"]
    for key in required_keys:
        assert key in committed, f"Missing key '{key}' in committed"
    
    # Since no styles/sku_map is seeded, expect all rows to go to exceptions
    assert committed["exceptions_queued"] >= 7, \
        f"Expected exceptions_queued >= 7 (all unresolved), got {committed['exceptions_queued']}"
    assert committed["items_upserted"] == 0, \
        f"Expected items_upserted=0 (no matched rows), got {committed['items_upserted']}"
    assert committed["returns_posted"] == 0, \
        f"Expected returns_posted=0 (no matched rows), got {committed['returns_posted']}"
    
    print(f"✅ TEST 5 PASSED: Commit mode working")
    print(f"   import_batch_id: {data['import_batch_id']}")
    print(f"   committed.exceptions_queued: {committed['exceptions_queued']} (all unmatched rows)")
    print(f"   committed.items_upserted: {committed['items_upserted']}")
    print(f"   committed.returns_posted: {committed['returns_posted']}")
    print(f"   No crash on unmatched rows ✓")
    return data


def test_6_reconciliation_summary_platform():
    """Test 6: GET /api/online-orders/reconciliation-summary?platform=myntra"""
    print("\n=== TEST 6: Reconciliation summary (platform filter) ===")
    
    resp = session.get(f"{BASE_URL}/online-orders/reconciliation-summary?platform=myntra")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    
    # Verify structure
    required_keys = ["total_rows", "packed", "never_touched_inventory", 
                     "returned_to_stock", "pending", "net_sold", "reason_breakdown"]
    for key in required_keys:
        assert key in data, f"Missing key '{key}' in reconciliation summary"
    
    # Verify reason_breakdown structure
    reason_breakdown = data["reason_breakdown"]
    assert "rto" in reason_breakdown, "Missing 'rto' in reason_breakdown"
    assert "customer_return" in reason_breakdown, "Missing 'customer_return' in reason_breakdown"
    assert "cancelled_after_pack" in reason_breakdown, "Missing 'cancelled_after_pack' in reason_breakdown"
    
    print(f"✅ TEST 6 PASSED: Reconciliation summary structure correct")
    print(f"   total_rows: {data['total_rows']}")
    print(f"   packed: {data['packed']}, net_sold: {data['net_sold']}")
    print(f"   returned_to_stock: {data['returned_to_stock']}, pending: {data['pending']}")
    print(f"   reason_breakdown: {reason_breakdown}")
    return data


def test_7_reconciliation_summary_month():
    """Test 7: GET /api/online-orders/reconciliation-summary?platform=myntra&month=2026-06"""
    print("\n=== TEST 7: Reconciliation summary (month filter) ===")
    
    resp = session.get(f"{BASE_URL}/online-orders/reconciliation-summary?platform=myntra&month=2026-06")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    
    # Verify same structure
    required_keys = ["total_rows", "packed", "never_touched_inventory", 
                     "returned_to_stock", "pending", "net_sold", "reason_breakdown"]
    for key in required_keys:
        assert key in data, f"Missing key '{key}' in reconciliation summary"
    
    print(f"✅ TEST 7 PASSED: Reconciliation summary with month filter working")
    print(f"   total_rows: {data['total_rows']}")
    return data


def test_8_reconciliation_summary_no_filters():
    """Test 8: GET /api/online-orders/reconciliation-summary (no filters)"""
    print("\n=== TEST 8: Reconciliation summary (no filters) ===")
    
    resp = session.get(f"{BASE_URL}/online-orders/reconciliation-summary")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    
    # Verify same structure
    required_keys = ["total_rows", "packed", "never_touched_inventory", 
                     "returned_to_stock", "pending", "net_sold", "reason_breakdown"]
    for key in required_keys:
        assert key in data, f"Missing key '{key}' in reconciliation summary"
    
    print(f"✅ TEST 8 PASSED: Reconciliation summary without filters working")
    print(f"   total_rows: {data['total_rows']}")
    return data


def test_9_regression_phase_g_h():
    """Test 9: Regression - Phase G & Phase H untouched"""
    print("\n=== TEST 9: Regression - Phase G & Phase H ===")
    
    # Test Phase G & H configs still exist
    resp = session.get(f"{BASE_URL}/order-import-format-configs")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    configs = resp.json()
    platforms_roles = [(c["platform"], c["role"]) for c in configs]
    
    # Verify pre-existing seed configs
    assert ("flipkart", "order") in platforms_roles, "Missing flipkart/order config (Phase G)"
    assert ("myntra", "order") in platforms_roles, "Missing myntra/order config (Phase G)"
    assert ("myntra", "dispatch") in platforms_roles, "Missing myntra/dispatch config (Phase H)"
    
    # Plus the new monthly_report
    assert ("myntra", "monthly_report") in platforms_roles, "Missing myntra/monthly_report config (Phase 2)"
    
    print(f"✅ All 4 seed configs present:")
    print(f"   - flipkart/order (Phase G)")
    print(f"   - myntra/order (Phase G)")
    print(f"   - myntra/dispatch (Phase H)")
    print(f"   - myntra/monthly_report (Phase 2)")
    
    # Quick sanity: GET myntra without role param should default to 'order'
    resp = session.get(f"{BASE_URL}/order-import-format-configs/myntra")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    config = resp.json()
    assert config["role"] == "order", f"Expected default role='order', got {config['role']}"
    assert config["is_picklist"] == True, "Expected myntra/order to be picklist config"
    
    print(f"✅ TEST 9 PASSED: Phase G & Phase H configs untouched")
    print(f"   GET /myntra (no role param) correctly defaults to role='order' (picklist config)")


def main():
    """Run all tests in sequence."""
    print("=" * 80)
    print("Phase 2 — Monthly Report Import & Inventory Reconciliation Testing")
    print("=" * 80)
    
    try:
        # Login
        print("\n🔐 Logging in as admin...")
        login()
        print("✅ Login successful")
        
        # Run tests
        test_1_canonical_fields_monthly_report()
        test_2_myntra_monthly_report_seed_config()
        test_3_missing_config_400()
        test_4_classification_logic_critical()
        test_5_commit_path_exceptions()
        test_6_reconciliation_summary_platform()
        test_7_reconciliation_summary_month()
        test_8_reconciliation_summary_no_filters()
        test_9_regression_phase_g_h()
        
        # Summary
        print("\n" + "=" * 80)
        print("✅ ALL 9/9 TESTS PASSED")
        print("=" * 80)
        print("\nSUMMARY:")
        print("✅ Test 1: Config discovery - canonical fields for monthly_report")
        print("✅ Test 2: Myntra seed config with correct column_map and FLL→FL replacement")
        print("✅ Test 3: Missing config correctly returns 400")
        print("✅ Test 4: CRITICAL - Classification logic (7 rows, all 6 branches)")
        print("✅ Test 5: Commit path - unmatched rows go to exceptions (no crash)")
        print("✅ Test 6: Reconciliation summary with platform filter")
        print("✅ Test 7: Reconciliation summary with month filter")
        print("✅ Test 8: Reconciliation summary without filters")
        print("✅ Test 9: Regression - Phase G & Phase H configs untouched")
        print("\nCRITICAL ASSERTS VERIFIED:")
        print("  ✅ Classification correctness for all 6 branches:")
        print("     - net_sold (MO1)")
        print("     - customer_return (MO2) + FLL→FL replacement")
        print("     - cancelled_after_pack (MO3)")
        print("     - never_touched_inventory (MO4)")
        print("     - rto (MO5)")
        print("     - pending (MO6, MO7)")
        print("  ✅ Stats match spec exactly: total=7, packed=6, never_touched=1,")
        print("     returned=3, pending=2, net_sold=1")
        print("  ✅ Reason breakdown: rto=1, customer_return=1, cancelled_after_pack=1")
        print("  ✅ Commit path handles unmatched rows gracefully (exceptions)")
        print("  ✅ Reconciliation summary endpoints working")
        print("  ✅ Phase G & Phase H regression passed")
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
