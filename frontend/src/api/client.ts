/**
 * TenderWriter — API Client
 * Centralized HTTP client for backend communication.
 */

const API_BASE = '/api';

interface RequestOptions {
    method?: string;
    body?: unknown;
    headers?: Record<string, string>;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { method = 'GET', body, headers = {} } = options;

    const token = localStorage.getItem('token');

    const config: RequestInit = {
        method,
        headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
            ...headers,
        },
    };

    if (body) {
        config.body = JSON.stringify(body);
    }

    const response = await fetch(`${API_BASE}${path}`, config);

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }

    if (response.status === 204) {
        return {} as T;
    }

    return response.json();
}

// ── Auth ──

export const authApi = {
    login: (data: Record<string, string>) => request<AuthResponse>('/auth/login', { method: 'POST', body: data }),
    register: (data: Record<string, string>) => request<any>('/auth/register', { method: 'POST', body: data }),
    verifyOtp: (data: Record<string, string>) => request<AuthResponse>('/auth/verify-otp', { method: 'POST', body: data }),
    me: () => request<User>('/auth/me'),
    updateProfile: (data: { name?: string; email?: string }) =>
        request<User>('/auth/profile', { method: 'PUT', body: data }),
};

// ── Tenders ──

export const tenderApi = {
    list: (params?: Record<string, string>) => {
        const query = params ? '?' + new URLSearchParams(params).toString() : '';
        return request<{ items: Tender[]; total: number }>(`/tenders${query}`);
    },
    get: (id: number) => request<TenderDetail>(`/tenders/${id}`),
    create: (data: TenderCreate) => request<Tender>('/tenders', { method: 'POST', body: data }),
    update: (id: number, data: TenderUpdate) =>
        request<Tender>(`/tenders/${id}`, { method: 'PUT', body: data }),
    delete: (id: number) => request(`/tenders/${id}`, { method: 'DELETE' }),
    uploadDocument: async (id: number, file: File) => {
        const formData = new FormData();
        formData.append('file', file);
        const token = localStorage.getItem('token');
        const response = await fetch(`${API_BASE}/tenders/${id}/import`, {
            method: 'POST',
            body: formData,
            headers: token ? { 'Authorization': `Bearer ${token}` } : {},
            // non settiamo il Content-Type qui, fetch lo fa in automatico con il boundary per multipart/form-data
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Upload error' }));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        return response.json();
    },
};

// ── Chat ──

export const chatApi = {
    getRoom: (tenderId: number) => request<ChatRoom>(`/tenders/${tenderId}/chat/room`),
    listMessages: (tenderId: number, params?: { before_id?: number; limit?: number }) => {
        const query = params
            ? '?' + new URLSearchParams(
                Object.entries(params)
                    .filter(([, value]) => value !== undefined && value !== null)
                    .reduce((acc, [key, value]) => ({ ...acc, [key]: String(value) }), {} as Record<string, string>)
            ).toString()
            : '';
        return request<ChatMessageList>(`/tenders/${tenderId}/chat/messages${query}`);
    },
    getRetrospective: (tenderId: number, params?: { timeline_limit?: number }) => {
        const query = params
            ? '?' + new URLSearchParams(
                Object.entries(params)
                    .filter(([, value]) => value !== undefined && value !== null)
                    .reduce((acc, [key, value]) => ({ ...acc, [key]: String(value) }), {} as Record<string, string>)
            ).toString()
            : '';
        return request<ChatRetrospective>(`/tenders/${tenderId}/chat/retrospective${query}`);
    },
    sendMessage: (tenderId: number, data: { text: string }) =>
        request<ChatMessage>(`/tenders/${tenderId}/chat/messages`, { method: 'POST', body: data }),
    uploadAttachment: (
        tenderId: number,
        params: { file: File; text?: string; onProgress?: (percent: number) => void }
    ) => {
        return new Promise<ChatMessage>((resolve, reject) => {
            const formData = new FormData();
            formData.append('file', params.file);
            if (params.text && params.text.trim()) {
                formData.append('text', params.text.trim());
            }

            const token = localStorage.getItem('token');
            const xhr = new XMLHttpRequest();
            xhr.open('POST', `${API_BASE}/tenders/${tenderId}/chat/attachments`);

            if (token) {
                xhr.setRequestHeader('Authorization', `Bearer ${token}`);
            }

            xhr.upload.onprogress = (event) => {
                if (!params.onProgress || !event.lengthComputable) return;
                const percent = Math.round((event.loaded / event.total) * 100);
                params.onProgress(percent);
            };

            xhr.onerror = () => reject(new Error('Attachment upload failed'));

            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        resolve(JSON.parse(xhr.responseText) as ChatMessage);
                    } catch {
                        reject(new Error('Invalid attachment upload response'));
                    }
                    return;
                }

                try {
                    const err = JSON.parse(xhr.responseText);
                    reject(new Error(err.detail || `HTTP ${xhr.status}`));
                } catch {
                    reject(new Error(`HTTP ${xhr.status}`));
                }
            };

            xhr.send(formData);
        });
    },
    downloadAttachment: async (tenderId: number, attachment: ChatAttachment) => {
        const token = localStorage.getItem('token');
        const response = await fetch(`${API_BASE}/tenders/${tenderId}/chat/attachments/${attachment.id}/download`, {
            method: 'GET',
            headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Download error' }));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = attachment.filename || `attachment-${attachment.id}`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
    },
    exportRetrospective: async (tenderId: number) => {
        const token = localStorage.getItem('token');
        const response = await fetch(`${API_BASE}/tenders/${tenderId}/chat/retrospective/export`, {
            method: 'GET',
            headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Export error' }));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }

        const disposition = response.headers.get('content-disposition') || '';
        let filename = `tender-${tenderId}-chat-retrospective.json`;
        const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
        if (utf8Match && utf8Match[1]) {
            try {
                filename = decodeURIComponent(utf8Match[1]);
            } catch {
                filename = utf8Match[1];
            }
        } else {
            const plainMatch = disposition.match(/filename="?([^";]+)"?/i);
            if (plainMatch && plainMatch[1]) {
                filename = plainMatch[1];
            }
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
    },
};

// ── Proposals ──

export const proposalApi = {
    list: (params?: Record<string, string>) => {
        const query = params ? '?' + new URLSearchParams(params).toString() : '';
        return request<{ items: Proposal[]; total: number }>(`/proposals${query}`);
    },
    get: (id: number) => request<ProposalDetail>(`/proposals/${id}`),
    create: (data: ProposalCreate) =>
        request<Proposal>('/proposals', { method: 'POST', body: data }),
    update: (id: number, data: Partial<ProposalCreate>) =>
        request<Proposal>(`/proposals/${id}`, { method: 'PUT', body: data }),
    updateSection: (proposalId: number, sectionId: number, data: Partial<Section>) =>
        request<Section>(`/proposals/${proposalId}/sections/${sectionId}`, {
            method: 'PUT',
            body: data,
        }),
};

// ── Content Library ──

export const contentApi = {
    list: (params?: Record<string, string>) => {
        const query = params ? '?' + new URLSearchParams(params).toString() : '';
        return request<{ items: ContentBlock[]; total: number }>(`/content-blocks${query}`);
    },
    get: (id: number) => request<ContentBlock>(`/content-blocks/${id}`),
    create: (data: ContentBlockCreate) =>
        request<ContentBlock>('/content-blocks', { method: 'POST', body: data }),
    update: (id: number, data: Partial<ContentBlockCreate>) =>
        request<ContentBlock>(`/content-blocks/${id}`, { method: 'PUT', body: data }),
    delete: (id: number) => request(`/content-blocks/${id}`, { method: 'DELETE' }),
};

// ── RAG ──

export const ragApi = {
    query: (data: RAGQueryRequest) =>
        request<RAGResponse>('/rag/query', { method: 'POST', body: data }),
    getHistory: () => request<{ id: number, query: string, response: string, created_at: string }[]>('/rag/history'),
    generateSection: (data: GenerateSectionRequest) =>
        request<RAGResponse>('/rag/generate-section', { method: 'POST', body: data }),
    complianceCheck: (data: ComplianceCheckRequest) =>
        request<ComplianceResponse>('/rag/compliance-check', { method: 'POST', body: data }),
    analyzeRequirements: (text: string) =>
        request<RequirementsResponse>('/rag/analyze-requirements', {
            method: 'POST',
            body: { document_text: text },
        }),
    health: () => request<Record<string, unknown>>('/rag/health'),
};

// ── System ──

export const systemApi = {
    getContainers: () => request<any[]>('/system/containers'),
    getLogs: (containerName: string, tail?: number) => request<{ logs: string }>(`/system/logs/${containerName}${tail ? `?tail=${tail}` : ''}`),
    getStats: (containerName: string) => request<any>(`/system/stats/${containerName}`),
    updateNginx: (data: { read_timeout: number, connect_timeout: number, send_timeout: number }) => request<any>('/system/nginx-timeout', { method: 'POST', body: data }),
    getAppSettings: () => request<AppSettingsData>('/system/app-settings'),
    updateAppSettings: (data: Partial<AppSettingsData>) => request<AppSettingsData>('/system/app-settings', { method: 'PUT', body: data }),
};

export interface AppSettingsData {
    rag_model?: string;
    nginx_read_timeout?: number;
    nginx_connect_timeout?: number;
    nginx_send_timeout?: number;
    admin_enabled?: boolean;
}

// ── Admin ──

export const adminApi = {
    listUsers: () => request<AdminUser[]>('/admin/users'),
    getAllTenderPermissions: () => request<TenderPermissionOverview[]>('/admin/tenders/permissions'),
    getTenderPermissions: (tenderId: number) =>
        request<TenderPermissionEntry[]>(`/admin/tenders/${tenderId}/permissions`),
    grantPermission: (tenderId: number, data: { user_id: number; permission: string }) =>
        request<TenderPermissionEntry>(`/admin/tenders/${tenderId}/permissions`, { method: 'POST', body: data }),
    revokePermission: (tenderId: number, userId: number) =>
        request(`/admin/tenders/${tenderId}/permissions/${userId}`, { method: 'DELETE' }),
};

export const kpiAdminApi = {
    getPortfolioOverview: () => request<KpiPortfolioOverview>('/admin/kpi/portfolio/overview'),
    getPortfolioBottlenecks: () => request<KpiPortfolioBottlenecks>('/admin/kpi/portfolio/bottlenecks'),
    getTenderSnapshot: (tenderId: number) => request<KpiTenderSnapshot>(`/admin/kpi/tenders/${tenderId}/snapshot`),
    getTenderDiagnostics: (tenderId: number) => request<KpiDiagnostics>(`/admin/kpi/tenders/${tenderId}/diagnostics`),
    getTenderForecast: (tenderId: number) => request<KpiForecast>(`/admin/kpi/tenders/${tenderId}/forecast`),
};

// ── Gateway Admin ──

export interface GatewayTarget {
    id: number;
    route_key: string;
    target_kind: string;
    provider: string;
    base_url: string;
    model_name?: string | null;
    enabled: boolean;
    priority: number;
    timeout_ms: number;
    use_anonymizer: boolean;
    metadata_json?: Record<string, unknown>;
}

export const gatewayApi = {
    listTargets: () => request<GatewayTarget[]>('/gateway/targets'),
    createTarget: (data: Omit<GatewayTarget, 'id'>) =>
        request<GatewayTarget>('/gateway/targets', { method: 'POST', body: data }),
    updateTarget: (id: number, data: Partial<Omit<GatewayTarget, 'id'>>) =>
        request<GatewayTarget>(`/gateway/targets/${id}`, { method: 'PUT', body: data }),
    deleteTarget: (id: number) => request(`/gateway/targets/${id}`, { method: 'DELETE' }),
};

// ── Types ──

export interface User {
    id: number;
    email: string;
    name: string;
    role: string;
}

export interface AuthResponse {
    access_token: string;
    token_type: string;
    user: User;
}

export interface Tender {
    id: number;
    title: string;
    client: string | null;
    description: string | null;
    deadline: string | null;
    status: string;
    category: string | null;
    tags: string[];
    budget_estimate: number | null;
    proposal_id?: number | null;
    created_at: string;
    created_by: number | null;
    created_by_name: string | null;
    requirement_count?: number;
}

export interface TenderDetail extends Tender {
    requirements: Requirement[];
}

export interface Requirement {
    id: number;
    requirement_text: string;
    category: string | null;
    priority: string;
    compliance_status: string;
}

export interface TenderCreate {
    title: string;
    client?: string;
    description?: string;
    deadline?: string;
    category?: string;
    tags?: string[];
    budget_estimate?: number;
}

export interface TenderUpdate {
    title?: string;
    client?: string;
    description?: string;
    deadline?: string;
    status?: string;
    category?: string;
    tags?: string[];
    budget_estimate?: number;
}

export interface Proposal {
    id: number;
    tender_id: number;
    title: string;
    status: string;
    version: number;
    notes: string | null;
    created_at: string;
    section_count?: number;
}

export interface ProposalDetail extends Proposal {
    sections: Section[];
}

export interface Section {
    id: number;
    title: string;
    content: Record<string, unknown>;
    order: number;
    status: string;
    assigned_to: number | null;
}

export interface ProposalCreate {
    tender_id: number;
    title: string;
    notes?: string;
}

export interface ContentBlock {
    id: number;
    title: string;
    content: string;
    category: string | null;
    tags: string[];
    usage_count: number;
    quality_rating: number;
    created_at: string;
}

export interface ContentBlockCreate {
    title: string;
    content: string;
    category?: string;
    tags?: string[];
}

export interface RAGQueryRequest {
    query: string;
    mode?: string;
    filters?: Record<string, unknown>;
    top_k?: number;
    temperature?: number;
}

export interface GenerateSectionRequest {
    query: string;
    section_title: string;
    instructions?: string;
    requirements?: string;
}

export interface ComplianceCheckRequest {
    requirement: string;
    section_content: string;
}

export interface RAGResponse {
    answer: string;
    sources: { text: string; score: number; metadata: Record<string, unknown> }[];
    mode: string;
}

export interface ComplianceResponse {
    assessment: {
        status: string;
        explanation: string;
        gaps: string[];
        suggestions: string[];
    };
    sources: unknown[];
}

export interface RequirementsResponse {
    requirements: { text: string; category: string; priority: string }[];
    count: number;
}

export interface AdminUser {
    id: number;
    email: string;
    name: string;
    role: string;
    is_active: boolean;
    is_verified: boolean;
    created_at: string | null;
}

export interface TenderPermissionEntry {
    id: number;
    tender_id: number;
    user_id: number;
    user_name: string;
    user_email: string;
    permission: string;
    granted_by: number | null;
    created_at: string | null;
}

export interface TenderPermissionOverview {
    tender_id: number;
    tender_title: string;
    owner_id: number | null;
    owner_name: string | null;
    permissions: TenderPermissionEntry[];
}

export interface KpiScore {
    kpi_code: string;
    value: number | null;
    label: string | null;
    health: string;
    provenance: string;
    confidence: number | null;
    evidence: string[];
}

export interface KpiTenderSnapshot {
    status: string;
    external_tender_id: string;
    analytical_phase: string | null;
    health: string;
    generated_at: string | null;
    kpis: KpiScore[];
    notes: string[];
}

export interface KpiDiagnostics {
    status: string;
    external_tender_id: string;
    generated_at: string | null;
    summary: string;
    findings: string[];
}

export interface KpiForecastScenario {
    name: string;
    probability: number | null;
    description: string | null;
}

export interface KpiForecast {
    status: string;
    external_tender_id: string;
    generated_at: string | null;
    scenarios: KpiForecastScenario[];
}

export interface KpiPortfolioOverview {
    status: string;
    generated_at: string | null;
    portfolio_health: string;
    total_tenders: number;
    tenders_by_health: Record<string, number>;
}

export interface KpiBottleneckItem {
    external_tender_id: string;
    bottleneck_type: string;
    summary: string;
    health: string;
}

export interface KpiPortfolioBottlenecks {
    status: string;
    generated_at: string | null;
    items: KpiBottleneckItem[];
}

export interface ChatRoom {
    id: number;
    tender_id: number;
    is_official: boolean;
    status: string;
    opened_at: string | null;
    created_at: string | null;
    participant_count: number;
}

export interface ChatAttachment {
    id: number;
    message_id: number;
    filename: string;
    mime_type: string | null;
    size_bytes: number | null;
    created_at: string | null;
}

export interface ChatMessage {
    id: number;
    chat_room_id: number;
    sender_id: number | null;
    sender_name: string | null;
    message_type: string;
    text: string;
    attachments: ChatAttachment[];
    created_at: string | null;
}

export interface ChatMessageList {
    items: ChatMessage[];
    next_before_id: number | null;
}

export interface ChatParticipant {
    user_id: number;
    user_name: string | null;
    user_email: string | null;
    role: string;
    source: string;
    is_active: boolean;
    joined_at: string | null;
    left_at: string | null;
}

export interface ChatRetrospectiveTimelineItem {
    kind: string;
    created_at: string | null;
    message: ChatMessage | null;
    event_id: number | null;
    event_type: string | null;
    actor_id: number | null;
    actor_name: string | null;
    payload: Record<string, unknown> | null;
}

export interface ChatRetrospective {
    room: ChatRoom;
    participants: ChatParticipant[];
    message_count: number;
    attachment_count: number;
    event_count: number;
    first_message_at: string | null;
    last_message_at: string | null;
    generated_at: string;
    timeline: ChatRetrospectiveTimelineItem[];
}
// LLM Settings
export const llmSettingsApi = {
    get: () => request<{ id?: number | null; max_tokens?: number | null; temperature?: number | null; stop_tokens?: string | null; }>("/gateway/llm-settings"),
    update: (data: { max_tokens?: number | null; temperature?: number | null; stop_tokens?: string | null; }) => request('/gateway/llm-settings', { method: 'PUT', body: data }),
};





