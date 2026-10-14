FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# App package lives under /srv/service_b so `service_b.main:app` imports resolve.
COPY . ./service_b

EXPOSE 8001

CMD ["uvicorn", "service_b.main:app", "--host", "0.0.0.0", "--port", "8001"]
