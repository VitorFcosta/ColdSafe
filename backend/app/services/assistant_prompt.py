"""Compact owner-scoped facts; the LLM still generates the answer."""
import json
import re
import unicodedata

from backend.app.services.assistant_context import number

LABELS = {
    'ambient_temperature': 'temperatura ambiente', 'humidity': 'umidade',
    'light': 'luz', 'motor_temperature': 'temperatura do motor',
    'vibration': 'vibração', 'motor_current': 'corrente do motor',
}
UNITS = {'degC': '°C', 'percent': '%', 'mm/s': 'mm/s', 'A': 'A'}
STATES = {'fresh': 'RECENTE', 'stale': 'ANTIGA, NÃO RECENTE', 'no_data': 'SEM LEITURA'}
BLOCKS = frozenset(('equipment', 'model', 'alerts', 'architecture'))


def _value(value):
    finite = number(value)
    return f'{finite:g}' if finite is not None else 'indisponível'


def _sensor(label, reading):
    value, unit = reading
    unit = UNITS.get(unit, json.dumps(unit, ensure_ascii=False, allow_nan=False))
    return f'{label} {_value(value)}{unit}'


def _topics(question):
    # shortcut: tópicos por palavras; ampliar se perguntas reais perderem fatos.
    text = ''.join(c for c in unicodedata.normalize('NFD', question or '')
                   if not unicodedata.combining(c)).casefold()
    patterns = {
        'architecture': r'\b(?:arquitet|fluxo|armazen|tecnolog|mqtt|rabbitmq|influxdb|postgres|vue|ollama)',
        'alerts': r'\balert',
        'model': r'\b(?:mae|rmse|metric|modelo|trein)|\berro(?: medio)?(?: absoluto)? de teste',
    }
    selected = {name for name, pattern in patterns.items() if re.search(pattern, text)}
    target = r'(?:saude|rul|vida util(?: restante)?)'
    bound_metric = rf'\b(?:mae|rmse|metricas?|erro(?: medio)?(?: absoluto)?)(?: de teste)? (?:d[aeo] )?{target}(?: e (?:d[aeo] )?{target})?'
    equipment_text = re.sub(bound_metric, '', text)
    if re.search(r'\b(?:equip|maquin|ventil|estado|leitur|saude|rul|vida util|sensor|temperatur|umidade|vibra|corrente|luz|previs|atual|recent)', equipment_text):
        selected = selected | {'equipment'}
    return selected or BLOCKS, text


def _minimum_fields(text):
    if re.search(r'\b(?:compar|estado|leitur|sensor)', text):
        return set()
    fields = {field for field, pattern in (('health', r'\bmenor saude\b'),
                                          ('rul_h', r'\bmenor (?:rul|vida util)\b'))
              if re.search(pattern, text)}
    if len(fields) == 1 and 'saude' in text and re.search(r'\brul\b|vida util', text):
        return set()
    return fields


def _equipment_lines(equipment, fields, details):
    available = [item for item in equipment if item['reading'] == 'fresh' and item['prediction'] == 'available']
    values = {key: [number(item[key]) for item in available] for key in ('health', 'rul_h')}
    minima = {key: min((v for v in values if v is not None), default=None) for key, values in values.items()}
    matches = [item for item in available if any(number(item[key]) is not None
               and number(item[key]) == minima[key] for key in fields)]
    items = matches if fields and matches else equipment
    labels = {'health': 'menor saúde entre os listados', 'rul_h': 'menor RUL entre os listados'}
    lines = []
    for item in items:
        recent = item['reading'] == 'fresh'
        current = recent and item['prediction'] == 'available'
        values = (f"saúde {_value(item['health'])} pontos/100; RUL {_value(item['rul_h'])} horas"
                  if current else 'saúde e RUL atuais indisponíveis')
        marks = [label for key, label in labels.items() if current and number(item[key]) is not None
                 and number(item[key]) == minima[key]]
        name = json.dumps(item['device'], ensure_ascii=False, allow_nan=False)
        lines.append(f"Equipamento {name}: {STATES.get(item['reading'], 'INDISPONÍVEL')}; {values}"
                     + ('; ' + '; '.join(marks) if marks else '') + '.')
        if details and recent and item['sensors']:
            sensors = [_sensor(label, item['sensors'][key])
                       for key, label in LABELS.items() if key in item['sensors']]
            lines.append('Leituras dos sensores (medições, não previsões): ' + '; '.join(sensors) + '.')
    lines.extend(labels[key].capitalize() + ': indisponível.' for key in fields if minima[key] is None)
    return lines, len(items)


