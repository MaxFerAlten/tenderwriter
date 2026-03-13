import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
    ArrowLeft,
    Download,
    MessageSquare,
    Paperclip,
    RefreshCw,
    RotateCcw,
    Send,
    Users,
    Wifi,
    WifiOff,
} from 'lucide-react';
import {
    chatApi,
    tenderApi,
    type ChatAttachment,
    type ChatMessage,
    type ChatRoom,
    type Tender,
} from '../api/client';
import { useAuth } from '../contexts/AuthContext';

const POLL_INTERVAL_MS = 10000;
const WS_HEARTBEAT_MS = 20000;

function formatMessageTime(value: string | null): string {
    if (!value) return '-';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '-';
    return date.toLocaleString();
}

function formatBytes(value: number | null | undefined): string {
    if (!value || value <= 0) return '-';
    if (value < 1024) return `${value} B`;
    const kb = value / 1024;
    if (kb < 1024) return `${kb.toFixed(1)} KB`;
    const mb = kb / 1024;
    return `${mb.toFixed(1)} MB`;
}

function upsertMessage(list: ChatMessage[], incoming: ChatMessage): ChatMessage[] {
    const idx = list.findIndex((item) => item.id === incoming.id);
    if (idx === -1) {
        return [...list, incoming].sort((a, b) => a.id - b.id);
    }
    const clone = [...list];
    clone[idx] = incoming;
    return clone.sort((a, b) => a.id - b.id);
}

function buildWsUrl(tenderId: number, token: string): string {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    return `${protocol}://${window.location.host}/api/tenders/${tenderId}/chat/ws?token=${encodeURIComponent(token)}`;
}

