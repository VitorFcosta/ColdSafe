FROM python:3.13.15-slim
WORKDIR /app
COPY simulator/requirements.txt /app/simulator/requirements.txt
RUN pip install --no-cache-dir -r simulator/requirements.txt
COPY simulator/model.py simulator/runtime.py simulator/control.py simulator/health.py /app/simulator/
COPY contracts/aiot.schema.json /app/contracts/aiot.schema.json
USER 65532:65532
ENTRYPOINT ["python", "-m", "simulator.runtime", "--catalog", "/catalog/catalog.json"]
