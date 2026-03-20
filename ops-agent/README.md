# TenderWriter Ops Agent

Internal privileged service for operational Docker actions.

## Purpose

This service is the only TenderWriter component allowed to access `docker.sock`.
It exposes a minimal allowlisted API for:

- listing `tw-*` containers
- reading logs for `tw-*` containers
- reading stats for `tw-*` containers
- reloading Nginx timeouts only inside `tw-frontend`

It is intended to be reachable only from the internal Docker network.

## Required Environment Variables

- `OPS_AGENT_TOKEN`

## Optional Environment Variables

- `OPS_AGENT_HOST` default `0.0.0.0`
- `OPS_AGENT_PORT` default `8070`
- `OPS_ALLOWED_PREFIX` default `tw-`
- `OPS_FRONTEND_CONTAINER` default `tw-frontend`

## Security Notes

- No generic Docker proxy endpoints are exposed.
- Arbitrary `exec` is intentionally forbidden.
- Container access is allowlisted by prefix and sanitized before lookup.
- Browser traffic should never hit this service directly.
