# Security

ArdvarkFood includes a web application, a local image-generation pipeline, and
an optional LLM agent runtime. Security reports are welcome; please report
suspected vulnerabilities privately so they can be investigated before details
are made public.

## Reporting a vulnerability

**Do not report security vulnerabilities in public issues, discussions, or pull
requests.**

Use GitHub's private vulnerability reporting for this repository:

<https://github.com/TheWildKaden/ArdvarkFood/security/advisories/new>

If private reporting is unavailable, contact the repository owner privately
through GitHub:

<https://github.com/TheWildKaden>

Please include, when known:

- The affected commit, release, endpoint, or component.
- The impact and conditions needed to reproduce the issue.
- A concise reproduction or proof of concept that does not access other
  people's data, destroy data, or disrupt a service.
- Any suggested mitigation.

Do not include real credentials, personal data, or other people's information
in a report. You may encrypt sensitive attachments using a method agreed with
the maintainer. Please allow maintainers a reasonable opportunity to investigate
and coordinate a fix before publishing technical details. The maintainer will
acknowledge a report as soon as practical and will share status updates when
available; response and remediation times are not guaranteed.

## What to report

Report vulnerabilities that could compromise the confidentiality, integrity,
or availability of this project or a deployment, including issues in:

- The FastAPI endpoints and configuration handling.
- The LLM agent loop, tool permissions, approval flow, and execution state.
- Workspace file access, command execution, MCP connections, or outbound
  network tools.
- Conversation, memory, audit, and generated-file storage.
- Dependency or deployment configurations maintained in this repository.

This project has no authentication layer for its runtime API. A deployment
reachable by untrusted users can expose conversations, model controls, tool
approvals, and other runtime operations. Do not expose it to the public
internet or an untrusted network without adding and verifying an appropriate
authentication and authorization layer.

## Deployment security notes

- Keep the application bound to a trusted, access-controlled network.
- Keep API keys and other secrets in environment secrets or a secret manager;
  never commit them to source, settings files, logs, or issue reports.
- Configure model and storage paths deliberately. Restrict filesystem
  permissions on model files, SQLite databases, and generated artifacts.
- Review tool permissions before deployment. Filesystem and Git reads are
  auto-approved by default; writes, terminal, Python, network, and MCP
  operations require approval by default. Configuration can change these
  defaults, so review the effective runtime settings.
- Approval is not authentication. A person able to reach the approval endpoint
  may be able to resolve pending operations. Restrict access to all runtime
  endpoints.
- Python tools run in a subprocess, **not** an operating-system sandbox.
  Approval does not make untrusted code safe. Disable or remove this tool if
  approved code execution is not appropriate for your deployment.
- Network tools require an explicit host allowlist and reject non-public
  resolved addresses, but this is not a substitute for network-level egress
  controls. Use a restrictive allowlist and outbound firewall rules.
- MCP server commands run with the application's operating-system privileges.
  Configure only trusted servers and review their commands, arguments, and
  environment.
- Treat prompts, model output, attachments, tool results, and retrieved memory
  as untrusted input. Do not rely on prompt instructions as a security
  boundary.
- Use trusted model files and dependencies. Review upstream model licenses and
  security advisories; model-generated output can be inaccurate or unsafe.
- Back up the SQLite database securely and protect backups as sensitive data.

## Supported versions

This repository does not currently publish a formal version-support or
security-update schedule. Until releases and supported branches are explicitly
designated, security reports should target the latest code on the default
branch. Users should update to the latest reviewed revision when a fix is
available.

## Coordinated disclosure

Please keep a report and exploit details private while a fix is being
investigated. Once a fix or mitigation is available, the reporter and
maintainers can coordinate an appropriate disclosure that explains the impact
and remediation without exposing users to unnecessary risk.
