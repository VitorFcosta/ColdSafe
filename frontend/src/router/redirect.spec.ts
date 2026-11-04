import { expect, it } from 'vitest'
import { safeInternalRedirect } from './redirect'

it.each([undefined, [], 'https://evil.example', '//evil.example', '/\\evil.example', '/login?redirect=/login', '/\n/evil'])('recusa destino de acesso inseguro %s', (value) => {
  expect(safeInternalRedirect(value)).toBe('/dashboard')
})
it('preserva caminho, parâmetros e fragmento internos', () => {
  expect(safeInternalRedirect('/training?dataset=dataset-1&job=job-1#resultado')).toBe('/training?dataset=dataset-1&job=job-1#resultado')
})
