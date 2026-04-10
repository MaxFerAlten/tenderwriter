import sys

file_path = r'D:\tender\tenderwriter\frontend\src\api\client.test.ts'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

# Fix 1
old_test_1 = """    it('preserves the tender import response contract for successful uploads without warnings', async () => {
        const file = new File(['demo'], 'rfp.pdf', { type: 'application/pdf' });
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({
                message: 'Document uploaded and ingested successfully',
                tender_id: 12,
                filename: 'rfp.pdf',
                stats: {
                    status: 'completed',
                    requirements_detected: 2,
                    requirement_extraction_method: 'heuristic_v1',
                    warnings: [],
                },
            }), {
                status: 202,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await tenderApi.uploadDocument(12, file);

        expect(response.tender_id).toBe(12);
        expect(response.stats.requirement_extraction_method).toBe('heuristic_v1');
        expect(response.stats.warnings).toEqual([]);
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/tenders/12/import',
            expect.objectContaining({
                method: 'POST',
                body: expect.any(FormData),
            })
        );
    });"""

new_test_1 = """    it('preserves the async tender import response contract returning 202 Accepted', async () => {
        const file = new File(['demo'], 'rfp.pdf', { type: 'application/pdf' });
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({
                message: 'Document uploaded and ingestion queued successfully',
                tender_id: 12,
                document_id: 99,
                task_id: 'task-abc',
                filename: 'rfp.pdf',
                status: 'queued',
            }), {
                status: 202,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await tenderApi.uploadDocument(12, file);

        expect(response.tender_id).toBe(12);
        expect(response.document_id).toBe(99);
        expect(response.status).toBe('queued');
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/tenders/12/import',
            expect.objectContaining({
                method: 'POST',
                body: expect.any(FormData),
            })
        );
    });"""

text = text.replace(old_test_1, new_test_1)

# Fix 2: the fallback warnings test
old_test_2_start = """    it('returns LLM fallback warnings from the tender import response for frontend modals', async () => {"""
old_test_2_end = """        expect(response.stats.warnings[0].fallback_method).toBe('heuristic_v1');
    });"""

import re
text = re.sub(
    r"    it\('returns LLM fallback warnings from the tender import response for frontend modals', async \(\) => \{.*?\n    \}\);", 
    "", 
    text, 
    flags=re.DOTALL
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)

print("Updated client.test.ts")
