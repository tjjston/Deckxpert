FROM python:3.11-slim

ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

RUN apt-get update \
    && apt-get install -y --no-install-recommends php-cli tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "sim_harness.web", "--host", "0.0.0.0", "--port", "8765"]
