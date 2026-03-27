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
    recordDecision: (id: number, data: TenderDecisionRequest) =>
        request<TenderLifecycleActionResponse>(`/tenders/${id}/decision`, { method: 'POST', body: data }),
    recordBidPlan: (id: number, data: TenderBidPlanRequest) =>
        request<TenderLifecycleActionResponse>(`/tenders/${id}/bid-plan`, { method: 'POST', body: data }),
    openContributionWave: (id: number, data: ContributionWaveRequest) =>
        request<TenderLifecycleActionResponse>(`/tenders/${id}/contribution-wave`, { method: 'POST', body: data }),
    recordOutcome: (id: number, data: TenderOutcomeRecordRequest) =>
        request<TenderLifecycleActionResponse>(`/tenders/${id}/outcome`, { method: 'POST', body: data }),
    createClarification: (id: number, data: TenderClarificationCreateRequest) =>
        request<TenderLifecycleActionResponse>(`/tenders/${id}/clarifications`, { method: 'POST', body: data }),
    draftClarification: (id: number, clarificationId: string, data: TenderClarificationUpdateRequest) =>
        request<TenderLifecycleActionResponse>(`/tenders/${id}/clarifications/${clarificationId}/draft`, { method: 'POST', body: data }),
    submitClarification: (id: number, clarificationId: string, data: TenderClarificationUpdateRequest) =>
        request<TenderLifecycleActionResponse>(`/tenders/${id}/clarifications/${clarificationId}/submit`, { method: 'POST', body: data }),
    closeClarification: (id: number, clarificationId: string, data: TenderClarificationUpdateRequest) =>
        request<TenderLifecycleActionResponse>(`/tenders/${id}/clarifications/${clarificationId}/close`, { method: 'POST', body: data }),
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


const CHAT_PREFETCH_TTL_MS = 45_000;
const CHAT_PREFETCH_MAX_ENTRIES = 24;

type TenderChatContextCacheEntry = {
    value: TenderChatContextSnapshot | null;
    promise: Promise<TenderChatContextSnapshot> | null;
    cached_at: number;
};

type TenderChatRetrospectiveCacheEntry = {
    value: ChatRetrospective | null;
    promise: Promise<ChatRetrospective> | null;
    cached_at: number;
};

const tenderChatContextCache = new Map<number, TenderChatContextCacheEntry>();
const tenderChatRetrospectiveCache = new Map<number, TenderChatRetrospectiveCacheEntry>();

function pruneTenderChatContextCache(): void {
    const now = Date.now();
    for (const [key, entry] of tenderChatContextCache.entries()) {
        if (!entry.promise && now - entry.cached_at > CHAT_PREFETCH_TTL_MS) {
            tenderChatContextCache.delete(key);
        }
    }
    while (tenderChatContextCache.size > CHAT_PREFETCH_MAX_ENTRIES) {
        const oldestKey = tenderChatContextCache.keys().next().value;
        if (oldestKey === undefined) {
            break;
        }
        tenderChatContextCache.delete(oldestKey);
    }
}

function pruneTenderChatRetrospectiveCache(): void {
    const now = Date.now();
    for (const [key, entry] of tenderChatRetrospectiveCache.entries()) {
        if (!entry.promise && now - entry.cached_at > CHAT_PREFETCH_TTL_MS) {
            tenderChatRetrospectiveCache.delete(key);
        }
    }
    while (tenderChatRetrospectiveCache.size > CHAT_PREFETCH_MAX_ENTRIES) {
        const oldestKey = tenderChatRetrospectiveCache.keys().next().value;
        if (oldestKey === undefined) {
            break;
        }
        tenderChatRetrospectiveCache.delete(oldestKey);
    }
}

function isTenderChatContextFresh(entry: TenderChatContextCacheEntry | undefined): boolean {
    return Boolean(entry && Date.now() - entry.cached_at <= CHAT_PREFETCH_TTL_MS);
}

function isTenderChatRetrospectiveFresh(entry: TenderChatRetrospectiveCacheEntry | undefined): boolean {
    return Boolean(entry && Date.now() - entry.cached_at <= CHAT_PREFETCH_TTL_MS);
}

async function fetchTenderChatContext(tenderId: number): Promise<TenderChatContextSnapshot> {
    const [tender, room, messageData] = await Promise.all([
        tenderApi.get(tenderId),
        chatApi.getRoom(tenderId),
        chatApi.listMessages(tenderId, { limit: 100 }),
    ]);

    return {
        tender,
        room,
        messages: messageData.items || [],
        prefetched_at: Date.now(),
    };
}

