# Container image for the Claude Code usage-telemetry receiver.
# Stdlib-only — no pip install needed.
FROM python:3.12-slim

WORKDIR /app
COPY billing/ ./billing/

# Persist the store + request log on a mounted volume, not in the image.
ENV OTEL_DB=/data/otel.db \
    RECEIVER_LOG=/data/receiver.log \
    PYTHONUNBUFFERED=1

VOLUME ["/data"]
EXPOSE 4318

# Bind to all interfaces inside the container (the host/proxy controls exposure).
# --require-auth: refuse to start unless RECEIVER_AUTH_TOKEN is set, so a missing
# token is a loud startup failure instead of an open billing endpoint. Pass the
# token in with `--env-file .env` (docker run) or `env_file:` (compose). Override
# the command to drop the flag only for a throwaway localhost test.
CMD ["python", "-m", "billing.otel.receiver", \
     "--host", "0.0.0.0", "--port", "4318", "--require-auth"]
