FROM python:3.9-slim

# Set environment variables
ENV FLASK_APP=app:app
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-realsplendid \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy application code
COPY ./backend/ ./backend/

# Install Python dependencies
RUN pip install --no-cache-dir -r ./backend/requirements.txt

# Expose port
EXPOSE 5000

# Copy the start script
COPY ./scripts/start.sh ./start.sh
RUN chmod +x ./start.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Command to run the application
CMD ["./start.sh"]