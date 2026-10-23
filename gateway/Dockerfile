FROM python:3.13.15-slim
WORKDIR /app
COPY simulator/requirements.txt /app/simulator/requirements.txt
COPY gateway/requirements.txt /app/gateway/requirements.txt
RUN pip install --no-cache-dir -r gateway/requirements.txt
COPY simulator/model.py simulator/health.py /app/simulator/
COPY gateway/ /app/gateway/
COPY contracts/aiot.schema.json /app/contracts/aiot.schema.json
RUN mkdir /state && chown 65532:65532 /state && chmod 0700 /state
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 65532:65532
ENTRYPOINT ["python", "-m", "gateway.runtime", "--catalog", "/catalog/catalog.json", "--journal", "/state/gateway.sqlite3"]
