# Operations

> Testing and deployment patterns for Python backend applications.

[![pytest](https://img.shields.io/badge/pytest-9.x-0A9EDC.svg?logo=pytest&logoColor=white)](https://pytest.org)
[![Docker](https://img.shields.io/badge/Docker-latest-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com)
[![Uvicorn](https://img.shields.io/badge/Uvicorn-0.30+-499848.svg)](https://www.uvicorn.org)
[![Gunicorn](https://img.shields.io/badge/Gunicorn-26.x-499848.svg)](https://gunicorn.org)

---

## Contents

| Section | Description |
|---------|-------------|
| [testing/](testing/README.md) | pytest, AsyncClient, dependency overrides, fixtures, mocking, LLM evals |
| [deployment/](deployment/README.md) | Docker, multi-stage builds, Uvicorn, Gunicorn, health checks, graceful shutdown |
| [Incident response](incident_response/README.md) | On-call ownership, runbooks and postmortems |
| [Cost management](cost_management/README.md) | Unit costs, attribution and budgets |
| [Developer experience](developer_experience/README.md) | Repeatable setup, hooks, containers and seed data |

---

## Prerequisites

- [fundamentals/fastapi/](../fundamentals/fastapi/README.md) — understand the application you're testing and deploying
- Basic pytest knowledge (for testing section)
- Basic Docker knowledge (for deployment section)
