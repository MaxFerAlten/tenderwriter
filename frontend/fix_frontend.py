import sys
import re

file_path = r'D:\tender\tenderwriter\frontend\src\api\client.ts'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

# Replace TenderImportResponse
new_import_response = """export interface TenderImportResponse {
    message: string;
    tender_id: number;
    document_id: number;
    task_id: string;
    filename: string;
    status: string;
}

export interface DocumentResponse {
    id: number;
    filename: string;
    file_url: string;
    doc_type: string | null;
    file_size: number | null;
    mime_type: string | null;
    ingestion_status: string;
    chunk_count: number;
    error_message: string | null;
    source_kind: string | null;
    ingestion_started_at: string | null;
    ingestion_completed_at: string | null;
    ingestion_job_id: string | null;
    created_at: string | null;
}
"""
text = re.sub(r'export interface TenderImportResponse \{[\s\S]*?\}', new_import_response, text)

# Add active, listDocs, getDoc in tenderApi before uploadDocument
new_tender_methods = """    activate: (id: number) => request<TenderDetail>(`/tenders/${id}/activate`, { method: 'POST' }),
    listDocuments: (id: number) => request<DocumentResponse[]>(`/tenders/${id}/documents`),
    getDocument: (id: number, documentId: number) => request<DocumentResponse>(`/tenders/${id}/documents/${documentId}`),
    streamDocumentStatusUrl: (id: number, documentId: number) => `${API_BASE}/tenders/${id}/documents/${documentId}/stream`,
    uploadDocument: """
text = text.replace('uploadDocument: ', new_tender_methods)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)

print("Replaced successfully")
