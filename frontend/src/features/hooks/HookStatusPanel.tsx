import React from 'react';
import { useHookStatus } from './useHooksStore';

export const HookStatusPanel: React.FC = () => {
  const {
    totalHooks,
    activeHooks,
    disabledHooks,
    hooks,
    loading,
    recentErrors,
  } = useHookStatus();

  if (loading) {
    return (
      <div className="hook-status-panel">
        <div className="hook-status-loading">Loading hooks...</div>
      </div>
    );
  }

  return (
    <div className="hook-status-panel">
      <div className="hook-status-header">
        <h3>Hook System Status</h3>
      </div>

      <div className="hook-status-summary">
        <div className="hook-stat">
          <span className="hook-stat-value">{totalHooks}</span>
          <span className="hook-stat-label">Total Hooks</span>
        </div>
        <div className="hook-stat hook-stat-active">
          <span className="hook-stat-value">{activeHooks}</span>
          <span className="hook-stat-label">Active</span>
        </div>
        <div className="hook-stat hook-stat-disabled">
          <span className="hook-stat-value">{disabledHooks}</span>
          <span className="hook-stat-label">Disabled</span>
        </div>
      </div>

      {recentErrors.length > 0 && (
        <div className="hook-errors">
          <h4>Recent Errors</h4>
          <ul>
            {recentErrors.map((err) => (
              <li key={err.hookId} className="hook-error-item">
                <strong>{err.hookName}</strong>: {err.error}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="hook-list">
        <h4>Registered Hooks</h4>
        {hooks.length === 0 ? (
          <p className="hook-empty">No hooks registered</p>
        ) : (
          <ul>
            {hooks.map((hook) => (
              <li key={hook.id} className="hook-item">
                <div className="hook-item-header">
                  <span className="hook-name">{hook.name}</span>
                  <span className={`hook-badge ${hook.config.enabled ? 'active' : 'disabled'}`}>
                    {hook.config.enabled ? 'Active' : 'Disabled'}
                  </span>
                </div>
                <div className="hook-item-details">
                  <span className="hook-event-type">{hook.event_type}</span>
                  <span className="hook-call-count">
                    Called {hook.call_count} times
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

export default HookStatusPanel;
