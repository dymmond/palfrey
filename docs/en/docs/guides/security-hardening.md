# Guide: Security Hardening

This guide focuses on practical controls that reduce common risk.

## 1. Network exposure

- bind only necessary interfaces
- avoid exposing debug/dev commands publicly
- use firewall/security group rules in addition to app configuration

## 2. Proxy trust boundaries

- enable `--proxy-headers` only when needed
- restrict `--forwarded-allow-ips` to known proxy sources
- do not use wildcard trust unless absolutely required

## 3. TLS strategy

- prefer edge TLS termination for managed environments
- if terminating in Palfrey, secure key files and certificate lifecycle

## 4. Request and resource limits

- configure `--limit-concurrency` to avoid overload collapse
- set sensible websocket size/queue limits
- use worker recycling options for long-lived deployments

## 5. Logging and privacy

- avoid logging secrets or raw sensitive payloads
- include request IDs for traceability
- keep retention and access controls compliant with policy

## 6. Dependency and release hygiene

- pin dependencies
- patch regularly
- run tests and docs checks before release

## Plain-language summary

Security hardening is mostly about reducing trust and reducing blast radius.
You decide what to trust, who can reach the service, and how much work it can accept.
