FROM python:3.13.15-slim
WORKDIR /app
COPY simulator/requirements.txt /app/simulator/requirements.txt
COPY gateway/requirements.txt /app/gateway/requirements.txt
COPY writer/requirements.txt /app/writer/requirements.txt
RUN pip install --no-cache-dir -r writer/requirements.txt
COPY backend/app/ /app/backend/app/
COPY contracts/aiot.schema.json /app/contracts/aiot.schema.json
COPY simulator/model.py simulator/health.py /app/simulator/
COPY gateway/bridge.py /app/gateway/bridge.py
COPY writer/ /app/writer/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 65532:65532
ENTRYPOINT ["python", "-m", "writer.runtime", "--catalog", "/catalog/catalog.json"]
