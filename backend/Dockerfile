# <dockerfile name="backend" stack="FastAPI + asyncpg">
#   Builds the API server image. Tables are auto-created on first boot, so there
#   is no separate migration step. Configuration comes from environment
#   variables (see docker-compose.yml / DEPLOYMENT.md).
# </dockerfile>
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install only the runtime dependencies (small, reliable).
COPY requirements-runtime.txt .
RUN pip install -r requirements-runtime.txt

# Copy the application code.
COPY . .

EXPOSE 8000

# Start the API. server:app = the FastAPI instance in server.py.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
