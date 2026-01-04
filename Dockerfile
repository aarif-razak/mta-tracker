FROM python:3.13.5 AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN python -m venv .venv
COPY requirements.txt ./
RUN .venv/bin/pip install -r requirements.txt

FROM python:3.13.5-slim
WORKDIR /app
COPY --from=builder /app/.venv .venv/
COPY . .

# Download stops.txt if not present
RUN if [ ! -f stops.txt ]; then \
    apt-get update && apt-get install -y curl unzip && \
    curl -L -o google_transit.zip http://web.mta.info/developers/data/nyct/subway/google_transit.zip && \
    unzip -o google_transit.zip stops.txt && \
    rm google_transit.zip && \
    apt-get remove -y curl unzip && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*; \
    fi

# Use python app.py to start background thread
CMD ["/app/.venv/bin/python", "app.py"]
