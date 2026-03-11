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
};

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

// LLM Settings
export const llmSettingsApi = {
    get: () => request<{ id?: number | null; max_tokens?: number | null; temperature?: number | null; stop_tokens?: string | null; }>("/gateway/llm-settings"),
    update: (data: { max_tokens?: number | null; temperature?: number | null; stop_tokens?: string | null; }) => request('/gateway/llm-settings', { method: 'PUT', body: data }),
};
