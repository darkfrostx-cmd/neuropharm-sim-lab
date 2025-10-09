# syntax=docker/dockerfile:1

FROM python:3.10-slim AS builder

# system libs for SciPy/NumPy/TVB/PySB (no ATLAS on Debian trixie)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gfortran cmake pkg-config git \
    libopenblas-dev liblapack-dev \
    libgsl-dev libffi-dev libssl-dev libhdf5-dev \
    mono-runtime \
  && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip setuptools wheel

WORKDIR /app
COPY backend/ ./backend/
COPY backend/requirements.txt backend/requirements-optional.txt ./
COPY scripts/install_mechanistic_backends.sh ./scripts/install_mechanistic_backends.sh
RUN chmod +x ./scripts/install_mechanistic_backends.sh

# base deps
RUN pip install --no-cache-dir -r requirements.txt
# heavy/mechanistic extras (PySB, OSPSuite, TVB, DoWhy/EconML)
RUN INSTALL_OSPSUITE=${INSTALL_OSPSUITE:-1} \
    OSPSUITE_INDEX_URL=${OSPSUITE_INDEX_URL:-} \
    OSPSUITE_WHEEL_URL=${OSPSUITE_WHEEL_URL:-} \
    OSPSUITE_VERSION=${OSPSUITE_VERSION:-} \
    ./scripts/install_mechanistic_backends.sh

FROM python:3.10-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# system libs for SciPy/NumPy/TVB/PySB (no ATLAS on Debian trixie)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gfortran cmake pkg-config git \
    libopenblas-dev liblapack-dev \
    libgsl-dev libffi-dev libssl-dev libhdf5-dev \
    mono-runtime \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app
COPY backend/ ./backend/
COPY backend/requirements.txt backend/requirements-optional.txt ./
COPY scripts/install_mechanistic_backends.sh ./scripts/install_mechanistic_backends.sh

CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
