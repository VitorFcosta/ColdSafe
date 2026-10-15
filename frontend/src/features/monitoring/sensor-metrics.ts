export const sensorMetrics = [
  { key: 'temperature_c', label: 'Temperatura ambiente', unit: '°C' },
  { key: 'humidity_percent', label: 'Umidade', unit: '%' },
  { key: 'light_percent', label: 'Luminosidade', unit: '%' },
  { key: 'vibration_rms_mm_s', label: 'Vibração RMS', unit: 'mm/s' },
  { key: 'motor_current_a', label: 'Corrente do motor', unit: 'A' },
  { key: 'motor_temperature_c', label: 'Temperatura do motor', unit: '°C' },
] as const

export type SensorMetricKey = (typeof sensorMetrics)[number]['key']

export const sensorMetricByKey = Object.fromEntries(sensorMetrics.map((metric) => [metric.key, metric])) as Readonly<
  Record<SensorMetricKey, (typeof sensorMetrics)[number]>
>
