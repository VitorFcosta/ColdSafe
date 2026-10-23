"""Small owner-scoped facts for the LLM; this path never changes operational state."""
from datetime import UTC, datetime
import math
from uuid import UUID

from psycopg.rows import dict_row

from backend.app.repositories.postgres import connect

SENSORS = ('ambient_temperature', 'humidity', 'light', 'motor_temperature',
           'vibration', 'motor_current')
ARCHITECTURE = ('O simulador envia medições ao MQTT. O gateway recebe essas mensagens e as '
                'encaminha ao RabbitMQ. As leituras ficam no InfluxDB. Contas, alertas e modelos '
                'ficam no PostgreSQL. A API fornece dados para a interface Vue e o gêmeo 3D. '
                'O Ollama executa o LLM localmente, em CPU, sem ferramentas ou acesso a bancos.')

# shortcut: two worst devices and six sensors, expand only with a larger measured LLM context.
DEVICES = """
WITH facts AS (
    SELECT d.mqtt_device_id AS device, t.envelope AS reading, t.received_at,
           p.envelope->'data' AS prediction,
           count(*) OVER () AS devices,
           count(*) FILTER (WHERE t.event_id IS NULL) OVER () AS missing_readings,
           count(*) FILTER (WHERE t.received_at < %(now)s - interval '30 seconds') OVER () AS stale_readings,
           count(*) FILTER (WHERE t.received_at >= %(now)s - interval '30 seconds'
                            AND p.envelope->'data'->>'status'='available') OVER () AS fresh_predictions
    FROM devices d JOIN environments e ON e.id=d.environment_id
    LEFT JOIN LATERAL (
        SELECT t.event_id,t.received_at,t.envelope FROM aiot_events t
        WHERE t.device_id=d.id AND t.kind='telemetry'
          AND t.envelope->>'environment_id'=e.id::text
          AND t.envelope->>'device_id'=d.mqtt_device_id
        ORDER BY t.received_at DESC,t.event_id DESC LIMIT 1
    ) t ON true
    LEFT JOIN LATERAL (
        SELECT p.envelope FROM aiot_events p
        LEFT JOIN models m ON m.id::text=p.envelope->'data'->>'model_id' AND m.owner_user_id=e.owner_user_id
        WHERE p.device_id=d.id AND p.kind='prediction' AND p.linked
          AND (m.id IS NOT NULL OR (p.envelope->'data'->>'model_id' IS NULL
               AND p.envelope->'data'->>'reason'='no_model'))
          AND p.source_event_id=t.event_id AND p.envelope->>'environment_id'=e.id::text
          AND EXISTS (SELECT 1 FROM aiot_events r WHERE r.source_event_id=t.event_id
                      AND r.device_id=d.id AND r.kind='telemetry_persisted' AND r.linked)
        ORDER BY p.received_at,p.event_id LIMIT 1
    ) p ON true
    WHERE e.owner_user_id=%(owner)s AND d.is_active
), ranked AS (
    SELECT *,
        row_number() OVER (ORDER BY CASE WHEN received_at >= %(now)s - interval '30 seconds'
            AND prediction->>'status'='available' THEN (prediction->>'health_score')::float8 END
            NULLS LAST,device) AS health_rank,
        row_number() OVER (ORDER BY CASE WHEN received_at >= %(now)s - interval '30 seconds'
            AND prediction->>'status'='available' THEN (prediction->>'rul_hours')::float8 END
            NULLS LAST,device) AS rul_rank
    FROM facts
)
SELECT * FROM ranked WHERE health_rank=1 OR rul_rank=1 ORDER BY health_rank LIMIT 2
"""


def number(value):
    """Only finite, short numeric facts cross the model boundary."""
    if type(value) not in (int, float):
        return None
    try:
        return float(f'{value:.6g}') if math.isfinite(value) else None
    except OverflowError:
        return None


def equipment(row, now):
    reading = row['reading']
    age = max(0, (now - row['received_at']).total_seconds()) if reading else None
    state = 'no_data' if age is None else 'fresh' if age <= 30 else 'stale'
    prediction = row['prediction'] or {}
    status = prediction.get('status', 'no_data') if state == 'fresh' else state
    sensors = (reading.get('data', {}).get('measurements', {}) if state == 'fresh' else {})
    return {
        'device': row['device'][:64], 'reading': state, 'age_s': int(age) if age is not None else None,
        'prediction': status, 'model': str(prediction.get('model_version') or '')[:32],
        'reason': prediction.get('reason') if state == 'fresh' else None,
        'health': number(prediction.get('health_score')) if status == 'available' else None,
        'rul_h': number(prediction.get('rul_hours')) if status == 'available' else None,
        'sensors': {key: [number(sensors[key].get('value')), str(sensors[key].get('unit', ''))[:8]]
                    for key in SENSORS if key in sensors},
    }


class AssistantContext:
    def __init__(self, settings):
        self.settings = settings

    @staticmethod
    def _now():
        return datetime.now(UTC)

    def build(self, owner: UUID) -> dict:
        now = self._now()
        with connect(self.settings) as connection:
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            connection.execute("SET LOCAL statement_timeout='3s'")
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(DEVICES, {'owner': owner, 'now': now}).fetchall()
                alerts = cursor.execute(
                    "SELECT (SELECT count(*) FROM aiot_alerts a JOIN devices d ON d.id=a.device_id "
                    'JOIN environments e ON e.id=d.environment_id WHERE e.owner_user_id=%s '
                    "AND d.is_active AND a.closed_at IS NULL AND a.envelope->>'environment_id'=e.id::text) AS temperature, "
                    '(SELECT count(*) FROM predictive_alerts a JOIN devices d ON d.id=a.device_id '
                    'JOIN environments e ON e.id=d.environment_id WHERE e.owner_user_id=%s '
                    'AND a.owner_user_id=%s AND d.is_active AND a.closed_at IS NULL) AS predictive',
                    (owner, owner, owner)).fetchone()
                model = cursor.execute(
                    "SELECT m.model_version,m.metrics#>'{health,metrics,test,candidate,mae}' AS health_mae, "
                    "m.metrics#>'{rul,metrics,test,candidate,mae}' AS rul_mae FROM active_models a JOIN models m "
                    'ON (m.id,m.owner_user_id)=(a.model_id,a.owner_user_id) '
                    'WHERE a.owner_user_id=%s LIMIT 1', (owner,)).fetchone()
        items = [equipment(row, now) for row in rows]
        if len(items) == 2:
            items = [items[0], {**items[1], 'sensors': {}}]
        return {
            'scope': {**{key: rows[0][key] if rows else 0 for key in
                        ('devices', 'missing_readings', 'stale_readings', 'fresh_predictions')},
                      'sample': 'min_health,min_rul;readings:first',
                      'truncated': bool(rows and rows[0]['devices'] > len(items))},
            'equipment': items, 'alerts': dict(alerts),
            'model': {'version': model['model_version'][:32], 'test_mae': {
                target: number(model[target + '_mae']) for target in ('health', 'rul')}} if model else None,
            'architecture': ARCHITECTURE,
            'limits': 'Dados ausentes/antigos não são atuais; métricas sintéticas sem calibração física.',
        }