export default function TenderChat() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();

    const messagesEndRef = useRef<HTMLDivElement | null>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const fileInputRef = useRef<HTMLInputElement | null>(null);

    const tenderId = useMemo(() => Number(id), [id]);

    const [tender, setTender] = useState<Tender | null>(null);
    const [room, setRoom] = useState<ChatRoom | null>(null);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [draft, setDraft] = useState('');
    const [sending, setSending] = useState(false);
    const [sendError, setSendError] = useState<string | null>(null);

    const [uploadingAttachment, setUploadingAttachment] = useState(false);
    const [uploadProgress, setUploadProgress] = useState<number | null>(null);
    const [uploadError, setUploadError] = useState<string | null>(null);
    const [pendingAttachment, setPendingAttachment] = useState<{ file: File; caption: string } | null>(null);
    const [downloadingAttachmentId, setDownloadingAttachmentId] = useState<number | null>(null);

    const [wsConnected, setWsConnected] = useState(false);
    const [connectionError, setConnectionError] = useState<string | null>(null);
    const [infoMessage, setInfoMessage] = useState<string | null>(null);

    const totalAttachments = useMemo(
        () => messages.reduce((acc, msg) => acc + (msg.attachments?.length ?? 0), 0),
        [messages]
    );

    const fetchMessages = useCallback(async (silent = false) => {
        if (!Number.isFinite(tenderId) || tenderId <= 0) return;

        try {
            const data = await chatApi.listMessages(tenderId, { limit: 100 });
            setMessages(data.items || []);
        } catch (err) {
            if (!silent) {
                setError(err instanceof Error ? err.message : 'Failed to load chat messages');
            }
        }
    }, [tenderId]);

    const loadChatContext = useCallback(async () => {
        if (!Number.isFinite(tenderId) || tenderId <= 0) {
            setError('Invalid tender id');
            setLoading(false);
            return;
        }

        try {
            setLoading(true);
            setError(null);
            const [tenderData, roomData, messageData] = await Promise.all([
                tenderApi.get(tenderId),
                chatApi.getRoom(tenderId),
                chatApi.listMessages(tenderId, { limit: 100 }),
            ]);
            setTender(tenderData);
            setRoom(roomData);
            setMessages(messageData.items || []);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load chat');
        } finally {
            setLoading(false);
        }
    }, [tenderId]);

    useEffect(() => {
        loadChatContext();
    }, [loadChatContext]);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }, [messages]);

    useEffect(() => {
        if (!Number.isFinite(tenderId) || tenderId <= 0) return;

        const token = localStorage.getItem('token');
        if (!token) {
            setWsConnected(false);
            setConnectionError('Missing auth token for realtime');
            return;
        }

        let closedByCleanup = false;
        const ws = new WebSocket(buildWsUrl(tenderId, token));
        wsRef.current = ws;

        ws.onopen = () => {
            setWsConnected(true);
            setConnectionError(null);
        };

        ws.onmessage = (event) => {
            try {
                const payload = JSON.parse(event.data);
                if (payload?.type === 'message_created' && payload?.message) {
                    const incoming = payload.message as ChatMessage;
                    setMessages((prev) => upsertMessage(prev, incoming));
                }
            } catch {
                // Ignore malformed payloads to keep stream resilient.
            }
        };

        ws.onerror = () => {
            setWsConnected(false);
            setConnectionError('Realtime unavailable, fallback to polling active');
        };

        ws.onclose = () => {
            wsRef.current = null;
            setWsConnected(false);
            if (!closedByCleanup) {
                setConnectionError('Realtime disconnected, fallback to polling active');
            }
        };

        return () => {
            closedByCleanup = true;
            try {
                ws.close();
            } catch {
                // Ignore close errors during unmount.
            }
        };
    }, [tenderId]);

    useEffect(() => {
        if (!wsConnected) return;
        const interval = window.setInterval(() => {
            if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                wsRef.current.send(JSON.stringify({ type: 'ping' }));
            }
        }, WS_HEARTBEAT_MS);

        return () => window.clearInterval(interval);
    }, [wsConnected]);

    useEffect(() => {
        if (wsConnected) return;
        if (!Number.isFinite(tenderId) || tenderId <= 0) return;

        const interval = window.setInterval(() => {
            void fetchMessages(true);
        }, POLL_INTERVAL_MS);

        return () => window.clearInterval(interval);
    }, [fetchMessages, tenderId, wsConnected]);

    const handleSend = async () => {
        const text = draft.trim();
        if (!text || !Number.isFinite(tenderId) || tenderId <= 0) return;

        try {
            setSending(true);
            setSendError(null);
            setInfoMessage(null);
            const created = await chatApi.sendMessage(tenderId, { text });
            setMessages((prev) => upsertMessage(prev, created));
            setDraft('');
        } catch (err) {
            setSendError(err instanceof Error ? err.message : 'Failed to send message');
        } finally {
            setSending(false);
        }
    };

    const uploadAttachment = async (file: File, caption: string) => {
        if (!Number.isFinite(tenderId) || tenderId <= 0) return;

        try {
            setUploadingAttachment(true);
            setUploadProgress(0);
            setUploadError(null);
            setInfoMessage(null);

            const created = await chatApi.uploadAttachment(tenderId, {
                file,
                text: caption,
                onProgress: (percent) => setUploadProgress(percent),
            });

            setMessages((prev) => upsertMessage(prev, created));
            if (caption) {
                setDraft('');
            }
            setPendingAttachment(null);
        } catch (err) {
            setUploadError(err instanceof Error ? err.message : 'Failed to upload attachment');
            setPendingAttachment({ file, caption });
        } finally {
            setUploadingAttachment(false);
            setUploadProgress(null);
        }
    };

    const onComposerKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            void handleSend();
        }
    };

    const handleAttachClick = () => {
        fileInputRef.current?.click();
    };

    const handleAttachmentSelected = (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        event.target.value = '';
        if (!file) return;

        const caption = draft.trim();
        void uploadAttachment(file, caption);
    };

    const handleRetryAttachment = () => {
        if (!pendingAttachment) return;
        void uploadAttachment(pendingAttachment.file, pendingAttachment.caption);
    };

    const handleDownloadAttachment = async (attachment: ChatAttachment) => {
        if (!Number.isFinite(tenderId) || tenderId <= 0) return;

        try {
            setDownloadingAttachmentId(attachment.id);
            await chatApi.downloadAttachment(tenderId, attachment);
        } catch (err) {
            setInfoMessage(err instanceof Error ? err.message : 'Failed to download attachment');
        } finally {
            setDownloadingAttachmentId(null);
        }
    };

    if (loading) {
        return (
            <div className="loading-spinner" style={{ padding: '3rem 0' }}>
                <div className="spinner" />
                <p style={{ color: 'var(--text-muted)', marginTop: '0.75rem' }}>Loading chat...</p>
            </div>
        );
    }

    return (
        <div className="animate-in">
            <div className="page-header" style={{ marginBottom: '1rem' }}>
                <div>
                    <button className="btn btn-ghost btn-sm" onClick={() => navigate('/')} style={{ marginBottom: '0.5rem' }}>
                        <ArrowLeft size={14} />
                        Back to dashboard
                    </button>
                    <h1 className="page-title" style={{ marginBottom: '0.25rem' }}>Tender Chat</h1>
                    <p className="page-subtitle" style={{ margin: 0 }}>
                        {tender?.title || `Tender #${tenderId}`}
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <span className="badge" style={{ background: wsConnected ? '#065f46' : '#7f1d1d', color: '#fff' }}>
                        {wsConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
                        {wsConnected ? 'Realtime ON' : 'Polling mode'}
                    </span>
                </div>
            </div>

            {error && (
                <div className="card" style={{ borderColor: '#ef4444', marginBottom: '1rem', color: '#ef4444' }}>
                    {error}
                </div>
            )}

            {connectionError && (
                <div className="card" style={{ borderColor: '#f59e0b', marginBottom: '1rem', color: '#f59e0b' }}>
                    {connectionError}
                </div>
            )}

            {uploadingAttachment && (
                <div className="card" style={{ borderColor: '#3b82f6', marginBottom: '1rem', color: '#93c5fd' }}>
                    Uploading attachment{uploadProgress !== null ? ` (${uploadProgress}%)` : ''}...
                </div>
            )}

            {uploadError && (
                <div className="card" style={{ borderColor: '#ef4444', marginBottom: '1rem', color: '#ef4444', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem' }}>
                    <span>{uploadError}</span>
                    {pendingAttachment && (
                        <button className="btn btn-ghost btn-sm" onClick={handleRetryAttachment}>
                            <RotateCcw size={12} />
                            Retry Upload
                        </button>
                    )}
                </div>
            )}

            {infoMessage && (
                <div className="card" style={{ borderColor: '#3b82f6', marginBottom: '1rem', color: '#93c5fd' }}>
                    {infoMessage}
                </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 280px', gap: '1rem' }}>
                <div className="card" style={{ display: 'flex', flexDirection: 'column', minHeight: '70vh', padding: 0, overflow: 'hidden' }}>
                    <div style={{ borderBottom: '1px solid var(--border-default)', padding: '0.9rem 1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <MessageSquare size={16} />
                            <strong>Official Chat Room</strong>
                        </div>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                            <span className="badge">
                                <Users size={12} />
                                {room?.participant_count ?? 0}
                            </span>
                            <button className="btn btn-ghost btn-sm" onClick={() => void fetchMessages(false)}>
                                <RefreshCw size={12} />
                                Refresh
                            </button>
                        </div>
                    </div>

                    <div style={{ flex: 1, overflowY: 'auto', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                        {messages.length === 0 ? (
                            <div className="empty-state" style={{ marginTop: '2rem' }}>
                                <MessageSquare size={32} />
                                <h3>No messages yet</h3>
                                <p>Start the official tender discussion here.</p>
                            </div>
                        ) : (
                            messages.map((msg) => {
                                const isMine = Boolean(msg.sender_id && user?.id && msg.sender_id === user.id);
                                return (
                                    <div
                                        key={msg.id}
                                        style={{
                                            alignSelf: isMine ? 'flex-end' : 'flex-start',
                                            maxWidth: '80%',
                                            padding: '0.65rem 0.8rem',
                                            borderRadius: '10px',
                                            background: isMine ? 'rgba(59,130,246,0.25)' : 'rgba(255,255,255,0.06)',
                                            border: '1px solid var(--border-default)',
                                        }}
                                    >
                                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.35rem' }}>
                                            {msg.sender_name || 'System'} · {formatMessageTime(msg.created_at)}
                                        </div>

                                        {msg.text && msg.text.trim().length > 0 && (
                                            <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.45 }}>{msg.text}</div>
                                        )}

                                        {(msg.attachments?.length ?? 0) > 0 && (
                                            <div style={{ marginTop: msg.text?.trim() ? '0.6rem' : 0, display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
                                                {msg.attachments.map((attachment) => (
                                                    <div
                                                        key={attachment.id}
                                                        style={{
                                                            display: 'flex',
                                                            alignItems: 'center',
                                                            justifyContent: 'space-between',
                                                            gap: '0.5rem',
                                                            padding: '0.45rem 0.55rem',
                                                            borderRadius: '8px',
                                                            border: '1px solid var(--border-default)',
                                                            background: 'rgba(0,0,0,0.12)',
                                                        }}
                                                    >
                                                        <div style={{ minWidth: 0 }}>
                                                            <div style={{ fontSize: '0.83rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                                {attachment.filename}
                                                            </div>
                                                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                                                {formatBytes(attachment.size_bytes)}
                                                            </div>
                                                        </div>
                                                        <button
                                                            className="btn btn-ghost btn-sm"
                                                            style={{ padding: '0.2rem 0.5rem' }}
                                                            disabled={downloadingAttachmentId === attachment.id}
                                                            onClick={() => void handleDownloadAttachment(attachment)}
                                                        >
                                                            <Download size={12} />
                                                            {downloadingAttachmentId === attachment.id ? 'Downloading...' : 'Download'}
                                                        </button>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                );
                            })
                        )}
                        <div ref={messagesEndRef} />
                    </div>

                    <div style={{ borderTop: '1px solid var(--border-default)', padding: '0.9rem 1rem' }}>
                        {sendError && (
                            <div style={{ color: '#ef4444', marginBottom: '0.6rem', fontSize: '0.9rem' }}>{sendError}</div>
                        )}
                        <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'flex-end' }}>
                            <textarea
                                className="form-textarea"
                                rows={3}
                                placeholder="Write a message... (Enter to send, Shift+Enter for new line)"
                                value={draft}
                                onChange={(e) => setDraft(e.target.value)}
                                onKeyDown={onComposerKeyDown}
                                style={{ resize: 'none', margin: 0, flex: 1 }}
                            />
                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    onChange={handleAttachmentSelected}
                                    style={{ display: 'none' }}
                                />
                                <button
                                    className="btn btn-ghost"
                                    onClick={handleAttachClick}
                                    title="Attach file"
                                    disabled={uploadingAttachment}
                                >
                                    <Paperclip size={16} />
                                </button>
                                <button className="btn btn-primary" onClick={() => void handleSend()} disabled={sending || !draft.trim()}>
                                    <Send size={16} />
                                    {sending ? 'Sending...' : 'Send'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="card" style={{ height: 'fit-content' }}>
                    <h3 style={{ marginTop: 0, marginBottom: '0.5rem' }}>Chat Details</h3>
                    <p style={{ color: 'var(--text-muted)', marginTop: 0 }}>
                        Room status: <strong>{room?.status || 'unknown'}</strong>
                    </p>
                    <p style={{ color: 'var(--text-muted)' }}>
                        Opened at: <strong>{formatMessageTime(room?.opened_at || null)}</strong>
                    </p>
                    <hr style={{ borderColor: 'var(--border-default)', margin: '0.8rem 0' }} />
                    <h4 style={{ marginBottom: '0.35rem' }}>Attachments</h4>
                    <p style={{ color: 'var(--text-muted)', marginTop: 0 }}>
                        Total files shared: <strong>{totalAttachments}</strong>
                    </p>
                    {pendingAttachment && (
                        <p style={{ color: 'var(--text-muted)', marginTop: 0 }}>
                            Pending retry: <strong>{pendingAttachment.file.name}</strong>
                        </p>
                    )}
                </div>
            </div>
        </div>
    );
}
