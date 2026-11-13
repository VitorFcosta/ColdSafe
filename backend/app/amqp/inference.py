"""Private telemetry inference and activation in one bounded worker process."""
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
import pika
import psycopg

from backend.app.amqp.models import ModelWorker
from backend.app.services.models import ModelActivationBusy
from gateway.bridge import PermanentError, VALIDATORS, encode
from simulator.model import SCHEMA, strict_json, validate_catalog

PREDICTION = Draft202012Validator({**SCHEMA, '$ref': '#/$defs/prediction_event'},
                                  format_checker=FormatChecker())


class InferenceWorker(ModelWorker):
    def __init__(self, models, inference, catalog: dict, check_scope, *,
                 host: str, port: int, password: str):
        validate_catalog(catalog)
        self.inference, self.catalog, self.check_scope = inference, catalog, check_scope
        self.inference_pending = None
        super().__init__(models, host=host, port=port, password=password)

    def validate(self, route: str, properties: pika.BasicProperties, raw: bytes) -> dict:
        if len(raw) > 8192:
            raise PermanentError('PAYLOAD_TOO_LARGE')
        if not route.startswith('v3.telemetry.'):
            return super().validate(route, properties, raw)
        try:
            event = strict_json(raw)
            VALIDATORS['telemetry'].validate(event)
        except (ValueError, TypeError, UnicodeError, RecursionError, ValidationError):
            raise PermanentError('INVALID_SCHEMA') from None
        count = (properties.headers or {}).get('x-delivery-count', 0)
        if (route != f"v3.telemetry.{event['device_record_id']}" or event['received_at'] is None or
                properties.content_type != 'application/json' or properties.delivery_mode != 2 or
                properties.message_id != event['event_id'] or
                properties.correlation_id != event['correlation_id'] or
                not isinstance(count, int) or isinstance(count, bool) or count < 0):
            raise PermanentError('INVALID_BINDING')
        if any(event[key] != self.catalog[key] for key in ('device_id', 'device_record_id', 'environment_id')):
            raise PermanentError('UNAUTHORIZED_SCOPE')
        data = event['data']
        if (event['correlation_id'] != event['event_id'] or
                data['equipment']['equipment_id'] != self.catalog['equipment_id'] or
                any(value['sensor_id'] != self.catalog['sensors'][key]
                    for key, value in data['measurements'].items()) or
                any(value['actuator_id'] != self.catalog['actuators'][key]
                    for key, value in data['actuators'].items())):
            raise PermanentError('IDENTITY_MISMATCH')
        if not self.check_scope(self.catalog):
            raise PermanentError('UNAUTHORIZED_SCOPE')
        return event

    def execute(self, event: dict, channel) -> bool:
        if event['type'] == 'model_activation':
            return super().execute(event, channel)
        result = self._wait(self.executor.submit(self.inference.process, event), channel)
        return result is not None

    def flush_outputs(self, channel) -> None:
        super().flush_outputs(channel)
        for event in self.inference.pending_outputs():
            try:
                PREDICTION.validate(event)
            except ValidationError:
                raise ValueError('Invalid prediction output') from None
            channel.basic_publish('coldsafe.events',
                f"v3.prediction.{event['device_record_id']}", encode(event),
                pika.BasicProperties(content_type='application/json', delivery_mode=2,
                    message_id=event['event_id'], correlation_id=event['correlation_id']),
                mandatory=True)
            self.inference.mark_published(event['event_id'])

    def step(self, channel) -> None:
        super().step(channel)
        if self.inference_pending is None:
            self.inference_pending = channel.basic_get('coldsafe.inference', auto_ack=False)
        method, properties, raw = self.inference_pending
        if method is None:
            self.inference_pending = None
            return
        try:
            event = self.validate(method.routing_key, properties, raw)
            handled = self.execute(event, channel)
        except PermanentError:
            channel.basic_reject(method.delivery_tag, requeue=False)
            self.inference_pending = None
        except ModelActivationBusy:
            # Keep the broker delivery while another process holds the owner lock.
            return
        except (psycopg.Error, OSError):
            raise psycopg.OperationalError('Inference storage temporarily unavailable') from None
        else:
            if handled:
                self.flush_outputs(channel)
                channel.basic_ack(method.delivery_tag)
                self.inference_pending = None

    def disconnect(self) -> None:
        super().disconnect()
        self.inference_pending = None
