import { useState, useCallback, useEffect } from 'react';
import { hooksApi } from '../../api/client';

export interface HookEvent {
  value: string;
  label: string;
  description: string | null;
}

export interface HookConfig {
  timeout_ms: number;
  retry_count: number;
  retry_delay_ms: number;
  allow_parallel: boolean;
  permission_behavior: string;
  system_message_injection: string | null;
  enabled: boolean;
}

export interface HookInfo {
  id: string;
  name: string;
  event_type: string;
  description: string | null;
  config: HookConfig;
  registered_at: number | null;
  call_count: number;
  last_called: number | null;
  last_error: string | null;
}

export interface HookStatus {
  hooks: HookInfo[];
  events: HookEvent[];
  loading: boolean;
  error: string | null;
}

export function useHooksStore() {
  const [status, setStatus] = useState<HookStatus>({
    hooks: [],
    events: [],
    loading: false,
    error: null,
  });

  const fetchHooks = useCallback(async () => {
    setStatus(prev => ({ ...prev, loading: true, error: null }));
    try {
      const response = await hooksApi.list<HookInfo>();
      setStatus(prev => ({
        ...prev,
        hooks: response || [],
        loading: false,
      }));
    } catch (error) {
      setStatus(prev => ({
        ...prev,
        loading: false,
        error: error instanceof Error ? error.message : 'Failed to fetch hooks',
      }));
    }
  }, []);

  const fetchEvents = useCallback(async () => {
    try {
      const response = await hooksApi.listEvents<HookEvent>();
      setStatus(prev => ({
        ...prev,
        events: response.events || [],
      }));
    } catch (error) {
      console.error('Failed to fetch hook events:', error);
    }
  }, []);

  const registerHook = useCallback(async (hook: {
    name: string;
    event_type: string;
    description?: string;
    config?: HookConfig;
    handler_type?: 'async' | 'sync';
    code: string;
  }) => {
    setStatus(prev => ({ ...prev, loading: true, error: null }));
    try {
      await hooksApi.register(hook);
      await fetchHooks();
      return true;
    } catch (error) {
      setStatus(prev => ({
        ...prev,
        loading: false,
        error: error instanceof Error ? error.message : 'Failed to register hook',
      }));
      return false;
    }
  }, [fetchHooks]);

  const unregisterHook = useCallback(async (hookId: string) => {
    setStatus(prev => ({ ...prev, loading: true, error: null }));
    try {
      await hooksApi.unregister(hookId);
      await fetchHooks();
      return true;
    } catch (error) {
      setStatus(prev => ({
        ...prev,
        loading: false,
        error: error instanceof Error ? error.message : 'Failed to unregister hook',
      }));
      return false;
    }
  }, [fetchHooks]);

  const testHook = useCallback(async (
    hookId: string,
    eventType: string,
    testData?: Record<string, unknown>
  ) => {
    try {
      return await hooksApi.test(hookId, eventType, testData);
    } catch (error) {
      console.error('Failed to test hook:', error);
      return null;
    }
  }, []);

  useEffect(() => {
    fetchHooks();
    fetchEvents();
  }, [fetchHooks, fetchEvents]);

  return {
    ...status,
    fetchHooks,
    fetchEvents,
    registerHook,
    unregisterHook,
    testHook,
  };
}

export function useHookStatus() {
  const { hooks, loading, error } = useHooksStore();

  const activeHooks = hooks.filter(h => h.config.enabled);
  const disabledHooks = hooks.filter(h => !h.config.enabled);

  return {
    totalHooks: hooks.length,
    activeHooks: activeHooks.length,
    disabledHooks: disabledHooks.length,
    hooks,
    loading,
    error,
    recentErrors: hooks.filter(h => h.last_error).map(h => ({
      hookId: h.id,
      hookName: h.name,
      error: h.last_error,
      lastCalled: h.last_called,
    })),
  };
}