async function fetchTenderChatRetrospective(tenderId: number): Promise<ChatRetrospective> {
    return chatApi.getRetrospective(tenderId, { timeline_limit: 200 });
}

export async function resolveTenderChatContext(tenderId: number, options: { preferCached?: boolean } = {}): Promise<TenderChatContextSnapshot> {
    if (!Number.isFinite(tenderId) || tenderId <= 0) {
        throw new Error('Invalid tender id');
    }

    const preferCached = options.preferCached ?? true;
    const existing = tenderChatContextCache.get(tenderId);
    if (existing?.promise) {
        return existing.promise;
    }
    if (preferCached && isTenderChatContextFresh(existing)) {
        if (existing?.value) {
            return existing.value;
        }
    }

    const promise = fetchTenderChatContext(tenderId)
        .then((value) => {
            tenderChatContextCache.set(tenderId, {
                value,
                promise: null,
                cached_at: Date.now(),
            });
            pruneTenderChatContextCache();
            return value;
        })
        .catch((error) => {
            const cached = tenderChatContextCache.get(tenderId);
            if (cached?.promise === promise) {
                tenderChatContextCache.delete(tenderId);
            }
            throw error;
        });

    tenderChatContextCache.set(tenderId, {
        value: null,
        promise,
        cached_at: Date.now(),
    });
    pruneTenderChatContextCache();

    return promise;
}

export async function resolveTenderChatRetrospective(tenderId: number, options: { preferCached?: boolean } = {}): Promise<ChatRetrospective> {
    if (!Number.isFinite(tenderId) || tenderId <= 0) {
        throw new Error('Invalid tender id');
    }

    const preferCached = options.preferCached ?? true;
    const existing = tenderChatRetrospectiveCache.get(tenderId);
    if (existing?.promise) {
        return existing.promise;
    }
    if (preferCached && isTenderChatRetrospectiveFresh(existing)) {
        if (existing?.value) {
            return existing.value;
        }
    }

    const promise = fetchTenderChatRetrospective(tenderId)
        .then((value) => {
            tenderChatRetrospectiveCache.set(tenderId, {
                value,
                promise: null,
                cached_at: Date.now(),
            });
            pruneTenderChatRetrospectiveCache();
            return value;
        })
        .catch((error) => {
            const cached = tenderChatRetrospectiveCache.get(tenderId);
            if (cached?.promise === promise) {
                tenderChatRetrospectiveCache.delete(tenderId);
            }
            throw error;
        });

    tenderChatRetrospectiveCache.set(tenderId, {
        value: null,
        promise,
        cached_at: Date.now(),
    });
    pruneTenderChatRetrospectiveCache();

    return promise;
}

export async function prefetchTenderChatContext(tenderId: number): Promise<void> {
    await resolveTenderChatContext(tenderId, { preferCached: true });
}

export async function prefetchTenderChatRetrospective(tenderId: number): Promise<void> {
    await resolveTenderChatRetrospective(tenderId, { preferCached: true });
}

export function consumePrefetchedTenderChatContext(tenderId: number): TenderChatContextSnapshot | null {
    const existing = tenderChatContextCache.get(tenderId);
    if (!isTenderChatContextFresh(existing) || !existing?.value) {
        return null;
    }

    tenderChatContextCache.delete(tenderId);
    return existing.value;
}

export function consumePrefetchedTenderChatRetrospective(tenderId: number): ChatRetrospective | null {
    const existing = tenderChatRetrospectiveCache.get(tenderId);
    if (!isTenderChatRetrospectiveFresh(existing) || !existing?.value) {
        return null;
    }

    tenderChatRetrospectiveCache.delete(tenderId);
    return existing.value;
}

export function resetTenderChatContextCacheForTest(): void {
    tenderChatContextCache.clear();
    tenderChatRetrospectiveCache.clear();
}

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
    markDraftReady: (proposalId: number, data: ProposalDraftReadyRequest = {}) =>
        request<ProposalLifecycleActionResponse>(`/proposals/${proposalId}/draft-ready`, { method: 'POST', body: data }),
    updateSubmissionStatus: (proposalId: number, data: ProposalSubmissionStatusRequest) =>
        request<ProposalLifecycleActionResponse>(`/proposals/${proposalId}/submission-status`, { method: 'POST', body: data }),
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
    getCapabilities: () => request<SystemCapabilitiesData>('/system/capabilities'),
    getContainers: () => request<SystemContainer[]>('/system/containers'),
    getLogs: (containerName: string, tail?: number) => request<{ logs: string }>(`/system/logs/${containerName}${tail ? `?tail=${tail}` : ''}`),
    getStats: (containerName: string) => request<SystemContainerStats>(`/system/stats/${containerName}`),
    updateNginx: (data: { read_timeout: number, connect_timeout: number, send_timeout: number }) => request<any>('/system/nginx-timeout', { method: 'POST', body: data }),
    getAppSettings: () => request<AppSettingsData>('/system/app-settings'),
    updateAppSettings: (data: Partial<AppSettingsData>) => request<AppSettingsData>('/system/app-settings', { method: 'PUT', body: data }),
};

