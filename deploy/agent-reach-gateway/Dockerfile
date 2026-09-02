FROM node:22-bookworm-slim AS node_runtime

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    PIP_NO_CACHE_DIR=1 \\
    AGENT_REACH_LANG=ko

# Agent Reach's mcporter backend requires modern node:crypto APIs.
COPY --from=node_runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node_runtime /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \\
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

RUN apt-get update && apt-get install -y --no-install-recommends \\
    ca-certificates curl git jq gh \\
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip setuptools wheel pipx \\
    && python -m pip install \\
      "agent-reach[all] @ https://github.com/Panniantong/Agent-Reach/archive/main.zip" \\
      fastapi "uvicorn[standard]"

# User explicitly approved expanded cloud installation. Keep the build resilient:
# if an upstream optional channel cannot install on a server image, runtime doctor
# reports it instead of preventing the public/basic gateway from starting.
RUN agent-reach install --env=auto --system || \\
    echo "Agent Reach optional system setup was partial; runtime doctor will report channel status."

WORKDIR /app
COPY app.py /app/app.py

EXPOSE 10000
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000}"]
