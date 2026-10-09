FROM python:3.13-slim-bookworm AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt


FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED 1

COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache /wheels/*

COPY ./app ./app

CMD python -m app.run.dispatcher
