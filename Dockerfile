FROM python:3.12-slim

WORKDIR /app

# Copy source and metadata together so pip install has the package available
COPY pyproject.toml .
COPY froide_mcp/ froide_mcp/

# Install production dependencies (non-editable — editable installs are not
# appropriate for immutable container images)
RUN pip install --no-cache-dir .

# Cloud Run injects PORT env var
ENV PORT=8080

CMD ["python", "-m", "froide_mcp.server"]
