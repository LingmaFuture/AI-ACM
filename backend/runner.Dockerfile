FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1

RUN pip install --no-cache-dir "numpy>=2.1,<3" \
    && useradd --create-home --uid 10001 runner

WORKDIR /runner
COPY app/runner.py ./runner.py
USER 10001:10001

ENTRYPOINT ["python", "/runner/runner.py"]

