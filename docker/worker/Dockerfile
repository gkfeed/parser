FROM python:3.13-slim-bookworm AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt


FROM python:3.13-slim-bookworm
#ENV PYTHONUNBUFFERED 1

COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache /wheels/*

ARG INSTALL_PLAYWRIGHT=false
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then \
      python -m playwright install --with-deps --only-shell chromium \
      && rm -rf /var/lib/apt/lists/*; \
    fi

COPY ./app ./app
COPY ./docker/worker/run-worker /usr/local/bin/run-worker

RUN chmod +x /usr/local/bin/run-worker

ENTRYPOINT ["/usr/local/bin/run-worker"]
