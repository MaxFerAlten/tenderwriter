import sys
import os

# Add the current directory to sys.path
sys.path.append(os.getcwd())

try:
    print("Importing app.main...")
    from app.main import app
    print("Successfully imported app.main")

    print("Importing app.api.auth...")
    from app.api import auth
    print("Successfully imported app.api.auth")

    print("Importing app.api.tenders...")
    from app.api import tenders
    print("Successfully imported app.api.tenders")

    print("Checking get_current_user in auth...")
    if not hasattr(auth, 'get_current_user'):
        raise Exception("get_current_user not found in auth")
    
    print("Checking import_tender_document in tenders...")
    # Typically routes are registered, checking function existence
    if not hasattr(tenders, 'import_tender_document'):
         raise Exception("import_tender_document not found in tenders")

    print("All critical imports and checks successful.")
except Exception as e:
    print(f"Verification failed: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
