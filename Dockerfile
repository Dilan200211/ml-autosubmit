FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered output for logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY config.py .
COPY monsterlab_api.py .
COPY database.py .
COPY scheduler.py .
COPY utils.py .
COPY bot.py .

# Create a non-root user with UID in Choreo's required range (10000-20000)
RUN useradd --create-home --uid 10001 botuser
USER 10001

# Default DB path — use /tmp which is always writable in containers
ENV DB_PATH=/tmp/submissions.db

CMD ["python", "bot.py"]
