export const HEALTH_COLOR: Record<string, string> = {
    green: '#10b981',
    amber: '#f59e0b',
    red: '#ef4444',
};

export function StatusBadge({ label, color }: { label: string; color: string }) {
    return (
        <span
            style={{
                padding: '0.2rem 0.6rem',
                borderRadius: '999px',
                fontSize: '0.75rem',
                background: `${color}22`,
                color,
                border: `1px solid ${color}66`,
                textTransform: 'uppercase',
                letterSpacing: 0.4,
            }}
        >
            {label}
        </span>
    );
}
