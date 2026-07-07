#!/usr/bin/env python3
"""
Backend test for Phase — System-generated SSK_XXXXX style code + catalogue codes
Tests the new style code generation, color master, and catalogue SKU endpoints.
"""
import requests
import re
import sys
from typing import Dict, Any, List

# Base URL from frontend/.env
BASE_URL = "https://8084e150-a3b8-4ec1-9c91-cd7e92a259f1.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"

# Global token storage
access_token = None


def login() -> str:
    """Login and return access token."""
    global access_token
    print("\n=== TEST: Login ===")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    print(f"POST /api/auth/login → {resp.status_code}")
    if resp.status_code != 200:
        print(f"ERROR: Login failed with {resp.status_code}: {resp.text}")
        sys.exit(1)
    data = resp.json()
    access_token = data.get("access_token")
    if not access_token:
        print("ERROR: No access_token in login response")
        sys.exit(1)
    print(f"✓ Login successful, got access_token")
    return access_token


def headers() -> Dict[str, str]:
    """Return auth headers."""
    return {"Authorization": f"Bearer {access_token}"}


def test_ssk_style_code_generation():
    """Test 1: SSK style code generation (atomic counter)"""
    print("\n" + "="*80)
    print("TEST 1: SSK STYLE CODE GENERATION (ATOMIC COUNTER)")
    print("="*80)
    
    # Test 1a: POST /api/styles with no code → response.code MUST match ^SSK_\d{5}$
    print("\n--- Test 1a: Create style without code field ---")
    resp = requests.post(f"{BASE_URL}/styles", headers=headers(), json={
        "name": "Alpha Test Style",
        "category": "Footwear"
    })
    print(f"POST /api/styles (no code) → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    
    data = resp.json()
    code1 = data.get("code", "")
    style_id1 = data.get("id", "")
    print(f"Response code: {code1}")
    
    if not re.match(r"^SSK_\d{5}$", code1):
        print(f"❌ FAILED: Code '{code1}' does not match ^SSK_\\d{{5}}$ pattern")
        return False
    print(f"✓ Code matches SSK_XXXXX pattern: {code1}")
    
    # Test 1b: POST /api/styles with user-supplied code → MUST be IGNORED
    print("\n--- Test 1b: Create style with user-supplied code (MUST be ignored) ---")
    resp = requests.post(f"{BASE_URL}/styles", headers=headers(), json={
        "code": "MANUAL-XYZ",
        "name": "Beta Test Style",
        "category": "Footwear"
    })
    print(f"POST /api/styles (code='MANUAL-XYZ') → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    
    data = resp.json()
    code2 = data.get("code", "")
    style_id2 = data.get("id", "")
    print(f"Response code: {code2}")
    
    if code2 == "MANUAL-XYZ":
        print(f"❌ FAILED: User-supplied code 'MANUAL-XYZ' was NOT ignored!")
        return False
    if not re.match(r"^SSK_\d{5}$", code2):
        print(f"❌ FAILED: Code '{code2}' does not match ^SSK_\\d{{5}}$ pattern")
        return False
    print(f"✓ User-supplied code was ignored, system generated: {code2}")
    
    # Test 1c: Create 3 styles in succession and verify strictly ascending consecutive codes
    print("\n--- Test 1c: Create 3 styles in succession (verify consecutive codes) ---")
    codes = []
    style_ids = []
    for i in range(3):
        resp = requests.post(f"{BASE_URL}/styles", headers=headers(), json={
            "name": f"Consecutive Style {i+1}",
            "category": "Footwear"
        })
        if resp.status_code != 200:
            print(f"❌ FAILED: Style {i+1} creation failed with {resp.status_code}: {resp.text}")
            return False
        data = resp.json()
        code = data.get("code", "")
        style_id = data.get("id", "")
        codes.append(code)
        style_ids.append(style_id)
        print(f"Style {i+1}: {code}")
    
    # Extract numeric parts and verify they are consecutive
    nums = []
    for code in codes:
        match = re.match(r"^SSK_(\d{5})$", code)
        if not match:
            print(f"❌ FAILED: Code '{code}' does not match pattern")
            return False
        nums.append(int(match.group(1)))
    
    print(f"Numeric sequences: {nums}")
    for i in range(len(nums) - 1):
        if nums[i+1] != nums[i] + 1:
            print(f"❌ FAILED: Codes are not consecutive: {nums[i]} → {nums[i+1]}")
            return False
    
    print(f"✓ All 3 codes are strictly ascending consecutive: {codes}")
    
    # Store for later tests
    test_ssk_style_code_generation.style_id1 = style_id1
    test_ssk_style_code_generation.code1 = code1
    test_ssk_style_code_generation.style_id2 = style_id2
    test_ssk_style_code_generation.code2 = code2
    test_ssk_style_code_generation.style_ids = style_ids
    test_ssk_style_code_generation.codes = codes
    
    print("\n✅ TEST 1 PASSED: SSK style code generation working correctly")
    return True


def test_style_code_immutability():
    """Test 2: Style code immutability on PATCH"""
    print("\n" + "="*80)
    print("TEST 2: STYLE CODE IMMUTABILITY ON PATCH")
    print("="*80)
    
    style_id = test_ssk_style_code_generation.style_id1
    original_code = test_ssk_style_code_generation.code1
    
    # Test 2a: PATCH with different code → MUST return 400 with "immutable"
    print("\n--- Test 2a: PATCH with different code (MUST be rejected) ---")
    resp = requests.patch(f"{BASE_URL}/styles/{style_id}", headers=headers(), json={
        "code": "HACKED",
        "name": "NewName"
    })
    print(f"PATCH /api/styles/{style_id} (code='HACKED') → {resp.status_code}")
    if resp.status_code != 400:
        print(f"❌ FAILED: Expected 400, got {resp.status_code}: {resp.text}")
        return False
    
    error_detail = resp.json().get("detail", "")
    print(f"Error detail: {error_detail}")
    if "immutable" not in error_detail.lower():
        print(f"❌ FAILED: Error message does not contain 'immutable'")
        return False
    print(f"✓ Code change correctly rejected with 400 and 'immutable' message")
    
    # Test 2b: PATCH with matching code → 200, name updated
    print("\n--- Test 2b: PATCH with matching code (should succeed) ---")
    resp = requests.patch(f"{BASE_URL}/styles/{style_id}", headers=headers(), json={
        "code": original_code,
        "name": "NewName1"
    })
    print(f"PATCH /api/styles/{style_id} (code='{original_code}') → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    
    data = resp.json()
    if data.get("name") != "NewName1":
        print(f"❌ FAILED: Name not updated, got '{data.get('name')}'")
        return False
    if data.get("code") != original_code:
        print(f"❌ FAILED: Code changed from '{original_code}' to '{data.get('code')}'")
        return False
    print(f"✓ PATCH with matching code succeeded, name updated to 'NewName1'")
    
    # Test 2c: PATCH without code field → 200, code unchanged, name updated
    print("\n--- Test 2c: PATCH without code field (should succeed) ---")
    resp = requests.patch(f"{BASE_URL}/styles/{style_id}", headers=headers(), json={
        "name": "NewName2"
    })
    print(f"PATCH /api/styles/{style_id} (no code) → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    
    data = resp.json()
    if data.get("name") != "NewName2":
        print(f"❌ FAILED: Name not updated, got '{data.get('name')}'")
        return False
    if data.get("code") != original_code:
        print(f"❌ FAILED: Code changed from '{original_code}' to '{data.get('code')}'")
        return False
    print(f"✓ PATCH without code succeeded, name updated to 'NewName2', code unchanged")
    
    # Test 2d: GET to confirm code never changed
    print("\n--- Test 2d: GET to confirm code never changed ---")
    resp = requests.get(f"{BASE_URL}/styles/{style_id}", headers=headers())
    print(f"GET /api/styles/{style_id} → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    
    data = resp.json()
    if data.get("code") != original_code:
        print(f"❌ FAILED: Code changed from '{original_code}' to '{data.get('code')}'")
        return False
    print(f"✓ GET confirms code is still '{original_code}'")
    
    print("\n✅ TEST 2 PASSED: Style code immutability working correctly")
    return True


def test_color_master_seed_and_crud():
    """Test 3: Color Master seeding + CRUD"""
    print("\n" + "="*80)
    print("TEST 3: COLOR MASTER SEEDING + CRUD")
    print("="*80)
    
    # Test 3a: GET /api/color-master → returns >= 25 default colors
    print("\n--- Test 3a: GET color-master (verify seeded defaults) ---")
    resp = requests.get(f"{BASE_URL}/color-master", headers=headers())
    print(f"GET /api/color-master → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    
    colors = resp.json()
    print(f"Total colors: {len(colors)}")
    if len(colors) < 25:
        print(f"❌ FAILED: Expected >= 25 colors, got {len(colors)}")
        return False
    print(f"✓ Found {len(colors)} colors (>= 25)")
    
    # Verify structure: each has {id, color_name, color_code (2-3 upper alpha), active:true}
    for color in colors[:3]:  # Check first 3
        if not all(k in color for k in ["id", "color_name", "color_code", "active"]):
            print(f"❌ FAILED: Color missing required fields: {color}")
            return False
        code = color.get("color_code", "")
        if not (2 <= len(code) <= 3) or not code.isupper() or not code.isalpha():
            print(f"❌ FAILED: Invalid color_code format: '{code}'")
            return False
    print(f"✓ All colors have correct structure")
    
    # Test 3b: Verify specific seeded pairs exist
    print("\n--- Test 3b: Verify specific seeded color pairs ---")
    required_pairs = [
        ("Tan", "TN"),
        ("Beige", "BG"),
        ("Gold", "GD"),
        ("Silver", "SL"),
        ("Blue", "BL"),
        ("Gunmetal", "GN"),
        ("Black", "BK"),
        ("Deep Peach", "DP"),
    ]
    
    color_map = {c["color_name"]: c["color_code"] for c in colors}
    for name, expected_code in required_pairs:
        if name not in color_map:
            print(f"❌ FAILED: Color '{name}' not found in seeded colors")
            return False
        if color_map[name] != expected_code:
            print(f"❌ FAILED: Color '{name}' has code '{color_map[name]}', expected '{expected_code}'")
            return False
        print(f"✓ ({name}, {expected_code}) exists")
    
    # Test 3c: POST new color with lowercase code → stored as uppercase
    print("\n--- Test 3c: POST new color (lowercase code → uppercase) ---")
    # Use a unique color name and code to avoid collision with previous test runs
    import random
    import string
    
    # Get existing color codes to avoid collision
    resp_existing = requests.get(f"{BASE_URL}/color-master", headers=headers())
    existing_codes = {c["color_code"] for c in resp_existing.json()}
    
    # Generate a unique 2-letter code
    unique_code = None
    for _ in range(100):  # Try up to 100 times
        candidate = ''.join(random.choices(string.ascii_lowercase, k=2))
        if candidate.upper() not in existing_codes:
            unique_code = candidate
            break
    
    if not unique_code:
        print("❌ FAILED: Could not generate unique color code")
        return False
    
    unique_suffix = random.randint(1000, 9999)
    color_name = f"TestColor{unique_suffix}"
    
    resp = requests.post(f"{BASE_URL}/color-master", headers=headers(), json={
        "color_name": color_name,
        "color_code": unique_code
    })
    print(f"POST /api/color-master ({color_name}, {unique_code}) → {resp.status_code}")
    if resp.status_code not in [200, 201]:
        print(f"❌ FAILED: Expected 200/201, got {resp.status_code}: {resp.text}")
        return False
    
    data = resp.json()
    turquoise_id = data.get("id")
    expected_upper_code = unique_code.upper()
    if data.get("color_code") != expected_upper_code:
        print(f"❌ FAILED: color_code not uppercased, got '{data.get('color_code')}', expected '{expected_upper_code}'")
        return False
    print(f"✓ Color created with code '{expected_upper_code}' (uppercased from '{unique_code}')")
    
    # Test 3d: POST duplicate code → 409
    print("\n--- Test 3d: POST duplicate code (should fail with 409) ---")
    resp = requests.post(f"{BASE_URL}/color-master", headers=headers(), json={
        "color_name": "Foo",
        "color_code": "TN"
    })
    print(f"POST /api/color-master (Foo, TN) → {resp.status_code}")
    if resp.status_code != 409:
        print(f"❌ FAILED: Expected 409, got {resp.status_code}: {resp.text}")
        return False
    print(f"✓ Duplicate code 'TN' correctly rejected with 409")
    
    # Test 3e: POST duplicate name → 409
    print("\n--- Test 3e: POST duplicate name (should fail with 409) ---")
    resp = requests.post(f"{BASE_URL}/color-master", headers=headers(), json={
        "color_name": color_name,
        "color_code": "XY"
    })
    print(f"POST /api/color-master ({color_name}, XY) → {resp.status_code}")
    if resp.status_code != 409:
        print(f"❌ FAILED: Expected 409, got {resp.status_code}: {resp.text}")
        return False
    print(f"✓ Duplicate name '{color_name}' correctly rejected with 409")
    
    # Test 3f: POST invalid code (too long) → 422
    print("\n--- Test 3f: POST invalid code (too long) → 422 ---")
    resp = requests.post(f"{BASE_URL}/color-master", headers=headers(), json={
        "color_name": "Bad",
        "color_code": "XXXX"
    })
    print(f"POST /api/color-master (Bad, XXXX) → {resp.status_code}")
    if resp.status_code != 422:
        print(f"❌ FAILED: Expected 422, got {resp.status_code}: {resp.text}")
        return False
    print(f"✓ Invalid code 'XXXX' (too long) correctly rejected with 422")
    
    # Test 3g: POST invalid code (non-alpha) → 422
    print("\n--- Test 3g: POST invalid code (non-alpha) → 422 ---")
    resp = requests.post(f"{BASE_URL}/color-master", headers=headers(), json={
        "color_name": "Bad2",
        "color_code": "1A"
    })
    print(f"POST /api/color-master (Bad2, 1A) → {resp.status_code}")
    if resp.status_code != 422:
        print(f"❌ FAILED: Expected 422, got {resp.status_code}: {resp.text}")
        return False
    print(f"✓ Invalid code '1A' (non-alpha) correctly rejected with 422")
    
    # Test 3h: POST empty name → 422
    print("\n--- Test 3h: POST empty name → 422 ---")
    resp = requests.post(f"{BASE_URL}/color-master", headers=headers(), json={
        "color_name": "",
        "color_code": "AB"
    })
    print(f"POST /api/color-master ('', AB) → {resp.status_code}")
    if resp.status_code != 422:
        print(f"❌ FAILED: Expected 422, got {resp.status_code}: {resp.text}")
        return False
    print(f"✓ Empty name correctly rejected with 422")
    
    # Test 3i: PUT to set active=false
    print("\n--- Test 3i: PUT to set active=false ---")
    resp = requests.put(f"{BASE_URL}/color-master/{turquoise_id}", headers=headers(), json={
        "active": False
    })
    print(f"PUT /api/color-master/{turquoise_id} (active=false) → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    
    data = resp.json()
    if data.get("active") != False:
        print(f"❌ FAILED: active not set to false, got {data.get('active')}")
        return False
    print(f"✓ Color set to active=false")
    
    # Test 3j: PUT duplicate code on update → 409
    print("\n--- Test 3j: PUT duplicate code on update → 409 ---")
    resp = requests.put(f"{BASE_URL}/color-master/{turquoise_id}", headers=headers(), json={
        "color_code": "TN"
    })
    print(f"PUT /api/color-master/{turquoise_id} (color_code=TN) → {resp.status_code}")
    if resp.status_code != 409:
        print(f"❌ FAILED: Expected 409, got {resp.status_code}: {resp.text}")
        return False
    print(f"✓ Duplicate code 'TN' on update correctly rejected with 409")
    
    # Test 3k: PUT to update name → 200
    print("\n--- Test 3k: PUT to update name → 200 ---")
    new_name = f"{color_name} Deep"
    resp = requests.put(f"{BASE_URL}/color-master/{turquoise_id}", headers=headers(), json={
        "color_name": new_name
    })
    print(f"PUT /api/color-master/{turquoise_id} (color_name='{new_name}') → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    
    data = resp.json()
    if data.get("color_name") != new_name:
        print(f"❌ FAILED: color_name not updated, got '{data.get('color_name')}'")
        return False
    print(f"✓ Color name updated to '{new_name}'")
    
    # Test 3l: GET with search filter
    print("\n--- Test 3l: GET with search filter ---")
    search_term = color_name[:4].lower()
    resp = requests.get(f"{BASE_URL}/color-master?search={search_term}", headers=headers())
    print(f"GET /api/color-master?search={search_term} → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    
    results = resp.json()
    if len(results) == 0:
        print(f"❌ FAILED: Search for '{search_term}' returned no results")
        return False
    if not any(color_name in r.get("color_name", "") for r in results):
        print(f"❌ FAILED: Search results don't contain {color_name}")
        return False
    print(f"✓ Search for '{search_term}' returned {len(results)} result(s) including {color_name}")
    
    # Test 3m: GET with active=false filter
    print("\n--- Test 3m: GET with active=false filter ---")
    resp = requests.get(f"{BASE_URL}/color-master?active=false", headers=headers())
    print(f"GET /api/color-master?active=false → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    
    results = resp.json()
    if len(results) == 0:
        print(f"❌ FAILED: No inactive colors found (we just set {color_name} to inactive)")
        return False
    if not all(r.get("active") == False for r in results):
        print(f"❌ FAILED: Some results have active=true")
        return False
    print(f"✓ Filter active=false returned {len(results)} inactive color(s)")
    
    # Store turquoise_id for later
    test_color_master_seed_and_crud.turquoise_id = turquoise_id
    
    print("\n✅ TEST 3 PASSED: Color Master seeding + CRUD working correctly")
    return True


def test_catalogue_codes_endpoint():
    """Test 4: Catalogue codes endpoint (build_catalogue_sku)"""
    print("\n" + "="*80)
    print("TEST 4: CATALOGUE CODES ENDPOINT (build_catalogue_sku)")
    print("="*80)
    
    # Test 4a: Create a fresh style and set lifecycle with planned_colors and planned_sizes
    print("\n--- Test 4a: Create style and set lifecycle ---")
    resp = requests.post(f"{BASE_URL}/styles", headers=headers(), json={
        "name": "Catalogue Test Style",
        "category": "Footwear"
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: Style creation failed with {resp.status_code}: {resp.text}")
        return False
    
    style_data = resp.json()
    style_id = style_data.get("id")
    style_code = style_data.get("code")
    print(f"✓ Created style {style_code} (id={style_id})")
    
    # Use a unique unmapped color name to avoid collision
    import random
    unmapped_color = f"UnmappedColor{random.randint(1000, 9999)}"
    
    # Set lifecycle with planned_colors and planned_sizes
    resp = requests.put(f"{BASE_URL}/style-lifecycle/{style_id}", headers=headers(), json={
        "planned_colors": ["Tan", "Gunmetal", "Silver", unmapped_color],
        "planned_sizes": ["36", "37", "38", "39", "40"]
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: Lifecycle update failed with {resp.status_code}: {resp.text}")
        return False
    print(f"✓ Set lifecycle with planned_colors=['Tan','Gunmetal','Silver','{unmapped_color}'] and planned_sizes=['36','37','38','39','40']")
    
    # Test 4b: GET catalogue-codes and verify structure
    print("\n--- Test 4b: GET catalogue-codes (verify structure) ---")
    resp = requests.get(f"{BASE_URL}/styles/{style_id}/catalogue-codes", headers=headers())
    print(f"GET /api/styles/{style_id}/catalogue-codes → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    
    data = resp.json()
    
    # Verify top-level structure
    required_keys = ["style_id", "style_code", "style_name", "colors", "sizes", "rows", "unmapped_colors"]
    for key in required_keys:
        if key not in data:
            print(f"❌ FAILED: Missing key '{key}' in response")
            return False
    print(f"✓ Response has all required keys: {required_keys}")
    
    # Verify values
    if data["style_id"] != style_id:
        print(f"❌ FAILED: style_id mismatch: {data['style_id']} != {style_id}")
        return False
    if data["style_code"] != style_code:
        print(f"❌ FAILED: style_code mismatch: {data['style_code']} != {style_code}")
        return False
    print(f"✓ style_id and style_code match")
    
    # Verify colors and sizes
    if data["colors"] != ["Tan", "Gunmetal", "Silver", unmapped_color]:
        print(f"❌ FAILED: colors mismatch: {data['colors']}")
        return False
    if data["sizes"] != ["36", "37", "38", "39", "40"]:
        print(f"❌ FAILED: sizes mismatch: {data['sizes']}")
        return False
    print(f"✓ colors and sizes match planned values")
    
    # Verify rows count (4 colors)
    if len(data["rows"]) != 4:
        print(f"❌ FAILED: Expected 4 rows, got {len(data['rows'])}")
        return False
    print(f"✓ rows has 4 entries (one per color)")
    
    # Test 4c: Verify Tan row (mapped)
    print("\n--- Test 4c: Verify Tan row (mapped) ---")
    tan_row = next((r for r in data["rows"] if r["color_name"] == "Tan"), None)
    if not tan_row:
        print(f"❌ FAILED: Tan row not found")
        return False
    
    if tan_row["color_code"] != "TN":
        print(f"❌ FAILED: Tan color_code is '{tan_row['color_code']}', expected 'TN'")
        return False
    if tan_row["mapped"] != True:
        print(f"❌ FAILED: Tan mapped is {tan_row['mapped']}, expected True")
        return False
    
    expected_group_sku = f"{style_code}-TN"
    if tan_row["group_sku"] != expected_group_sku:
        print(f"❌ FAILED: Tan group_sku is '{tan_row['group_sku']}', expected '{expected_group_sku}'")
        return False
    print(f"✓ Tan row: color_code='TN', mapped=true, group_sku='{expected_group_sku}'")
    
    # Verify size_skus
    if len(tan_row["size_skus"]) != 5:
        print(f"❌ FAILED: Tan size_skus has {len(tan_row['size_skus'])} entries, expected 5")
        return False
    
    # Find size "38" and verify leaf_sku
    size_38 = next((s for s in tan_row["size_skus"] if s["size"] == "38"), None)
    if not size_38:
        print(f"❌ FAILED: Size '38' not found in Tan size_skus")
        return False
    
    expected_leaf_sku = f"{style_code}-TN-38"
    if size_38["leaf_sku"] != expected_leaf_sku:
        print(f"❌ FAILED: Size 38 leaf_sku is '{size_38['leaf_sku']}', expected '{expected_leaf_sku}'")
        return False
    print(f"✓ Tan size_skus has 5 entries, size '38' leaf_sku='{expected_leaf_sku}'")
    
    # Test 4d: Verify Gunmetal row (mapped)
    print("\n--- Test 4d: Verify Gunmetal row (mapped) ---")
    gunmetal_row = next((r for r in data["rows"] if r["color_name"] == "Gunmetal"), None)
    if not gunmetal_row:
        print(f"❌ FAILED: Gunmetal row not found")
        return False
    
    if gunmetal_row["color_code"] != "GN":
        print(f"❌ FAILED: Gunmetal color_code is '{gunmetal_row['color_code']}', expected 'GN'")
        return False
    if gunmetal_row["mapped"] != True:
        print(f"❌ FAILED: Gunmetal mapped is {gunmetal_row['mapped']}, expected True")
        return False
    
    expected_group_sku = f"{style_code}-GN"
    if gunmetal_row["group_sku"] != expected_group_sku:
        print(f"❌ FAILED: Gunmetal group_sku is '{gunmetal_row['group_sku']}', expected '{expected_group_sku}'")
        return False
    print(f"✓ Gunmetal row: color_code='GN', mapped=true, group_sku='{expected_group_sku}'")
    
    # Test 4e: Verify Silver row (mapped)
    print("\n--- Test 4e: Verify Silver row (mapped) ---")
    silver_row = next((r for r in data["rows"] if r["color_name"] == "Silver"), None)
    if not silver_row:
        print(f"❌ FAILED: Silver row not found")
        return False
    
    if silver_row["color_code"] != "SL":
        print(f"❌ FAILED: Silver color_code is '{silver_row['color_code']}', expected 'SL'")
        return False
    if silver_row["mapped"] != True:
        print(f"❌ FAILED: Silver mapped is {silver_row['mapped']}, expected True")
        return False
    
    expected_group_sku = f"{style_code}-SL"
    if silver_row["group_sku"] != expected_group_sku:
        print(f"❌ FAILED: Silver group_sku is '{silver_row['group_sku']}', expected '{expected_group_sku}'")
        return False
    print(f"✓ Silver row: color_code='SL', mapped=true, group_sku='{expected_group_sku}'")
    
    # Test 4f: Verify unmapped color row (unmapped)
    print(f"\n--- Test 4f: Verify {unmapped_color} row (unmapped) ---")
    unmapped_row = next((r for r in data["rows"] if r["color_name"] == unmapped_color), None)
    if not unmapped_row:
        print(f"❌ FAILED: {unmapped_color} row not found")
        return False
    
    if unmapped_row["color_code"] != "":
        print(f"❌ FAILED: {unmapped_color} color_code is '{unmapped_row['color_code']}', expected ''")
        return False
    if unmapped_row["mapped"] != False:
        print(f"❌ FAILED: {unmapped_color} mapped is {unmapped_row['mapped']}, expected False")
        return False
    if unmapped_row["group_sku"] != "":
        print(f"❌ FAILED: {unmapped_color} group_sku is '{unmapped_row['group_sku']}', expected ''")
        return False
    
    # Verify all size_skus have empty leaf_sku
    for size_sku in unmapped_row["size_skus"]:
        if size_sku["leaf_sku"] != "":
            print(f"❌ FAILED: {unmapped_color} size {size_sku['size']} has non-empty leaf_sku: '{size_sku['leaf_sku']}'")
            return False
    print(f"✓ {unmapped_color} row: color_code='', mapped=false, group_sku='', all leaf_skus empty")
    
    # Test 4g: Verify unmapped_colors
    print("\n--- Test 4g: Verify unmapped_colors ---")
    if data["unmapped_colors"] != [unmapped_color]:
        print(f"❌ FAILED: unmapped_colors is {data['unmapped_colors']}, expected ['{unmapped_color}']")
        return False
    print(f"✓ unmapped_colors == ['{unmapped_color}']")
    
    # Test 4h: Add unmapped color to color_master and re-GET catalogue-codes
    print(f"\n--- Test 4h: Add {unmapped_color} to color_master and verify mapping ---")
    
    # Get existing color codes to avoid collision
    resp_existing = requests.get(f"{BASE_URL}/color-master", headers=headers())
    existing_codes = {c["color_code"] for c in resp_existing.json()}
    
    # Generate a unique 2-letter code for the unmapped color
    import string
    unique_code_for_unmapped = None
    for _ in range(100):
        candidate = ''.join(random.choices(string.ascii_lowercase, k=2))
        if candidate.upper() not in existing_codes:
            unique_code_for_unmapped = candidate.upper()
            break
    
    if not unique_code_for_unmapped:
        print("❌ FAILED: Could not generate unique color code for unmapped color")
        return False
    
    resp = requests.post(f"{BASE_URL}/color-master", headers=headers(), json={
        "color_name": unmapped_color,
        "color_code": unique_code_for_unmapped
    })
    if resp.status_code not in [200, 201]:
        print(f"❌ FAILED: {unmapped_color} color creation failed with {resp.status_code}: {resp.text}")
        return False
    print(f"✓ Added {unmapped_color} color with code '{unique_code_for_unmapped}'")
    
    # Re-GET catalogue-codes
    resp = requests.get(f"{BASE_URL}/styles/{style_id}/catalogue-codes", headers=headers())
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    
    data = resp.json()
    
    # Verify unmapped color is now mapped
    unmapped_row_after = next((r for r in data["rows"] if r["color_name"] == unmapped_color), None)
    if not unmapped_row_after:
        print(f"❌ FAILED: {unmapped_color} row not found after adding to color_master")
        return False
    
    if unmapped_row_after["color_code"] != unique_code_for_unmapped:
        print(f"❌ FAILED: {unmapped_color} color_code is '{unmapped_row_after['color_code']}', expected '{unique_code_for_unmapped}'")
        return False
    if unmapped_row_after["mapped"] != True:
        print(f"❌ FAILED: {unmapped_color} mapped is {unmapped_row_after['mapped']}, expected True")
        return False
    
    expected_group_sku = f"{style_code}-{unique_code_for_unmapped}"
    if unmapped_row_after["group_sku"] != expected_group_sku:
        print(f"❌ FAILED: {unmapped_color} group_sku is '{unmapped_row_after['group_sku']}', expected '{expected_group_sku}'")
        return False
    print(f"✓ {unmapped_color} row now: color_code='{unique_code_for_unmapped}', mapped=true, group_sku='{expected_group_sku}'")
    
    # Verify unmapped_colors is now empty
    if data["unmapped_colors"] != []:
        print(f"❌ FAILED: unmapped_colors is {data['unmapped_colors']}, expected []")
        return False
    print(f"✓ unmapped_colors == []")
    
    # Test 4i: Create style with NO lifecycle → empty fallback
    print("\n--- Test 4i: Create style with NO lifecycle (fallback path) ---")
    resp = requests.post(f"{BASE_URL}/styles", headers=headers(), json={
        "name": "No Lifecycle Style",
        "category": "Footwear"
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: Style creation failed with {resp.status_code}: {resp.text}")
        return False
    
    no_lifecycle_style_id = resp.json().get("id")
    print(f"✓ Created style without lifecycle (id={no_lifecycle_style_id})")
    
    # GET catalogue-codes (should return empty arrays)
    resp = requests.get(f"{BASE_URL}/styles/{no_lifecycle_style_id}/catalogue-codes", headers=headers())
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    
    data = resp.json()
    if data["colors"] != [] or data["sizes"] != [] or data["rows"] != []:
        print(f"❌ FAILED: Expected empty arrays for style without lifecycle, got colors={data['colors']}, sizes={data['sizes']}, rows={data['rows']}")
        return False
    print(f"✓ Style without lifecycle returns empty colors/sizes/rows arrays")
    
    print("\n✅ TEST 4 PASSED: Catalogue codes endpoint working correctly")
    return True


def test_regression_smoke():
    """Test 5: Regression smoke (existing endpoints still work)"""
    print("\n" + "="*80)
    print("TEST 5: REGRESSION SMOKE (EXISTING ENDPOINTS)")
    print("="*80)
    
    # Test 5a: POST /api/auth/login
    print("\n--- Test 5a: POST /api/auth/login ---")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    print(f"POST /api/auth/login → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    print(f"✓ Login working")
    
    # Test 5b: GET /api/fg-inventory
    print("\n--- Test 5b: GET /api/fg-inventory ---")
    resp = requests.get(f"{BASE_URL}/fg-inventory", headers=headers())
    print(f"GET /api/fg-inventory → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    print(f"✓ FG inventory listing working")
    
    # Test 5c: POST /api/fg-inventory/movements (use a style created in test 1)
    print("\n--- Test 5c: POST /api/fg-inventory/movements ---")
    style_id = test_ssk_style_code_generation.style_id1
    resp = requests.post(f"{BASE_URL}/fg-inventory/movements", headers=headers(), json={
        "style_id": style_id,
        "color": "Black",
        "size": "38",
        "movement_type": "production_in",
        "quantity": 10,
        "reference_type": "job",
        "reference_id": "TEST-JOB-001"
    })
    print(f"POST /api/fg-inventory/movements → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    print(f"✓ FG inventory movement working")
    
    # Test 5d: GET /api/fg-inventory/movements
    print("\n--- Test 5d: GET /api/fg-inventory/movements ---")
    resp = requests.get(f"{BASE_URL}/fg-inventory/movements", headers=headers())
    print(f"GET /api/fg-inventory/movements → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    print(f"✓ FG inventory movements listing working")
    
    # Test 5e: GET /api/sku-map
    print("\n--- Test 5e: GET /api/sku-map ---")
    resp = requests.get(f"{BASE_URL}/sku-map", headers=headers())
    print(f"GET /api/sku-map → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    print(f"✓ SKU map listing working")
    
    # Test 5f: GET /api/style-lifecycle/{style_id}
    print("\n--- Test 5f: GET /api/style-lifecycle/{style_id} ---")
    resp = requests.get(f"{BASE_URL}/style-lifecycle/{style_id}", headers=headers())
    print(f"GET /api/style-lifecycle/{style_id} → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}: {resp.text}")
        return False
    print(f"✓ Style lifecycle endpoint working")
    
    print("\n✅ TEST 5 PASSED: All regression smoke tests passed")
    return True


def main():
    """Run all tests."""
    print("="*80)
    print("BACKEND TEST: SSK_XXXXX STYLE CODE + CATALOGUE CODES")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Admin: {ADMIN_EMAIL}")
    
    # Login first
    login()
    
    # Run all tests
    results = []
    
    results.append(("SSK Style Code Generation", test_ssk_style_code_generation()))
    results.append(("Style Code Immutability", test_style_code_immutability()))
    results.append(("Color Master Seed + CRUD", test_color_master_seed_and_crud()))
    results.append(("Catalogue Codes Endpoint", test_catalogue_codes_endpoint()))
    results.append(("Regression Smoke", test_regression_smoke()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
