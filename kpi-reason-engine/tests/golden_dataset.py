from __future__ import annotations

GOLDEN_DATASET_CASES = [
    {
        'case_id': 'healthy_submission_path',
        'description': 'Tender with requirements addressed and active proposal progression on the submission path.',
        'tender': {
            'external_tender_id': 'GD-HEALTHY',
            'title': 'Healthy Submission Tender',
            'customer_name': 'Northwind',
            'due_at': '2030-04-30T10:00:00Z',
            'current_status': 'active',
            'departments': ['sales'],
            'requirement_contexts': [
                {
                    'external_requirement_id': 'REQ-1',
                    'reference': '1.1',
                    'summary': 'Provide ISO 27001 evidence',
                    'priority': 'high',
                    'compliance_status': 'fully_addressed',
                    'mapped_section_id': 'SEC-1',
                }
            ],
            'section_contexts': [
                {
                    'external_section_id': 'SEC-1',
                    'title': 'Security',
                    'owner_department': 'sales',
                    'status': 'approved',
                }
            ],
            'metadata': {'priority': 'high'},
        },
        'events': [
            {
                'event_type': 'tender_document_ingested',
                'occurred_at': '2026-03-15T08:00:00Z',
                'source': 'tw-backend',
                'payload': {'document_id': 'DOC-1'},
            },
            {
                'event_type': 'requirements_extracted',
                'occurred_at': '2026-03-15T08:05:00Z',
                'source': 'tw-backend',
                'payload': {'requirement_count': 1},
            },
            {
                'event_type': 'proposal_section_updated',
                'occurred_at': '2026-03-15T08:10:00Z',
                'source': 'tw-backend',
                'payload': {'external_section_id': 'SEC-1'},
            },
        ],
        'expected': {
            'analytical_phase': 'S7',
            'health': 'green',
            'top_forecast': 'submit_on_time',
        },
    },
    {
        'case_id': 'rework_pressure',
        'description': 'Tender under review with blocking rework and SLA friction.',
        'tender': {
            'external_tender_id': 'GD-REWORK',
            'title': 'Rework Pressure Tender',
            'customer_name': 'Northwind',
            'due_at': '2030-04-30T10:00:00Z',
            'current_status': 'in_progress',
            'departments': ['legal', 'sales'],
            'requirement_contexts': [
                {
                    'external_requirement_id': 'REQ-1',
                    'reference': '1.1',
                    'summary': 'Provide signed annex',
                    'priority': 'high',
                    'compliance_status': 'fully_addressed',
                    'mapped_section_id': 'SEC-1',
                }
            ],
            'section_contexts': [
                {
                    'external_section_id': 'SEC-1',
                    'title': 'Compliance',
                    'owner_department': 'legal',
                    'status': 'approved',
                }
            ],
            'metadata': {'priority': 'high'},
        },
        'events': [
            {
                'event_type': 'tender_document_ingested',
                'occurred_at': '2026-03-15T08:00:00Z',
                'source': 'tw-backend',
                'payload': {'document_id': 'DOC-1'},
            },
            {
                'event_type': 'requirements_extracted',
                'occurred_at': '2026-03-15T08:05:00Z',
                'source': 'tw-backend',
                'payload': {'requirement_count': 1},
            },
            {
                'event_type': 'contribution_request_created',
                'occurred_at': '2026-03-15T08:10:00Z',
                'source': 'tw-backend',
                'payload': {
                    'external_contribution_id': 'C1',
                    'external_request_id': 'R1',
                    'requested_at': '2026-03-15T08:00:00Z',
                    'due_at': '2026-03-16T08:00:00Z',
                    'sla_target_hours': 8,
                    'sla_max_hours': 24,
                },
            },
            {
                'event_type': 'contribution_received',
                'occurred_at': '2026-03-16T20:00:00Z',
                'source': 'tw-backend',
                'payload': {
                    'external_contribution_id': 'C1',
                    'external_request_id': 'R1',
                    'requested_at': '2026-03-15T08:00:00Z',
                    'received_at': '2026-03-16T20:00:00Z',
                    'due_at': '2026-03-16T08:00:00Z',
                    'response_time_hours': 36,
                    'lateness_hours': 12,
                },
            },
            {
                'event_type': 'contribution_review_started',
                'occurred_at': '2026-03-16T21:00:00Z',
                'source': 'tw-backend',
                'payload': {
                    'external_contribution_id': 'C1',
                    'external_review_cycle_id': 'RV-1',
                    'stage_name': 'quality_review',
                },
            },
            {
                'event_type': 'rework_requested',
                'occurred_at': '2026-03-16T22:00:00Z',
                'source': 'tw-backend',
                'payload': {
                    'external_contribution_id': 'C1',
                    'external_rework_id': 'RW1',
                    'severity': 'high',
                    'is_blocking': True,
                },
            },
        ],
        'expected': {
            'analytical_phase': 'S6',
            'health': 'red',
            'top_forecast': 'extended_rework',
        },
    },
    {
        'case_id': 'compliance_risk',
        'description': 'Tender blocked by a compliance gate failure.',
        'tender': {
            'external_tender_id': 'GD-COMPLIANCE',
            'title': 'Compliance Risk Tender',
            'customer_name': 'Northwind',
            'due_at': '2030-04-30T10:00:00Z',
            'current_status': 'in_progress',
            'departments': ['legal'],
            'requirement_contexts': [
                {
                    'external_requirement_id': 'REQ-1',
                    'reference': '1.1',
                    'summary': 'Provide signed annex',
                    'priority': 'high',
                    'compliance_status': 'not_addressed',
                    'mapped_section_id': 'SEC-1',
                }
            ],
            'section_contexts': [
                {
                    'external_section_id': 'SEC-1',
                    'title': 'Compliance',
                    'owner_department': 'legal',
                    'status': 'approved',
                }
            ],
            'metadata': {},
        },
        'events': [
            {
                'event_type': 'tender_document_ingested',
                'occurred_at': '2026-03-15T08:00:00Z',
                'source': 'tw-backend',
                'payload': {'document_id': 'DOC-1'},
            },
            {
                'event_type': 'requirements_extracted',
                'occurred_at': '2026-03-15T08:05:00Z',
                'source': 'tw-backend',
                'payload': {'requirement_count': 1},
            },
            {
                'event_type': 'compliance_gate_opened',
                'occurred_at': '2026-03-15T08:10:00Z',
                'source': 'tw-backend',
                'payload': {
                    'external_gate_id': 'G-1',
                    'gate_name': 'Auto compliance readiness',
                },
            },
            {
                'event_type': 'compliance_gate_failed',
                'occurred_at': '2026-03-15T08:20:00Z',
                'source': 'tw-backend',
                'payload': {
                    'external_gate_id': 'G-1',
                    'gate_name': 'Auto compliance readiness',
                    'status': 'failed',
                    'decision_notes': 'signed annex still missing',
                },
            },
        ],
        'expected': {
            'analytical_phase': 'S8',
            'health': 'red',
            'top_forecast': 'extended_rework',
        },
    },
    {
        'case_id': 'excluded_no_bid',
        'description': 'Tender explicitly excluded from the flow.',
        'tender': {
            'external_tender_id': 'GD-NOBID',
            'title': 'Excluded Tender',
            'customer_name': 'Northwind',
            'due_at': '2030-04-30T10:00:00Z',
            'current_status': 'no_bid',
            'departments': ['sales'],
            'requirement_contexts': [],
            'section_contexts': [],
            'metadata': {},
        },
        'events': [
            {
                'event_type': 'tender_outcome_recorded',
                'occurred_at': '2026-03-15T08:00:00Z',
                'source': 'tw-backend',
                'payload': {'outcome': 'no_bid'},
            },
        ],
        'expected': {
            'analytical_phase': 'S13',
            'top_forecast': 'stop_locked',
        },
    },
]
