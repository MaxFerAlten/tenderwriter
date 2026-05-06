import sys

file_path = r"D:\tender\tenderwriter\backend\app\api\tenders.py"
with open(file_path, encoding="utf-8") as f:
    lines = f.readlines()

new_func = '''@router.post("/{tender_id}/import", status_code=202)
async def import_tender_document(
    tender_id: int,
    request: Request,
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a tender document (PDF/DOCX). RBAC-checked.
    Creates a Document record and enqueues the ingestion task.
    """
    tender = await check_tender_access(tender_id, current_user, db)
    
    # Restrict uploads for finalized tenders
    if tender.status in [TenderStatus.SUBMITTED, TenderStatus.WON, TenderStatus.LOST, TenderStatus.CANCELLED]:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot upload documents to a tender with status '{tender.status.value}'"
        )

    # 1. Create Document record in PENDING state
    doc = Document(
        filename=file.filename or "unknown",
        file_url="",  # Will update after upload
        doc_type="tender",
        file_size=file.size or 0,
        mime_type=file.content_type,
        ingestion_status=IngestionStatus.PENDING,
        uploaded_by=current_user.id,
        tender_id=tender.id,
        source_kind="upload",
    )
    db.add(doc)
    await db.flush()

    # 2. Upload to MinIO
    minio_client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )

    bucket_name = settings.minio_bucket
    if not minio_client.bucket_exists(bucket_name):
        minio_client.make_bucket(bucket_name)

    # Determine user prefix for folder structure
    user_prefix = current_user.email.split('@')[0] if current_user.email else "unknown"

    # Determine structured path
    object_name = get_tender_upload_path(
        user_prefix=user_prefix,
        tender_title=tender.title,
        tender_id=tender.id,
        filename=file.filename
    )
    
    # Read file content to upload
    content = await file.read()
    import io
    file_stream = io.BytesIO(content)
    
    minio_client.put_object(
        bucket_name,
        object_name,
        file_stream,
        length=len(content),
        content_type=file.content_type,
    )

    # 3. Update Document with storage metadata
    doc.storage_bucket = bucket_name
    doc.storage_object_name = object_name
    doc.file_url = f"minio://{bucket_name}/{object_name}"
    await db.flush()

    # 4. Enqueue Ingestion Task
    from app.tasks import index_document_task
    task = index_document_task.delay(doc.id)

    # 5. Save tracking information
    doc.ingestion_job_id = task.id
    
    await db.commit()

    return {
        "message": "Document uploaded and ingestion queued successfully",
        "tender_id": tender_id,
        "document_id": doc.id,
        "task_id": task.id,
        "filename": file.filename,
        "status": "queued",
    }
'''

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if '@router.post("/{tender_id}/import", status_code=202)' in line:
        start_idx = i
    if start_idx != -1 and i > start_idx and "class TenderDecisionRequest(" in line:
        end_idx = i - 3
        break

if start_idx != -1 and end_idx != -1:
    new_lines = lines[:start_idx] + [new_func + "\n\n"] + lines[end_idx + 1 :]
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    print(f"Successfully replaced from line {start_idx} to {end_idx}")
else:
    print(f"Could not find bounds. start: {start_idx}, end: {end_idx}")
    sys.exit(1)