export interface SystemCapabilityStatus {
    available: boolean;
    reason: string | null;
}

export interface SystemCapabilitiesData {
    ops_agent: SystemCapabilityStatus;
    ops_monitoring: SystemCapabilityStatus;
    nginx_hot_reload: SystemCapabilityStatus;
}

export interface SystemContainer {
    id: string;
    name: string;
    status: string;
    health: string;
}

export interface SystemContainerStats {
    cpu_percent: number;
    memory_usage_mb: number;
    memory_limit_mb: number;
    memory_percent: number;
}

export interface AppSettingsData {
    rag_model?: string;
    nginx_read_timeout?: number;
    nginx_connect_timeout?: number;
    nginx_send_timeout?: number;
    admin_enabled?: boolean;
    anonymizer_enabled?: boolean;
}

export interface AnonymizerConfigData {
    entities: string[];
    ttl_seconds: number;
    strategy: 'redaction' | 'faking';
    min_confidence: number;
    mask_cig: boolean;
}

export interface AnonymizerStatsData {
    requests: number;
    sessions: number;
    entities_detected: number;
    deanonymize_requests: number;
    faking_requests?: number;
    fallback_events?: number;
    runtime_failure_count?: number;
    circuit_open?: boolean;
    circuit_open_events?: number;
    last_error_reason?: string | null;
}

export interface AnonymizerPolicyRuleData {
    mode?: 'internal_only' | 'external_anonymized';
    anonymizer_enabled?: boolean;
}

export interface AnonymizerPolicyData {
    default: AnonymizerPolicyRuleData;
    routes: Record<string, AnonymizerPolicyRuleData>;
    tenders: Record<string, AnonymizerPolicyRuleData>;
}

export interface EffectiveAnonymizerPolicyData {
    route_key: string;
    tender_id?: number | null;
    mode: 'internal_only' | 'external_anonymized';
    anonymizer_enabled: boolean;
    target_id?: number | null;
    target_kind?: string | null;
    target_provider?: string | null;
    target_base_url?: string | null;
    target_model?: string | null;
    target_timeout_ms?: number | null;
    target_use_anonymizer?: boolean | null;
    sources: string[];
}

export interface AnonymizerAuditEntryData {
    id: number;
    action: string;
    user_email: string;
    user_role: string;
    tender_id?: number | null;
    route_key?: string | null;
    llm_route?: string | null;
    anonymized?: boolean | null;
    target_id?: number | null;
    target_provider?: string | null;
    target_base_url?: string | null;
    session_token?: string | null;
    success: boolean;
    error_message?: string | null;
    payload_json?: Record<string, unknown> | null;
    created_at: string;
}

export interface AnonymizerChunkResult {
    text: string;
    anonymized_text: string;
    detections: Array<Record<string, unknown>>;
    replacements: Record<string, string>;
}

export interface AnonymizerTestResult {
    session_id: string;
    config: AnonymizerConfigData;
    chunk?: AnonymizerChunkResult;
    chunks?: AnonymizerChunkResult[];
    mapping?: Record<string, string>;
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
    getPortfolioIntelligence: () => request<KpiPortfolioIntelligence>('/admin/kpi/portfolio/intelligence'),
    resyncPortfolio: () => request<KpiPortfolioResyncResult>('/admin/kpi/portfolio/resync', { method: 'POST' }),
    getTenderSnapshot: (tenderId: number) => request<KpiTenderSnapshot>(`/admin/kpi/tenders/${tenderId}/snapshot`),
    getTenderDiagnostics: (tenderId: number) => request<KpiDiagnostics>(`/admin/kpi/tenders/${tenderId}/diagnostics`),
    getTenderTransitions: (tenderId: number) => request<KpiTransitions>(`/admin/kpi/tenders/${tenderId}/transitions`),
    getTenderForecast: (tenderId: number) => request<KpiForecast>(`/admin/kpi/tenders/${tenderId}/forecast`),
    recomputeTender: (tenderId: number) => request<KpiAnalysisJob>(`/admin/kpi/tenders/${tenderId}/recompute`, { method: 'POST' }),
    backfillTenderHistory: (tenderId: number) => request<KpiAnalysisJob>(`/admin/kpi/tenders/${tenderId}/history/backfill`, { method: 'POST' }),
    getLatestAnalysisJob: (tenderId: number) => request<KpiAnalysisJob>(`/admin/kpi/tenders/${tenderId}/analysis-jobs/latest`),
};

