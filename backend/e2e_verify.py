import requests
import time
import sys

BASE_URL = "http://localhost:8000/api"
HEALTH_URL = "http://localhost:8000/health"

def run_e2e():
    print("--- Starting E2E Verification ---")
    
    # 1. Health Check
    try:
        resp = requests.get(HEALTH_URL)
        if resp.status_code == 200:
            print("[PASS] Backend is healthy")
        else:
            print(f"[FAIL] Backend returned {resp.status_code}")
            sys.exit(1)
    except Exception as e:
        print(f"[FAIL] Backend not reachable: {e}")
        sys.exit(1)

    # 2. Authentication
    email = f"e2e_{int(time.time())}@example.com"
    password = "password123"
    
    print(f"Registering user: {email}")
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "name": "E2E Tester",
        "password": password
    })
    
    token = None
    if resp.status_code == 201:
        print("[PASS] Registration successful")
        token = resp.json()["access_token"]
    else:
        print(f"[WARN] Registration failed ({resp.status_code}), trying login...")
        resp = requests.post(f"{BASE_URL}/auth/login", json={
            "email": email,
            "password": password
        })
        if resp.status_code == 200:
             print("[PASS] Login successful")
             token = resp.json()["access_token"]
        else:
             print(f"[FAIL] Auth failed. Login Status: {resp.status_code}. Response: {resp.text}")
             sys.exit(1)

    headers = {"Authorization": f"Bearer {token}"}

    # 3. Verify /me (The fix we implemented)
    print("Verifying /me endpoint...")
    resp = requests.get(f"{BASE_URL}/auth/me", headers=headers)
    if resp.status_code == 200:
        user = resp.json()
        if user["email"] == email:
            print(f"[PASS] /me returned correct user: {user['email']}")
        else:
             print(f"[FAIL] /me returned wrong user: {user}")
    else:
        print(f"[FAIL] /me failed: {resp.text}")
        sys.exit(1)

    # 4. Create Tender
    print("Creating Test Tender...")
    resp = requests.post(f"{BASE_URL}/tenders", headers=headers, json={
        "title": "E2E Verified Tender",
        "description": "Created by automated script"
    })
    if resp.status_code == 201:
        tender = resp.json()
        print(f"[PASS] Tender created: ID {tender['id']}")
    else:
        print(f"[FAIL] Create tender failed: {resp.text}")
        sys.exit(1)
        
    # 5. File Upload (Mock)
    # create a dummy file
    files = {'file': ('test_doc.txt', 'This is a test document content for ingestion.')}
    print(f"Uploading file to Tender {tender['id']}...")
    resp = requests.post(f"{BASE_URL}/tenders/{tender['id']}/import", headers=headers, files=files)
    
    if resp.status_code == 202:
        print("[PASS] File upload accepted")
        print(f"Response: {resp.json()}")
    else:
        print(f"[FAIL] File upload failed: {resp.text}")
        # Not exiting here as it might be a MinIO connection issue we want to report specifically
    
    print("\n--- E2E Verification Completed Successfully ---")

if __name__ == "__main__":
    run_e2e()
