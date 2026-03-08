import re

def sanitize_name(name: str) -> str:
    """Sanitize a name for use in a file path."""
    if not name:
        return "unnamed"
    # Remove non-alphanumeric characters and replace spaces with underscores
    sanitized = re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')
    return sanitized or "unnamed"

def get_structured_minio_path(proposal_title: str, proposal_id: int, section_title: str = None, section_id: int = None, is_upload: bool = False, filename: str = None) -> str:
    """Generate a structured MinIO path for documents."""
    base_folder = f"{sanitize_name(proposal_title)}_{proposal_id}"
    if is_upload:
        folder = "uploaded"
        if filename:
            return f"{base_folder}/{folder}/{filename}"
        return f"{base_folder}/{folder}"
    
    if section_title and section_id:
        return f"{base_folder}/proposal_documents/{sanitize_name(section_title)}_{section_id}.docx"
    
    return f"{base_folder}/proposal_documents"

def get_tender_upload_path(tender_title: str, tender_id: int, filename: str) -> str:
    """Generate a structured MinIO path for tender uploads (when no proposal exists)."""
    return f"{sanitize_name(tender_title)}_{tender_id}/uploaded/{filename}"
