# Domain Glossary

This document freezes the Sprint 1 vocabulary for `tw-kpi-reason-engine`.

## Core Domain Entities

### Tender
Primary analytical aggregate tracked by the KPI engine. A tender is identified across services by `external_tender_id`.

### ContributionUnit
Logical deliverable requested from an owner as part of a tender. A contribution unit can map to one or more proposal sections, documents, or review artifacts.

### Department
Organizational owner responsible for one or more contribution units.

### ContributionRequest
Formal request sent to a department or owner with due date, SLA expectations, and scope.

### ContributionSubmission
Delivered response to a contribution request. It can contain text, documents, or references to generated proposal material.

### ReviewCycle
Explicit review iteration applied to a contribution or proposal segment.

### ReviewFinding
Structured finding raised during review, including quality gaps, missing evidence, or compliance issues.

### ReworkAction
Follow-up action raised after review when a contribution needs revision or clarification.

### ComplianceGate
Formal gate that validates whether the tender is compliant before moving forward.

### CallSession
Coordination meeting related to the tender lifecycle.

### AttendanceRecord
Presence or absence record associated with a call session.

### TenderOutcome
Explicit business outcome of a tender, for example `won`, `lost`, `no_bid`, or `excluded`.

## KPI Families

### A1
Requirement coverage score. Measures how much of the tender requirement space is mapped to the proposal or contribution plan.

### A2
Contribution completeness score. Measures whether the expected contributions have been requested, received, and connected to the working proposal.

### A3
Evidence depth score. Measures how well requirements and claims are backed by references, proofs, or usable source material.

### A4
Compliance alignment score. Measures the expected conformity of the current tender package against mandatory conditions and internal gates.

### B1
SLA responsiveness score. Measures whether contribution requests receive answers within target time and maximum time boundaries.

### B2
Rework pressure score. Measures how much the tender is slowed down by repeated rework loops and unresolved findings.

### B3
Gate stability score. Measures how consistently compliance gates are passed without blocking regressions.

### B4
Coordination reliability score. Measures operational reliability across calls, attendance, and execution cadence.

### Q
Composite quality index produced from the analytical KPI family, with explainability metadata.

### E
Composite execution index produced from the operational KPI family, with explainability metadata.

## Health Classes

### green
The tender is progressing within expected quality and execution boundaries.

### amber
The tender is viable but shows material signals of slippage, missing inputs, or emerging compliance risk.

### red
The tender is materially at risk, blocked, or likely to miss quality or operational thresholds.

### unknown
The engine does not have enough measured information yet.

## Analytical States

### S0 - Intake Created
The tender exists in the system but no analytical evidence has been processed yet.

### S1 - Documents Available
Tender documents or source material have been ingested.

### S2 - Requirements Structured
Requirements have been extracted or mapped into structured context.

### S3 - Proposal Initialized
A proposal structure exists and analytical tracking can begin.

### S4 - Contributions Requested
Contribution units have been opened and sent to owners.

### S5 - Contributions In Progress
Responses are arriving and the tender is actively collecting operational inputs.

### S6 - Rework Active
One or more contribution units are under rework or clarification loops.

### S7 - Compliance Gate Open
The tender is undergoing a formal compliance or review gate.

### S8 - Compliance Blocked
The tender is blocked by findings, missing evidence, or failed gates.

### S9 - Final Assembly
The tender is being consolidated for final submission packaging.

### S10 - Submission Ready
The tender is operationally ready to be submitted.

### S11 - Submitted
Submission has been explicitly recorded.

### S12 - Won
The tender has a successful outcome.

### S13 - Closed Unsuccessful
The tender closed without success, including lost, no-bid, or excluded outcomes.

## Sprint 1 Notes

- Sprint 1 freezes names and meanings only.
- The analytical state does not replace the existing application workflow in Sprint 1.
- Final outcome variants remain explicit business events under `TenderOutcome`.
