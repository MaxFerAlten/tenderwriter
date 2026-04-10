import sys
import re

file_path = r'D:\tender\tenderwriter\frontend\src\pages\Dashboard.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Update handleUpload
old_handleUpload = """    const handleUpload = async (id: number, file: File) => {
        const tenderTitle = tenders.find((item) => item.id === id)?.title || `Tender ${id}`;
        try {
            setError(null);
            setUploadAlert(null);
            const response: TenderImportResponse = await tenderApi.uploadDocument(id, file);
            const warnings = response.stats.warnings || [];
            if (warnings.length > 0) {
                setUploadAlert({
                    title: 'Import completed with warnings',
                    tenderTitle,
                    filename: file.name,
                    warnings,
                    extractionMethod: response.stats.requirement_extraction_method || null,
                });
            }
            warmChatExperience(id);
            // Refresh to see status change from DRAFT -> ACTIVE
            await loadTenders();
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Failed to upload document';
            setError(message);
            setUploadAlert({
                title: 'Document upload failed',
                tenderTitle,
                filename: file.name,
                warnings: [
                    {
                        code: 'upload_failed',
                        title: 'Upload error',
                        message,
                        severity: 'error',
                        fallback_applied: false,
                    },
                ],
            });
            throw err;
        }
    };"""

new_handleUpload = """    const [ingestionStatuses, setIngestionStatuses] = useState<Record<number, { status: string, error?: string }>>({});

    const handleUpload = async (id: number, file: File) => {
        const tenderTitle = tenders.find((item) => item.id === id)?.title || `Tender ${id}`;
        try {
            setError(null);
            setUploadAlert(null);
            const response = await tenderApi.uploadDocument(id, file);
            
            // Start SSE listener
            setIngestionStatuses(prev => ({ ...prev, [id]: { status: 'processing' } }));
            
            const eventSource = new EventSource(tenderApi.streamDocumentStatusUrl(id, response.document_id));
            
            eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.error) {
                    setIngestionStatuses(prev => ({ ...prev, [id]: { status: 'failed', error: data.error } }));
                    eventSource.close();
                    return;
                }
                
                setIngestionStatuses(prev => ({ ...prev, [id]: { status: data.status, error: data.error_message } }));
                
                if (data.status === 'completed' || data.status === 'failed') {
                    eventSource.close();
                    if (data.status === 'completed') {
                        warmChatExperience(id);
                        loadTenders();
                    } else {
                        setError(`Ingestion failed: ${data.error_message || 'Unknown error'}`);
                    }
                }
            };
            
            eventSource.onerror = () => {
                setIngestionStatuses(prev => ({ ...prev, [id]: { status: 'failed', error: 'EventSource error' } }));
                eventSource.close();
            };
            
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Failed to upload document';
            setError(message);
            throw err;
        }
    };"""

text = text.replace(old_handleUpload, new_handleUpload)

# 2. Update TenderCard to show ingestion status
old_tender_card_args = "function TenderCard({ tender, index, onUpload, onCreateProposal, onEditProposal, onSubmit, onOpenChat, onWarmChat, onOpenFullChat }: { tender: Tender; index: number; onUpload: (id: number, file: File) => Promise<void>; onCreateProposal: (tenderId: number | null) => void; onEditProposal: (proposalId: number) => void; onSubmit: (id: number) => Promise<void>; onOpenChat: (id: number) => void; onWarmChat: (id: number) => void; onOpenFullChat: (id: number) => void }) {"
new_tender_card_args = "function TenderCard({ tender, index, ingestionStatus, onUpload, onActivate, onCreateProposal, onEditProposal, onSubmit, onOpenChat, onWarmChat, onOpenFullChat }: { tender: Tender; index: number; ingestionStatus?: { status: string, error?: string }; onUpload: (id: number, file: File) => Promise<void>; onActivate: (id: number) => Promise<void>; onCreateProposal: (tenderId: number | null) => void; onEditProposal: (proposalId: number) => void; onSubmit: (id: number) => Promise<void>; onOpenChat: (id: number) => void; onWarmChat: (id: number) => void; onOpenFullChat: (id: number) => void }) {"

old_upload_button = """                {!['submitted', 'won', 'lost', 'cancelled'].includes(tender.status) && (
                    <label className="btn btn-secondary btn-sm" style={{ cursor: uploading ? 'not-allowed' : 'pointer', fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}>
                        {uploading ? <Loader2 size={12} className="spin" /> : success ? <Check size={12} color="#10b981" /> : <Upload size={12} />}
                        {uploading ? 'Uploading...' : success ? 'Uploaded' : 'Upload PDF'}
                        <input
                            type="file"
                            accept=".pdf,.docx,.txt"
                            style={{ display: 'none' }}
                            onChange={handleFileChange}
                            disabled={uploading}
                        />
                    </label>
                )}"""

new_upload_button = """                {tender.status === 'draft' && (!ingestionStatus || ingestionStatus.status === 'failed') && (
                    <label className="btn btn-secondary btn-sm" style={{ cursor: uploading ? 'not-allowed' : 'pointer', fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}>
                        {uploading ? <Loader2 size={12} className="spin" /> : <Upload size={12} />}
                        {uploading ? 'Uploading...' : 'Upload PDF'}
                        <input
                            type="file"
                            accept=".pdf,.docx,.txt"
                            style={{ display: 'none' }}
                            onChange={handleFileChange}
                            disabled={uploading}
                        />
                    </label>
                )}

                {ingestionStatus?.status === 'processing' && (
                    <div className="badge badge-draft" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Loader2 size={12} className="spin" /> Parsing...
                    </div>
                )}
                
                {ingestionStatus?.status === 'completed' && tender.status === 'draft' && (
                    <button
                        className="btn btn-primary btn-sm"
                        style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem', gap: '0.25rem' }}
                        onClick={() => onActivate(tender.id)}
                    >
                        <Check size={12} />
                        Activate Tender
                    </button>
                )}"""
                
text = text.replace(old_tender_card_args, new_tender_card_args)
text = text.replace(old_upload_button, new_upload_button)

# 3. Add handleActivate in Dashboard
old_handle_submit = "    const handleSubmitTender = async (id: number) => {"
new_handle_activate = """    const handleActivateTender = async (id: number) => {
        try {
            setLoading(true);
            await tenderApi.activate(id);
            await loadTenders();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to activate tender');
        } finally {
            setLoading(false);
        }
    };

    const handleSubmitTender = async (id: number) => {"""

text = text.replace(old_handle_submit, new_handle_activate)

# 4. Update TenderCard call site in Dashboard
old_tender_card_map = """                                    colTenders.map((tender, i) => (
                                        <TenderCard key={tender.id} tender={tender} index={i} onUpload={handleUpload} onCreateProposal={setShowNewProposal} onEditProposal={handleEditProposal} onSubmit={handleSubmitTender} onOpenChat={handleOpenChat} onWarmChat={handleWarmChat} onOpenFullChat={handleOpenFullChat} />
                                    ))"""

new_tender_card_map = """                                    colTenders.map((tender, i) => (
                                        <TenderCard key={tender.id} tender={tender} index={i} ingestionStatus={ingestionStatuses[tender.id]} onActivate={handleActivateTender} onUpload={handleUpload} onCreateProposal={setShowNewProposal} onEditProposal={handleEditProposal} onSubmit={handleSubmitTender} onOpenChat={handleOpenChat} onWarmChat={handleWarmChat} onOpenFullChat={handleOpenFullChat} />
                                    ))"""

text = text.replace(old_tender_card_map, new_tender_card_map)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)

print("Dashboard rewrite script completed.")
