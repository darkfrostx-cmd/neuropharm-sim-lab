# Dockerfile
FROM python:3.10-slim

# system libs needed for SciPy/NumPy/TVB/PySB builds & wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gfortran cmake pkg-config git \
    libopenblas-dev liblapack-dev libatlas-base-dev \
    libgsl-dev libffi-dev libssl-dev libhdf5-dev \
  && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip setuptools wheel

WORKDIR /app
COPY backend/ ./backend/
COPY backend/requirements.txt backend/requirements-optional.txt ./

# base deps
RUN pip install -r requirements.txt
# heavy/mechanistic extras (PySB, TVB, DoWhy/EconML)
RUN pip install -r requirements-optional.txt

ENV PORT=8080
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