export const observabilityApi = {
    getWorkspace: (tenderId: number) => request<OperationalWorkspace>(`/tenders/${tenderId}/observability/workspace`),
    createContribution: (tenderId: number, data: ContributionUnitCreateRequest) =>
        request<ContributionUnitRecord>(`/tenders/${tenderId}/observability/contributions`, { method: 'POST', body: data }),
    createRequest: (tenderId: number, contributionId: number, data: ContributionRequestCreateRequest) =>
        request<ContributionRequestRecord>(`/tenders/${tenderId}/observability/contributions/${contributionId}/requests`, { method: 'POST', body: data }),
    receiveRequest: (tenderId: number, contributionId: number, requestId: number, data: ContributionRequestReceiveRequest) =>
        request<ContributionRequestRecord>(`/tenders/${tenderId}/observability/contributions/${contributionId}/requests/${requestId}/receive`, { method: 'POST', body: data }),
    createReview: (tenderId: number, contributionId: number, data: ReviewCycleCreateRequest) =>
        request<ReviewCycleRecord>(`/tenders/${tenderId}/observability/contributions/${contributionId}/reviews`, { method: 'POST', body: data }),
    completeReview: (tenderId: number, contributionId: number, reviewId: number, data: ReviewCycleCompleteRequest) =>
        request<ReviewCycleRecord>(`/tenders/${tenderId}/observability/contributions/${contributionId}/reviews/${reviewId}/complete`, { method: 'POST', body: data }),
    createRework: (tenderId: number, contributionId: number, data: ReworkCreateRequest) =>
        request<ReworkRecord>(`/tenders/${tenderId}/observability/contributions/${contributionId}/rework`, { method: 'POST', body: data }),
    resolveRework: (tenderId: number, contributionId: number, reworkId: number, data: ReworkResolveRequest) =>
        request<ReworkRecord>(`/tenders/${tenderId}/observability/contributions/${contributionId}/rework/${reworkId}/resolve`, { method: 'POST', body: data }),
    createGate: (tenderId: number, data: ComplianceGateCreateRequest) =>
        request<ComplianceGateRecord>(`/tenders/${tenderId}/observability/gates`, { method: 'POST', body: data }),
    decideGate: (tenderId: number, gateId: number, data: ComplianceGateDecisionRequest) =>
        request<ComplianceGateRecord>(`/tenders/${tenderId}/observability/gates/${gateId}/decision`, { method: 'POST', body: data }),
    createCall: (tenderId: number, data: CallSessionCreateRequest) =>
        request<CallSessionRecord>(`/tenders/${tenderId}/observability/calls`, { method: 'POST', body: data }),
    upsertAttendance: (tenderId: number, callId: number, data: AttendanceRecordUpsertRequest) =>
        request<AttendanceRecordItem>(`/tenders/${tenderId}/observability/calls/${callId}/attendance`, { method: 'POST', body: data }),
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

export const anonymizerApi = {
    getConfig: () => request<AnonymizerConfigData>('/anonymizer/config'),
    updateConfig: (data: Partial<AnonymizerConfigData>) =>
        request<AnonymizerConfigData>('/anonymizer/config', { method: 'POST', body: data }),
    getStats: () => request<AnonymizerStatsData>('/anonymizer/stats'),
    getPolicy: () => request<AnonymizerPolicyData>('/anonymizer/policy'),
    updatePolicy: (data: AnonymizerPolicyData) =>
        request<AnonymizerPolicyData>('/anonymizer/policy', { method: 'PUT', body: data }),
    getEffectivePolicy: (params?: { route_key?: string; tender_id?: number }) => {
        const query = params
            ? '?' + new URLSearchParams(
                Object.entries(params)
                    .filter(([, value]) => value !== undefined && value !== null)
                    .reduce((acc, [key, value]) => ({ ...acc, [key]: String(value) }), {} as Record<string, string>)
            ).toString()
            : '';
        return request<EffectiveAnonymizerPolicyData>(`/anonymizer/policy/effective${query}`);
    },
    getAudit: (params?: { limit?: number }) => {
        const query = params
            ? '?' + new URLSearchParams(
                Object.entries(params)
                    .filter(([, value]) => value !== undefined && value !== null)
                    .reduce((acc, [key, value]) => ({ ...acc, [key]: String(value) }), {} as Record<string, string>)
            ).toString()
            : '';
        return request<AnonymizerAuditEntryData[]>(`/anonymizer/audit${query}`);
    },
    test: (data: { text: string; session_id?: string; config?: Partial<AnonymizerConfigData> }) =>
        request<AnonymizerTestResult>('/anonymizer/test', { method: 'POST', body: data }),
    deanonymize: (data: { text: string; session_id: string }) =>
        request<{ session_id: string; text: string; mapping_size: number }>('/anonymizer/deanonymize', {
            method: 'POST',
            body: data,
        }),
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

export interface TenderLifecycleDecisionRecord {
    decision: string;
    decided_at: string | null;
    reason_code: string | null;
    notes: string | null;
    actor_id: number | null;
}

export interface TenderLifecycleBidPlanRecord {
    plan_status: string;
    planned_at: string | null;
    owner_user_ids: number[];
    milestone_count: number | null;
    notes: string | null;
    actor_id: number | null;
}

export interface TenderLifecycleContributionWaveRecord {
    opened_at: string | null;
    contribution_count: number | null;
    department_count: number | null;
    notes: string | null;
    actor_id: number | null;
}

export interface TenderLifecycleDraftReadyRecord {
    proposal_id: number | null;
    ready_at: string | null;
    approved_section_count: number | null;
    total_section_count: number | null;
    actor_id: number | null;
}

export interface TenderLifecycleSubmissionStatusRecord {
    proposal_id: number | null;
    submission_status: string;
    occurred_at: string | null;
    channel: string | null;
    reference_id: string | null;
    error_code: string | null;
    error_message: string | null;
    actor_id: number | null;
}

export interface TenderLifecycleOutcomeRecord {
    outcome: string;
    recorded_at: string | null;
    reason_code: string | null;
    notes: string | null;
    actor_id: number | null;
}

export interface TenderLifecycleClarificationRecord {
    request_id: string;
    status: string;
    request_summary: string | null;
    deadline_at: string | null;
    source_label: string | null;
    response_summary: string | null;
    requested_at: string | null;
    submitted_at: string | null;
    closed_at: string | null;
    updated_at: string | null;
    actor_id: number | null;
}

export interface TenderLifecycleMetadata {
    decision?: TenderLifecycleDecisionRecord | null;
    bid_plan?: TenderLifecycleBidPlanRecord | null;
    contribution_wave?: TenderLifecycleContributionWaveRecord | null;
    draft_ready?: TenderLifecycleDraftReadyRecord | null;
    submission_status?: TenderLifecycleSubmissionStatusRecord | null;
    structured_outcome?: TenderLifecycleOutcomeRecord | null;
    clarifications?: TenderLifecycleClarificationRecord[];
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
    lifecycle_metadata?: TenderLifecycleMetadata | null;
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
    mapped_section_id: number | null;
    mapped_section_title: string | null;
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

export interface TenderDecisionRequest {
    decision: string;
    decided_at?: string;
    reason_code?: string;
    notes?: string;
}

export interface TenderBidPlanRequest {
    plan_status?: string;
    planned_at?: string;
    owner_user_ids?: number[];
    milestone_count?: number;
    notes?: string;
}

export interface ContributionWaveRequest {
    opened_at?: string;
    contribution_count?: number;
    department_count?: number;
    notes?: string;
}

export interface TenderOutcomeRecordRequest {
    outcome: string;
    recorded_at?: string;
    reason_code?: string;
    notes?: string;
}

export interface TenderClarificationCreateRequest {
    request_id?: string;
    request_summary: string;
    deadline_at?: string;
    source_label?: string;
    occurred_at?: string;
}

export interface TenderClarificationUpdateRequest {
    response_summary?: string;
    occurred_at?: string;
    source_label?: string;
}

export interface TenderLifecycleActionResponse {
    status: string;
    event_type: string;
    tender_id: number;
    payload: Record<string, unknown>;
}

export interface ProposalDraftReadyRequest {
    ready_at?: string;
}

export interface ProposalSubmissionStatusRequest {
    submission_status: string;
    occurred_at?: string;
    channel?: string;
    reference_id?: string;
    error_code?: string;
    error_message?: string;
}

export interface ProposalLifecycleActionResponse {
    status: string;
    event_type: string;
    proposal_id: number;
    payload: Record<string, unknown>;
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

export interface KpiAnalysisMetadata {
    formula_bundle_version: string | null;
    model_bundle_version: string | null;
    prompt_bundle_version: string | null;
    contract_version: string | null;
    health_rule_version: string | null;
    score_scale_internal: string | null;
    score_scale_external: string | null;
    markov_phase_scope: string[];
    markov_reliable_phase_scope: string[];
    semantic_priority: string[];
    canonical_source_types: string[];
    rollout_policy: string | null;
    qualitative_engine_kind: string | null;
    qualitative_engine_mode: string | null;
    semantic_official_enabled: boolean;
    semantic_engine_kind: string | null;
    semantic_execution_mode: string | null;
    semantic_bundle_version: string | null;
    semantic_kpis: string[];
    semantic_fallback_kpis: string[];
    semantic_fallback_policy_version: string | null;
    shadow_rollout_enabled: boolean;
    markov_rollout_enabled: boolean;
    calibrated_forecast_enabled: boolean;
    shadow_mode_enabled: boolean;
    shadow_engine_kind: string | null;
    shadow_execution_mode: string | null;
    shadow_bundle_version: string | null;
    shadow_kpis: string[];
    forecast_engine_active: string | null;
    forecast_engine_candidates: string[];
    forecast_signal_type: string | null;
    forecast_fallback_reason: string | null;
    heuristic_bundle_version: string | null;
    markov_model_active: boolean;
    markov_model_version: string | null;
    markov_state_scope: string[];
    markov_absorbing_states: string[];
    markov_transition_samples: number | null;
    markov_dataset_tenders: number | null;
    markov_current_state_support: number | null;
    markov_source_mix: Record<string, number>;
    markov_bundle_kind: string | null;
    markov_full_journey_enabled: boolean;
    markov_coverage_ratio: number | null;
    markov_projected_path: string[];
    markov_backtest_version: string | null;
    markov_backtest_sample_count: number | null;
    markov_backtest_submission_accuracy: number | null;
    markov_backtest_calibration_gap: number | null;
    forecast_driver_kpis: string[];
    forecast_driver_scores: Record<string, number>;
    forecast_primary_action_code: string | null;
    forecast_primary_action_confidence: number | null;
    forecast_decision_bundle_version: string | null;
    engine_kind: string | null;
    scored_kpis: string[];
    event_count: number | null;
    requirements_tracked: number | null;
    sections_tracked: number | null;
    reconstructed: boolean;
    replay_until: string | null;
    replay_source_event_type: string | null;
    source_job_type: string | null;
    history_points: number | null;
}

export interface KpiSemanticCoverageGap {
    external_requirement_id: string;
    reference: string | null;
    summary: string | null;
    priority: string | null;
    status: string;
    mapped_section_id: string | null;
}

export interface KpiSemanticRiskItem {
    code: string;
    severity: string;
    summary: string;
    related_requirement_id: string | null;
    evidence: string | null;
}

export interface KpiSemanticDimensionItem {
    code: string;
    severity: string;
    summary: string;
    evidence: string | null;
}

export interface KpiSemanticEvaluation {
    enabled: boolean;
    status: string;
    engine_kind: string | null;
    execution_mode: string | null;
    semantic_score: number | null;
    proxy_score: number | null;
    delta_vs_proxy: number | null;
    health: string;
    confidence: number | null;
    source_type: string;
    evidences: string[];
    criticalities: string[];
    recommendations: string[];
    formula_version: string | null;
    model_version: string | null;
    prompt_version: string | null;
    fallback_reason: string | null;
    coverage_gaps: KpiSemanticCoverageGap[];
    risk_items: KpiSemanticRiskItem[];
    dimension_items: KpiSemanticDimensionItem[];
}

export interface KpiSemanticShadowEvaluation {
    enabled: boolean;
    status: string;
    engine_kind: string | null;
    execution_mode: string | null;
    shadow_score: number | null;
    proxy_score: number | null;
    delta_vs_proxy: number | null;
    health: string;
    confidence: number | null;
    source_type: string;
    evidences: string[];
    criticalities: string[];
    recommendations: string[];
    formula_version: string | null;
    model_version: string | null;
    prompt_version: string | null;
    coverage_gaps: KpiSemanticCoverageGap[];
    risk_items: KpiSemanticRiskItem[];
}

export interface KpiScore {
    kpi_code: string;
    score: number | null;
    value: number | null;
    label: string | null;
    health: string;
    severity: string;
    source_type: string;
    provenance: string;
    confidence: number | null;
    evidences: string[];
    evidence: string[];
    criticalities: string[];
    recommendations: string[];
    recommendation: string | null;
    formula_version: string | null;
    model_version: string | null;
    prompt_version: string | null;
    semantic: KpiSemanticEvaluation | null;
    shadow: KpiSemanticShadowEvaluation | null;
}

export interface KpiTenderSnapshot {
    status: string;
    external_tender_id: string;
    analytical_phase: string | null;
    health: string;
    generated_at: string | null;
    kpis: KpiScore[];
    notes: string[];
    analysis_metadata: KpiAnalysisMetadata;
}

export interface KpiDiagnostics {
    status: string;
    external_tender_id: string;
    generated_at: string | null;
    summary: string;
    findings: string[];
    analysis_metadata: KpiAnalysisMetadata;
}

export interface KpiTransitionItem {
    from_state: string;
    to_state: string;
    occurred_at: string | null;
    cause: string | null;
    confidence: number | null;
    source_event_type?: string | null;
    source_type: string;
    related_entity_id?: string | null;
}

export interface KpiRequirementTransitionItem {
    external_requirement_id: string;
    summary: string | null;
    priority: string | null;
    compliance_status: string | null;
    mapped_section_id: string | null;
    mapped_section_title: string | null;
    section_status: string | null;
    driver_phase: string | null;
    driver: string;
    last_event_type: string | null;
}

export interface KpiSnapshotHistoryItem {
    snapshot_id: number;
    generated_at: string | null;
    analytical_phase: string | null;
    health: string;
    summary: string | null;
    reconstructed: boolean;
    replay_until: string | null;
    source_type: string;
    source_job_type: string | null;
    replay_source_event_type: string | null;
}

export interface KpiTransitions {
    status: string;
    external_tender_id: string;
    generated_at: string | null;
    summary: string;
    items: KpiTransitionItem[];
    requirement_items: KpiRequirementTransitionItem[];
    history_items: KpiSnapshotHistoryItem[];
}

export interface KpiForecastScenario {
    name: string;
    probability: number | null;
    description: string | null;
    confidence: number | null;
    drivers: string[];
    recommended_action: string | null;
}

export interface KpiForecastDecisionAction {
    code: string;
    title: string;
    priority: 'now' | 'next' | 'watch';
    rationale: string;
    expected_impact: string | null;
    confidence: number | null;
    drivers: string[];
}

export interface KpiForecast {
    status: string;
    external_tender_id: string;
    generated_at: string | null;
    summary: string | null;
    overall_confidence: number | null;
    scenarios: KpiForecastScenario[];
    next_best_actions: KpiForecastDecisionAction[];
    analysis_metadata: KpiAnalysisMetadata;
}

export interface KpiAnalysisJob {
    external_tender_id: string;
    job_id: number | null;
    job_type: string | null;
    job_status: string;
    requested_by: string | null;
    priority: string | null;
    reason: string | null;
    created_at: string | null;
    started_at: string | null;
    completed_at: string | null;
    updated_at: string | null;
    latest_snapshot_generated_at: string | null;
    error_message: string | null;
}

export interface KpiPortfolioOverview {
    status: string;
    generated_at: string | null;
    portfolio_health: string;
    total_tenders: number;
    tenders_by_health: Record<string, number>;
    analytical_phases: Record<string, number>;
    critical_tenders: string[];
}

export interface KpiBottleneckItem {
    external_tender_id: string;
    bottleneck_type: string;
    summary: string;
    description?: string | null;
    health: string;
    severity?: string;
}

export interface KpiPortfolioBottlenecks {
    status: string;
    generated_at: string | null;
    items: KpiBottleneckItem[];
}

export interface KpiPortfolioPhaseHotspot {
    phase: string;
    count: number;
    summary: string;
}

export interface KpiPortfolioRiskHotspot {
    code: string;
    count: number;
    severity: string;
    summary: string;
}

export interface KpiPortfolioWatchlistItem {
    external_tender_id: string;
    title: string;
    analytical_phase: string | null;
    health: string;
    summary: string;
}

export interface KpiPortfolioIntelligence {
    status: string;
    generated_at: string | null;
    phase_hotspots: KpiPortfolioPhaseHotspot[];
    risk_hotspots: KpiPortfolioRiskHotspot[];
    outcome_trends: Record<string, number>;
    watchlist: KpiPortfolioWatchlistItem[];
    notes: string[];
}

export interface KpiPortfolioResyncItem {
    tender_id: number;
    delivered: boolean;
    upstream_status_code: number | null;
    error_message: string | null;
}

export interface KpiPortfolioResyncResult {
    status: string;
    generated_at: string | null;
    total_tenders: number;
    synced_tenders: number;
    failed_tenders: number;
    items: KpiPortfolioResyncItem[];
    notes: string[];
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

export interface TenderChatContextSnapshot {
    tender: TenderDetail;
    room: ChatRoom;
    messages: ChatMessage[];
    prefetched_at: number;
}
// LLM Settings
export const llmSettingsApi = {
    get: () => request<{ id?: number | null; max_tokens?: number | null; temperature?: number | null; stop_tokens?: string | null; }>("/gateway/llm-settings"),
    update: (data: { max_tokens?: number | null; temperature?: number | null; stop_tokens?: string | null; }) => request('/gateway/llm-settings', { method: 'PUT', body: data }),
};







export interface OperationalSummary {
    tender_id: number;
    contribution_count: number;
    request_count: number;
    open_rework_count: number;
    open_gate_count: number;
    call_count: number;
}

export interface ContributionUnitRecord {
    id: number;
    tender_id: number;
    title: string;
    description: string | null;
    department_name: string | null;
    owner_user_id: number | null;
    proposal_section_id: number | null;
    due_at: string | null;
    status: string;
}

export interface ContributionRequestRecord {
    id: number;
    contribution_unit_id: number;
    requested_to_user_id: number | null;
    requested_to_label: string | null;
    request_channel: string | null;
    requested_at: string | null;
    due_at: string | null;
    sla_target_hours: number | null;
    sla_max_hours: number | null;
    response_received_at: string | null;
    response_summary: string | null;
    status: string;
}

export interface ReviewCycleRecord {
    id: number;
    contribution_unit_id: number;
    reviewer_id: number | null;
    stage_name: string;
    started_at: string | null;
    completed_at: string | null;
    outcome: string | null;
    notes: string | null;
    status: string;
}

export interface ReworkRecord {
    id: number;
    contribution_unit_id: number;
    review_cycle_id: number | null;
    assigned_to_user_id: number | null;
    severity: string;
    is_blocking: boolean;
    reason: string | null;
    due_at: string | null;
    requested_at: string | null;
    resolved_at: string | null;
    resolution_notes: string | null;
    status: string;
}

export interface ComplianceGateRecord {
    id: number;
    tender_id: number;
    contribution_unit_id: number | null;
    owner_user_id: number | null;
    gate_name: string;
    due_at: string | null;
    evaluated_at: string | null;
    decision_notes: string | null;
    status: string;
}

export interface AttendanceRecordItem {
    id: number;
    call_session_id: number;
    user_id: number | null;
    attendee_label: string | null;
    attendance_status: string;
    recorded_at: string | null;
    notes: string | null;
}

export interface CallSessionRecord {
    id: number;
    tender_id: number;
    title: string;
    scheduled_at: string;
    started_at: string | null;
    ended_at: string | null;
    status: string;
    attendance?: AttendanceRecordItem[];
}

export interface OperationalWorkspace {
    summary: OperationalSummary;
    contributions: ContributionUnitRecord[];
    requests: ContributionRequestRecord[];
    reviews: ReviewCycleRecord[];
    reworks: ReworkRecord[];
    gates: ComplianceGateRecord[];
    calls: CallSessionRecord[];
}

export interface ContributionUnitCreateRequest {
    title: string;
    description?: string;
    department_name?: string;
    owner_user_id?: number;
    proposal_section_id?: number;
    due_at?: string;
}

export interface ContributionRequestCreateRequest {
    requested_to_user_id?: number;
    requested_to_label?: string;
    request_channel?: string;
    requested_at?: string;
    due_at?: string;
    sla_target_hours?: number;
    sla_max_hours?: number;
    response_summary?: string;
}

export interface ContributionRequestReceiveRequest {
    response_received_at?: string;
    response_summary?: string;
}

export interface ReviewCycleCreateRequest {
    reviewer_id?: number;
    stage_name?: string;
    started_at?: string;
    notes?: string;
}

export interface ReviewCycleCompleteRequest {
    completed_at?: string;
    outcome?: string;
    notes?: string;
}

export interface ReworkCreateRequest {
    review_cycle_id?: number;
    assigned_to_user_id?: number;
    severity?: string;
    is_blocking?: boolean;
    reason?: string;
    due_at?: string;
    requested_at?: string;
}

export interface ReworkResolveRequest {
    resolved_at?: string;
    resolution_notes?: string;
}

export interface ComplianceGateCreateRequest {
    gate_name: string;
    contribution_unit_id?: number;
    owner_user_id?: number;
    due_at?: string;
    decision_notes?: string;
}

export interface ComplianceGateDecisionRequest {
    status: string;
    evaluated_at?: string;
    decision_notes?: string;
}

export interface CallSessionCreateRequest {
    title: string;
    scheduled_at: string;
}

export interface AttendanceRecordUpsertRequest {
    user_id?: number;
    attendee_label?: string;
    attendance_status: string;
    recorded_at?: string;
    notes?: string;
}
