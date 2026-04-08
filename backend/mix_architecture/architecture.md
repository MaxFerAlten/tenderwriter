# Mix Architecture TenderClaw

La miglior architettura per TenderClaw è descritta come 6 piani:
- Experience plane: UI web + CLI + Channel gateway
- Control plane: intent gate, planner, conductor, review gates
- Execution plane: worker agents, tool loop, parallel/team mode
- Skill plane: skill loader, skill MCP manager, workflow engine
- State plane: sessioni, piani, team state, resumability, telemetry
- Integration plane: MCP, hooks, notifications, OAuth/provider clients

Questa separazione nasce dall’esigenza di dazionare chiaramente responsabilità, scalare orizzontalmente e isolare runtime dalle superfici di controllo.

Fonti principali di ispirazione: Claw Code (runtime e sessione), oh-my-codex (HUD, team/state), oh-my-openagent (planning/orchestration/hook system), Superpowers (workflow enforcement).

Nota: questo documento è una guida di alto livello e non sostituisce i piani file-per-file descritti in Finalizzazione Tender Claw.

**Link utili**
- File di riferimento: TenderClaw mix architecture (testo): 6 piani
- Diagrammi: diagrammi Mermaid in repository (se disponibili)
