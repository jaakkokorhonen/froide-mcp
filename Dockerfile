FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer cache)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy source
COPY froide_mcp/ froide_mcp/

# Cloud Run injects PORT env var
ENV PORT=8080

CMD ["python", "-m", "froide_mcp.server"]
