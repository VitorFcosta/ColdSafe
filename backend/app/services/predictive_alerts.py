"""Durable predictive hysteresis; synthetic thresholds require domain calibration."""
from math import isfinite
from uuid import uuid4

from simulator.model import utc


DEFAULT_RULES = {
    'health_critical': 30, 'health_recovery': 40,
    'rul_critical_hours': 24, 'rul_recovery_hours': 48,
    'open_count': 3, 'close_count': 10,
}


def validate_rules(values: dict) -> dict:
    if not isinstance(values, dict) or values.keys() != DEFAULT_RULES.keys():
        raise ValueError('All predictive rule fields are required')
    for key, value in values.items():
        try:
            finite = type(value) in (int, float) and isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError('Predictive thresholds must be finite numbers')
        if key.endswith('count') and (type(value) is not int or not 1 <= value <= 100):
            raise ValueError('Predictive consecutive counts must be integers from 1 to 100')
    if not (0 <= values['health_critical'] < values['health_recovery'] <= 100
            and 0 <= values['rul_critical_hours'] < values['rul_recovery_hours']):
        raise ValueError('Recovery thresholds must exceed critical thresholds')
    return dict(values)


def advance_streak(state: dict, health: float | None, rul: float | None,
                   active: bool, rules: dict) -> tuple[dict, str | None]:
    result = {**state, 'critical_streak': 0, 'recovery_streak': 0,
              'health_score': health, 'rul_hours': rul, 'trend': 'unknown'}
    if health is None or rul is None:
        return result, None
    if state['health_score'] is not None and state['rul_hours'] is not None:
        previous = (state['health_score'], state['rul_hours'])
        result['trend'] = ('declining' if health < previous[0] or rul < previous[1] else
                           'improving' if health > previous[0] or rul > previous[1] else 'stable')
    critical = health <= rules['health_critical'] or rul <= rules['rul_critical_hours']
    recovered = health >= rules['health_recovery'] and rul >= rules['rul_recovery_hours']
    if not active and critical:
        result['critical_streak'] = state['critical_streak'] + 1
        if result['critical_streak'] >= rules['open_count']:
            return result, 'opened'
    if active and recovered:
        result['recovery_streak'] = state['recovery_streak'] + 1
        if result['recovery_streak'] >= rules['close_count']:
            return result, 'closed'
    return result, None


