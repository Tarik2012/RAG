FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://raw.githubusercontent.com/opengrep/opengrep/main/install.sh | bash \
    && OPENGREP_BIN="$(find /root/.opengrep -name 'opengrep*' -type f -executable | head -n1)" \
    && cp "$OPENGREP_BIN" /usr/local/bin/opengrep \
    && chmod +x /usr/local/bin/opengrep \
    && opengrep --version

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN python manage.py collectstatic --noinput --clear 2>/dev/null || true

EXPOSE 8000

CMD sh -c "python manage.py migrate && (python manage.py createsuperuser --noinput || true) && gunicorn rag_backend.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120"
