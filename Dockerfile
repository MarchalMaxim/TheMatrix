# TheMatrix — stdlib-only Python web app; no third-party deps needed.
FROM python:3.12-slim

WORKDIR /app

# Copy the application. .dockerignore keeps data/, worker/, .env, .git out.
COPY . .

# Cloud Run injects PORT; server.py reads HOST and PORT from env.
# Default to 0.0.0.0:8080 for local-container runs.
ENV HOST=0.0.0.0
ENV PORT=8080
EXPOSE 8080

# Unbuffered stdout so logs appear in Cloud Logging immediately.
ENV PYTHONUNBUFFERED=1

CMD ["python", "server.py"]
