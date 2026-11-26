# Security

## Reporting

Please open a private security advisory on the GitHub repository rather than a public issue.

## Controls in this repo

- **Secrets:** none in code. The database URL comes from `FAI_DATABASE_URL`, and Compose requires `POSTGRES_PASSWORD` from `.env` (git-ignored). Gitleaks runs in CI.
- **SQL:** all queries go through SQLAlchemy with bound parameters. There is no string-built SQL.
- **Untrusted files:** downloads are parsed as data with `dtype=str` and validated before load. No macros run, and there is no `eval` or pickle.
- **LLM input:** document text is wrapped and marked as data in the system prompt. Output is schema-validated, and any value whose citation cannot be found in the source is dropped. Treat prompt injection in council PDFs as a real threat, not a theoretical one.
- **Container:** multi-stage build, non-root user (uid 10001), read-only root filesystem, `no-new-privileges`. Raw data is mounted read-only. Postgres binds to localhost only.
- **Supply chain:** Dependabot (pip, Actions, Docker), pip-audit, Trivy image scan, bandit.

## Data

Only public statistics are used. Do not commit raw downloads, and do not publish risk scores for named councils without the caveats in the README.
