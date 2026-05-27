# Built with the repo root as context (see docker-compose.yml). This service OWNS the DB
# (db.py) and the tools (tools.py); only the token-verification core (security.py) is shared
# with the API, copied from app/. The API holds no database access (ADR-003 blast-radius).
FROM python:3.12-slim
WORKDIR /app
COPY mcp_server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/security.py ./
COPY mcp_server/db.py mcp_server/tools.py mcp_server/server.py ./
EXPOSE 8001
CMD ["python", "server.py"]
