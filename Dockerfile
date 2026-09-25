# Mealplanner als container. Gegevens (database, foto's, iconen, API-sleutels) staan in /data;
# koppel daar een map of volume aan, anders ben je ze kwijt als de container verdwijnt.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MEALPLANNER_DB=/data/mealplanner.db

WORKDIR /app

# Eerst alleen de afhankelijkheden, zodat die laag hergebruikt wordt als alleen de code verandert.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY mealplanner ./mealplanner
COPY static ./static

# Niet als root draaien. UID 1000 is meestal ook de eerste gebruiker op de host,
# zodat een gekoppelde map ./data gewoon beschrijfbaar is.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin mealplanner \
    && mkdir /data && chown mealplanner:mealplanner /data
USER mealplanner

VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1

CMD ["python", "-m", "mealplanner.server", "--host", "0.0.0.0", "--port", "8000"]
