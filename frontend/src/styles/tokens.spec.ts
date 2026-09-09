import { readFile } from 'node:fs/promises'
import { describe, expect, it } from 'vitest'

const tokensPath = new URL('./tokens.css', import.meta.url)

describe('tokens visuais do ColdSafe', () => {
  it('define os papéis necessários para os estados operacionais aprovados', async () => {
    const tokens = await readFile(tokensPath, 'utf8')

    expect(tokens).toContain('--cs-color-canvas')
    expect(tokens).toContain('--cs-color-ink')
    expect(tokens).toContain('--cs-color-status-normal')
    expect(tokens).toContain('--cs-color-status-attention')
    expect(tokens).toContain('--cs-color-status-critical')
    expect(tokens).toContain('--cs-color-status-stale')
    expect(tokens).toContain('--cs-focus-ring')
  })
})
