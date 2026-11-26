# syntax=docker/dockerfile:1
FROM python:3.13-slim AS build
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip \
 && pip wheel --no-cache-dir --wheel-dir /wheels ".[postgres]"

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Pull Debian security fixes released after the base image was built.
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 radar
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir /wheels/* \
 && rm -rf /wheels
WORKDIR /app
COPY --chown=radar:radar data ./data
COPY --chown=radar:radar sql ./sql
USER radar
ENTRYPOINT ["council-radar"]
CMD ["--help"]