class PredictiveAlertService:
    def __init__(self, events):
        self.events = events

    @property
    def scope(self) -> tuple:
        return (self.events.owner_user_id, self.events.catalog['device_record_id'],
                self.events.catalog['equipment_id'])

    def rules(self, cursor) -> dict:
        cursor.execute('INSERT INTO predictive_rules(owner_user_id) VALUES(%s) ON CONFLICT DO NOTHING',
                       (self.scope[0],))
        row = cursor.execute('SELECT * FROM predictive_rules WHERE owner_user_id=%s FOR UPDATE',
                             (self.scope[0],)).fetchone()
        return {key: row[key] for key in DEFAULT_RULES}

    def reset_stale(self, cursor) -> None:
        cursor.execute('UPDATE predictive_state SET critical_streak=0,recovery_streak=0,'
                       "health_score=NULL,rul_hours=NULL,trend='unknown' "
                       'WHERE owner_user_id=%s AND device_id=%s AND equipment_id=%s '
                       "AND last_input_at < %s - interval '30 seconds'", (*self.scope, self.events._now()))

    def evaluate(self, cursor, source_event_id: str) -> None:
        from backend.app.services.aiot_events import instant

        rules = self.rules(cursor)
        self.reset_stale(cursor)
        source_row = cursor.execute("SELECT envelope FROM aiot_events WHERE event_id=%s "
                                    "AND device_id=%s AND kind='telemetry'",
                                    (source_event_id, self.scope[1])).fetchone()
        if source_row is None:
            return
        source = source_row['envelope']
        row = cursor.execute("SELECT p.envelope FROM aiot_events p WHERE p.device_id=%s "
                             "AND p.source_event_id=%s AND p.kind='prediction' AND p.linked "
                             "AND EXISTS(SELECT 1 FROM aiot_events r WHERE r.source_event_id=p.source_event_id "
                             "AND r.kind='telemetry_persisted' AND r.linked) "
                             'ORDER BY p.received_at,p.event_id LIMIT 1',
                             (self.scope[1], source['event_id'])).fetchone()
        if row is None:
            return
        prediction = row['envelope']
        data = prediction['data']
        received = instant(data['input_received_at'])
        cursor.execute('INSERT INTO predictive_state(owner_user_id,device_id,equipment_id) '
                       'VALUES(%s,%s,%s) ON CONFLICT DO NOTHING', self.scope)
        state = cursor.execute('SELECT * FROM predictive_state WHERE owner_user_id=%s '
                               'AND device_id=%s AND equipment_id=%s FOR UPDATE', self.scope).fetchone()
        if state['last_input_at'] is not None and received <= state['last_input_at']:
            return
        if str(state['last_model_id']) != str(data['model_id']):
            state = {**state, 'critical_streak': 0, 'recovery_streak': 0,
                     'health_score': None, 'rul_hours': None}
        active = cursor.execute('SELECT alert_id FROM predictive_alerts WHERE owner_user_id=%s '
                                'AND device_id=%s AND equipment_id=%s AND closed_at IS NULL',
                                self.scope).fetchone()
        usable = data['status'] == 'available' and (self.events._now() - received).total_seconds() <= 30
        updated, transition = advance_streak(state, data['health_score'] if usable else None,
                                             data['rul_hours'] if usable else None, bool(active), rules)
        cursor.execute('UPDATE predictive_state SET last_source_event_id=%s,last_input_at=%s,last_model_id=%s,'
                       'critical_streak=%s,recovery_streak=%s,health_score=%s,rul_hours=%s,trend=%s '
                       'WHERE owner_user_id=%s AND device_id=%s AND equipment_id=%s',
                       (source['event_id'], received, data['model_id'], updated['critical_streak'], updated['recovery_streak'],
                        updated['health_score'], updated['rul_hours'], updated['trend'], *self.scope))
        if transition is None:
            return
        alert_id = str(uuid4()) if transition == 'opened' else str(active['alert_id'])
        if transition == 'opened':
            cursor.execute('INSERT INTO predictive_alerts(alert_id,owner_user_id,device_id,equipment_id,'
                           'opened_at,source_event_id,prediction_event_id) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                           (alert_id, *self.scope, self.events._now(), source['event_id'], prediction['event_id']))
        else:
            cursor.execute('UPDATE predictive_alerts SET closed_at=%s,closed_prediction_event_id=%s '
                           'WHERE alert_id=%s', (self.events._now(), prediction['event_id'], alert_id))
        self.events._audit(cursor, f'predictive_alert_{transition}', {
            'alert_id': alert_id, 'equipment_id': self.scope[2], 'owner_user_id': self.scope[0],
            'source_event_id': source['event_id'], 'prediction_event_id': prediction['event_id'],
            'rules': rules})

    def snapshot(self, user_id, device_id: str) -> dict | None:
        from backend.app.services.aiot_events import instant

        with self.events._cursor() as cursor:
            if device_id != self.events.catalog['device_id'] or not self.events._scope(cursor, user_id):
                return None
            self.reset_stale(cursor)
            rules = self.rules(cursor)
            source = self.events._latest(cursor, self.scope[1])
            prediction = None
            if source:
                row = cursor.execute("SELECT envelope FROM aiot_events WHERE device_id=%s "
                                     "AND source_event_id=%s AND kind='prediction' AND linked "
                                     'ORDER BY received_at,event_id LIMIT 1',
                                     (self.scope[1], source['event_id'])).fetchone()
                if row:
                    prediction = self.events._deliverable_prediction(cursor, row['envelope'])
            age = ((self.events._now() - instant(source['received_at'])).total_seconds() if source else None)
            availability = ('no_data' if source is None else 'stale' if age > 30 else
                            prediction['data']['status'] if prediction else 'no_data')
            state = cursor.execute('SELECT trend,last_source_event_id FROM predictive_state WHERE owner_user_id=%s '
                                   'AND device_id=%s AND equipment_id=%s', self.scope).fetchone()
            alerts = cursor.execute('SELECT alert_id,opened_at,source_event_id,prediction_event_id '
                                    'FROM predictive_alerts WHERE owner_user_id=%s AND device_id=%s '
                                    'AND equipment_id=%s AND closed_at IS NULL ORDER BY opened_at', self.scope).fetchall()
            return {'device_id': device_id, 'equipment_id': self.scope[2], 'rules': rules,
                    'prediction': prediction, 'availability': availability, 'age_seconds': age,
                    'trend': state['trend'] if (state and availability == 'available'
                                               and str(state['last_source_event_id']) == source['event_id']) else 'unknown',
                    'active_alerts': [{**{key: str(value) for key, value in alert.items()},
                                      'opened_at': utc(alert['opened_at']), 'kind': 'predictive_failure'}
                                     for alert in alerts]}

    def update_rules(self, user_id, device_id: str, values: dict) -> dict | None:
        values = validate_rules(values)
        with self.events._cursor() as cursor:
            if device_id != self.events.catalog['device_id'] or not self.events._scope(cursor, user_id):
                return None
            role = cursor.execute('SELECT role FROM users WHERE id=%s', (user_id,)).fetchone()
            if role is None or role['role'] not in ('operator', 'admin'):
                raise PermissionError('FORBIDDEN')
            previous = self.rules(cursor)
            if previous == values:
                return values
            cursor.execute('UPDATE predictive_rules SET health_critical=%s,health_recovery=%s,'
                           'rul_critical_hours=%s,rul_recovery_hours=%s,open_count=%s,close_count=%s '
                           'WHERE owner_user_id=%s', (*[values[key] for key in DEFAULT_RULES], self.scope[0]))
            cursor.execute('UPDATE predictive_state SET critical_streak=0,recovery_streak=0 '
                           'WHERE owner_user_id=%s', (self.scope[0],))
            self.events._audit(cursor, 'predictive_rules_updated', {'previous': previous, 'rules': values}, user_id)
            return values
