FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements/runtime-py311.txt requirements/runtime-py311.txt
COPY pyproject.toml pyproject.toml
COPY backend/src backend/src
COPY backend/migrations/community backend/migrations/community
RUN python -m pip install --require-hashes --requirement requirements/runtime-py311.txt \
    && python -m pip install --no-deps --no-build-isolation --editable . \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin veyra

COPY deploy/community/start.sh /usr/local/bin/veyra-community-start
RUN chmod 0755 /usr/local/bin/veyra-community-start \
    && chown -R root:root /app

USER veyra
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/ready', timeout=3)"

ENTRYPOINT ["/usr/local/bin/veyra-community-start"]
