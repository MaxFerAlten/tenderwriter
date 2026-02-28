import fitz
import requests
import time
import sys
import os

BASE_URL = "http://localhost:8000/api"

def create_dummy_pdf(filename="test_rag_doc.pdf"):
    """Creates a simple valid PDF with PyMuPDF."""
    doc = fitz.open()
    page = doc.new_page()
    text = "This is a certification test document for HybridRAG ingestion. The secret code is OMEGA-X99."
    page.insert_text(fitz.Point(50, 50), text, fontsize=12)
    doc.save(filename)
    doc.close()
    return filename

def run_test():
    print("--- Starting PDF RAG Ingestion Test ---")
    
    # 1. Create PDF
    pdf_path = create_dummy_pdf()
    print(f"[+] Created dummy PDF: {pdf_path}")
    
    # 2. Auth
    email = f"pdf_tester_{int(time.time())}@example.com"
    password = "password123"
    
    try:
        resp = requests.post(f"{BASE_URL}/auth/register", json={
            "email": email, "name": "PDF Tester", "password": password
        })
    except requests.exceptions.ConnectionError:
        print("\n[SKIP] Backend is not reachable at localhost:8000.")
        print("Please make sure the backend server (FastAPI) and MinIO/Qdrant are running to execute this test.")
        os.remove(pdf_path)
        sys.exit(0)
    
    token = None
    if resp.status_code == 201:
         token = resp.json()["access_token"]
    else:
         resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
         if resp.status_code == 200:
             token = resp.json()["access_token"]
         else:
             print(f"[FAIL] Auth failed. Status: {resp.status_code}. Response: {resp.text}")
             sys.exit(1)
             
    headers = {"Authorization": f"Bearer {token}"}
    print("[+] Authenticated")

    # 3. Create Tender
    resp = requests.post(f"{BASE_URL}/tenders", headers=headers, json={
        "title": "PDF Ingestion Tender Test", "description": "Automated Certification Test"
    })
    if resp.status_code != 201:
        print(f"[FAIL] Tender creation failed: {resp.text}")
        sys.exit(1)
    tender_id = resp.json()["id"]
    print(f"[+] Created Tender ID: {tender_id}")
    
    # 4. Upload PDF
    print(f"[+] Uploading PDF to tender {tender_id}...")
    with open(pdf_path, "rb") as f:
        files = {'file': (os.path.basename(pdf_path), f, 'application/pdf')}
        resp = requests.post(f"{BASE_URL}/tenders/{tender_id}/import", headers=headers, files=files)
        
    if resp.status_code != 202:
        print(f"[FAIL] File upload failed: {resp.text}")
        sys.exit(1)
        
    upload_result = resp.json()
    stats = upload_result.get("stats", {})
    chunks = stats.get("chunks", 0)
    print(f"[+] PDF uploaded successfully. Ingestion stats: {stats}")
    
    if chunks == 0:
        print("[FAIL] Ingestion produced 0 chunks. PDF parsing might have failed or unstructured is not working.")
        sys.exit(1)
        
    # 5. Search in RAG
    print("[+] Testing RAG retrieval for specific content...")
    time.sleep(2) # Give indexers a moment if async (though it's awaited in the handler)
    
    resp = requests.post(f"{BASE_URL}/rag/query", headers=headers, json={
        "query": "OMEGA-X99",
        "mode": "search",
        "top_k": 3
    })
    
    if resp.status_code != 200:
        print(f"[FAIL] RAG query failed: {resp.text}")
        sys.exit(1)
        
    search_res = resp.json()
    sources = search_res.get("sources", [])
    
    found = False
    for s in sources:
        if "OMEGA-X99" in s.get("text", ""):
            found = True
            break
            
    if found:
        print("\n[PASS] Successfully found the ingested PDF content in RAG!")
    else:
        print(f"\n[FAIL] Could not find 'OMEGA-X99' in RAG sources. \nSources returned: {sources}")
        sys.exit(1)
        
    # Cleanup
    if os.path.exists(pdf_path):
         os.remove(pdf_path)
         
    print("--- Test Completed Correctly ---")

if __name__ == "__main__":
    run_test()
