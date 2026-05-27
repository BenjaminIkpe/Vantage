# Built with the repo root as context (see docker-compose.yml) so it can reuse the API's
# verified-token core + DB/tool layer as shared source — no duplication.
# PR1: these are copied from app/ while the API still runs tools in-process; a later slice
# relocates db.py/tools.py here and drops the API's database access (ADR-003 blast-radius).
FROM python:3.12-slim
WORKDIR /app
COPY mcp_server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/security.py app/db.py app/tools.py ./
COPY mcp_server/server.py ./
EXPOSE 8001
CMD ["python", "server.py"]
