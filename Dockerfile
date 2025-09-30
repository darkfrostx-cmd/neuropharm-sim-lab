# Dockerfile
FROM python:3.10-slim

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
RUN pip install -r requirements.txt
# heavy/mechanistic extras (PySB, OSPSuite, TVB, DoWhy/EconML)
RUN INSTALL_OSPSUITE=${INSTALL_OSPSUITE:-1} \ 
    OSPSUITE_INDEX_URL=${OSPSUITE_INDEX_URL:-} \ 
    OSPSUITE_WHEEL_URL=${OSPSUITE_WHEEL_URL:-} \ 
    OSPSUITE_VERSION=${OSPSUITE_VERSION:-} \ 
    ./scripts/install_mechanistic_backends.sh

ENV PORT=8080
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
