# Engine only. The frontend is a separate, static app -- see web/.
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mplad_shield/ ./mplad_shield/
COPY run.py .
COPY tests/ ./tests/

# Default run writes outputs/ into the mounted working directory:
#   docker build -t mplad-shield .
#   docker run --rm -v "${PWD}:/app" mplad-shield python run.py
CMD ["python", "run.py"]
