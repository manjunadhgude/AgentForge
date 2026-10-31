# Security Policy

## Supported scope

AgentForge is an educational reliability-engineering prototype. It is not a security-certified service and should not be exposed to the public internet without a separate deployment and security review.

## Reporting a vulnerability

Please do not publish secrets, access tokens, personal data, or exploitable details in a public issue. Use GitHub's private vulnerability reporting feature if it is enabled for this repository. Otherwise contact the repository maintainer privately through a verified GitHub contact channel and include:
- affected version/commit and component;
- concise impact and reproduction steps;
- any safe mitigation already identified.

Do not include real credentials or production data.

## Security boundaries

- Never commit `.env` files, API keys, database passwords, private keys, database dumps, or real customer data.
- Keep the API bound to a trusted local/development environment unless TLS, authentication/authorization, rate limiting, secret management, logging, monitoring, and network access controls have been reviewed.
- The default demos use simulated tools. Do not connect side-effecting production systems without downstream idempotency and reconciliation.
- A passing dependency audit is time-bound evidence, not a guarantee that the entire project is vulnerability-free.
