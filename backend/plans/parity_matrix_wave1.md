# Parity Matrix Wave 1 (Expanded)

This matrix maps key TenderClaw files to their source components for Wave 1 expansion.

| Area | Source | Target |
|---|---|---|
| Runtime Kernel | Claw Code | backend/runtime/conversation_runtime.py |
| Runtime Kernel | Claw Code | backend/runtime/prompt_builder.py |
| Runtime Kernel | Claw Code | backend/runtime/usage_tracker.py |
| Runtime Kernel | Claw Code | backend/runtime/context_compactor.py |
| Runtime Kernel | Claw Code | backend/runtime/permissions_policy.py |
| Hook Engine | Hook Engine Core | backend/hooks/engine.py |
| Hook Dispatcher | Hook Dispatcher | backend/hooks/dispatcher.py |
| Skills Loader | Claw Code | backend/core/skills.py |
| Skills Loader | Claw Code | backend/skills/discovery.py |
| Orchestration | Claw Code | backend/orchestration/pipeline.py |
| Orchestration | Claw Code | backend/orchestration/intent_gate.py |
| Planning/Execution | Claw Code | backend/orchestration/pipeline.py |
| API Gate / HUD | Claw Code | backend/api/gateway.py |
| OAuth/Provider | Claw Code | backend/runtime/oauth.py |
| Provider Client | Claw Code | backend/runtime/provider_client.py |
| Tools/Registry | Claw Code | backend/tools/registry.py |
