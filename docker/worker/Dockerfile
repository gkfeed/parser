FROM python:3.12-alpine as builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt


FROM python:3.12-alpine

ENV IS_WORKER 1
#ENV PYTHONUNBUFFERED 1

COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache /wheels/*

COPY ./app ./app