def format_summary(context: dict, question: str | None = None) -> str:
    required = ('scope', 'equipment', 'alerts', 'model', 'architecture')
    if not isinstance(context, dict) or not all(key in context for key in required):
        return 'Resumo indisponível.'
    scope = context['scope']
    counts = ('devices', 'stale_readings', 'missing_readings', 'fresh_predictions')
    if not isinstance(scope, dict) or not all(key in scope for key in counts):
        return 'Resumo indisponível.'
    selected, text = _topics(question)
    details = bool(re.search(r'\b(?:quant|total|numero|outro|demais|cada|todos|ambos|maior|melhor|'
                             r'estado|leitur|sensor|temperatur|umidade|vibra|corrente|luz)', text))
    details = details or bool(question and any(item['device'].casefold() in question.casefold()
                                               for item in context['equipment']))
    fields = _minimum_fields(text) if 'equipment' in selected and not details else set()
    minimum = selected != BLOCKS and bool(re.search(r'\b(?:menor|pior)\b', text))
    minimum = minimum and not details
    lines = []
    if 'equipment' in selected:
        if not minimum:
            lines.append(f"Conta: {_value(scope['devices'])} equipamentos. "
                         f"Leituras antigas: {_value(scope['stale_readings'])}; "
                         f"ausentes: {_value(scope['missing_readings'])}; "
                         f"previsões atuais: {_value(scope['fresh_predictions'])}.")
        if number(scope['devices']) == 0:
            lines.append('Conta sem equipamentos, leituras e previsões.')
        equipment, listed = _equipment_lines(context['equipment'], fields,
                                             not minimum and (details or selected == BLOCKS))
        lines.extend(equipment)
        count = number(scope['devices'])
        if scope.get('truncated') or (count is not None and count > listed):
            if not fields:
                lines.append('Amostra: menor saúde e menor RUL; sensores somente do primeiro equipamento.')
            lines.append('Amostra parcial. Outros nomes e valores não listados são desconhecidos.')
    if 'alerts' in selected:
        alerts = context['alerts']
        lines.append(f"Alertas ativos: preditivo {_value(alerts['predictive'])}, "
                     f"temperatura {_value(alerts['temperature'])}. Causa e limiares individuais não informados.")
        lines.append('Alerta preditivo: aviso baseado em previsões sintéticas; não comprova falha física.')
    if 'model' in selected and context['model']:
        model = context['model']
        version = json.dumps(model['version'], ensure_ascii=False, allow_nan=False)
        lines.append(f"Modelo {version}. MAE de teste (erro, não previsão atual): "
                     f"saúde {_value(model['test_mae']['health'])} pontos na escala 0–100; "
                     f"RUL {_value(model['test_mae']['rul'])} horas.")
        lines.append('MAE não corrige previsões: não se soma nem subtrai da saúde/RUL atual; '
                     'não define intervalo de erro individual.')
    elif 'model' in selected:
        lines.append('Sem modelo ativo e sem métricas.')
    if 'architecture' in selected:
        lines.append('Arquitetura: ' + context['architecture'])
    lines.append('Previsões sintéticas sem calibração física; erros de teste não garantem erro individual.')
    return '\n'.join(lines)
