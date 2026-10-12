import { expect, test } from '@playwright/test'

import { mockDashboardAccount } from './monitoring-api'

test('gestão mostra listas primeiro e mantém contexto e foco no celular e desktop', async ({ page }) => {
  await mockDashboardAccount(page)
  const longName = 'Câmara de conservação de vacinas do laboratório central'.repeat(2)
  const writes: string[] = []
  await page.route('**/api/v1/environments', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: [
      { id: 'lab-refrigerado', name: longName }, { id: 'estoque', name: 'Estoque' },
    ] }),
  }))
  await page.route('**/api/v1/environments/*/devices', (route) => {
    if (route.request().method() !== 'GET') writes.push(route.request().method())
    const isStock = route.request().url().includes('/estoque/')
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: isStock ? [] : [
      { id: 'sensor-1', environment_id: 'lab-refrigerado', name: 'Sensor reserva', mqtt_device_id: 'esp32-1', is_active: false },
      { id: 'sensor-2', environment_id: 'lab-refrigerado', name: 'Sensor principal', mqtt_device_id: 'esp32-2', is_active: true },
    ] }) })
  })
  await page.route('**/api/v1/environments/*/rules', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ success: true, data: { min_c: 2, max_c: 8, attention_margin_c: 1 } }),
  }))
  await page.route('**/api/v1/devices/*', (route) => {
    if (route.request().method() !== 'GET') writes.push(route.request().method())
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: {} }) })
  })

  await page.setViewportSize({ width: 320, height: 844 })
  await page.goto('/manage')
  await expect(page.getByRole('heading', { name: `Dispositivos de ${longName}` })).toBeVisible()
  await expect(page.getByRole('heading', { name: `Limites de temperatura de ${longName}` })).toBeVisible()
  await expect(page.getByText('Sensor reserva')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Desativar dispositivo Sensor reserva' })).toHaveCount(0)
  await expect(page.getByLabel('Nome do novo ambiente')).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)

  await page.getByRole('button', { name: `Editar ambiente ${longName}` }).click()
  await page.getByRole('textbox', { name: `Nome do ambiente ${longName}` }).fill('Rascunho')
  await page.getByRole('button', { name: `Cancelar edição do ambiente ${longName}` }).click()
  await page.getByRole('button', { name: 'Editar dispositivo Sensor principal' }).click()
  await page.getByRole('textbox', { name: 'Nome do dispositivo Sensor principal' }).fill('Rascunho')
  await page.getByRole('button', { name: 'Cancelar edição do dispositivo Sensor principal' }).click()
  expect(writes).toEqual([])

  const openEnvironment = page.getByRole('button', { name: 'Adicionar ambiente' })
  await openEnvironment.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByLabel('Nome do novo ambiente')).toBeFocused()
  await page.getByLabel('Nome do novo ambiente').fill('Rascunho')
  await page.getByRole('button', { name: 'Cancelar inclusão de ambiente' }).click()
  await expect(openEnvironment).toBeFocused()

  await page.getByRole('button', { name: 'Estoque', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Dispositivos de Estoque' })).toBeVisible()
  await expect(page.getByText('Nenhum dispositivo cadastrado neste ambiente')).toBeVisible()
  const openDevice = page.getByRole('button', { name: 'Adicionar dispositivo' })
  await openDevice.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByLabel('Nome do dispositivo')).toBeFocused()
  await expect(page.getByRole('heading', { name: 'Adicionar dispositivo em Estoque' })).toBeVisible()
  await page.getByLabel('Nome do dispositivo').fill('Rascunho')
  await page.getByRole('button', { name: 'Cancelar inclusão de dispositivo' }).click()
  await expect(openDevice).toBeFocused()

  await page.setViewportSize({ width: 1280, height: 800 })
  await page.getByRole('button', { name: longName, exact: true }).click()
  await expect(page.getByRole('heading', { name: `Limites de temperatura de ${longName}` })).toBeVisible()
  page.once('dialog', (dialog) => dialog.dismiss())
  await page.getByRole('button', { name: 'Desativar dispositivo Sensor principal' }).click()
  expect(writes).toEqual([])
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Desativar dispositivo Sensor principal' }).focus()
  await page.keyboard.press('Enter')
  await expect.poll(() => writes).toEqual(['DELETE'])
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1280)
})

test('limites mostram erros no campo, preservam rascunho e salvam apenas no ambiente selecionado', async ({ page }) => {
  await mockDashboardAccount(page)
  const writes: { environment: string; margin: number }[] = []
  await page.route('**/api/v1/environments', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: [
      { id: 'lab-refrigerado', name: 'Laboratório Refrigerado' }, { id: 'estoque', name: 'Estoque' },
    ] }),
  }))
  await page.route('**/api/v1/environments/estoque/devices', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: [] }),
  }))
  await page.route('**/api/v1/environments/*/rules', (route) => {
    const environment = route.request().url().includes('/estoque/') ? 'estoque' : 'lab-refrigerado'
    if (route.request().method() === 'PUT') {
      const body = route.request().postDataJSON() as { min_c: number; max_c: number; attention_margin_c: number }
      writes.push({ environment, margin: body.attention_margin_c })
      if (writes.length === 1) return route.fulfill({
        status: 503, contentType: 'application/json', body: JSON.stringify({ success: false, error: { message: 'API indisponível.' } }),
      })
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: body }) })
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: {
      min_c: environment === 'estoque' ? 0 : 2, max_c: environment === 'estoque' ? 10 : 8, attention_margin_c: 1,
    } }) })
  })

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/manage')
  const minimum = page.getByLabel('Mínimo (°C)')
  const maximum = page.getByLabel('Máximo (°C)')
  const margin = page.getByLabel('Margem de atenção (°C)')
  const save = page.getByRole('button', { name: 'Salvar limites' })
  await expect(minimum).toHaveValue('2')
  await minimum.fill('10')
  await maximum.fill('9')
  await save.click()
  await expect(minimum).toBeFocused()
  await expect(page.locator('#min-c-error')).toContainText('menor que o máximo')
  await expect(page.locator('#max-c-error')).toContainText('maior que o mínimo')
  expect(writes).toEqual([])

  await minimum.fill('2')
  await maximum.fill('8')
  await margin.fill('4')
  await save.click()
  await expect(margin).toBeFocused()
  await expect(page.locator('#margin-c-error')).toContainText('menor que metade')
  await expect(margin).toHaveValue('4')
  expect(writes).toEqual([])

  await margin.fill('1')
  await save.click()
  await expect(page.locator('#rules-save-error')).toContainText('API indisponível.')
  await expect(margin).toHaveValue('1')
  await expect(page.getByText('Limites de Laboratório Refrigerado salvos.')).toHaveCount(0)
  await save.click()
  await expect(page.getByText('Limites de Laboratório Refrigerado salvos.')).toBeVisible()
  expect(writes).toEqual([{ environment: 'lab-refrigerado', margin: 1 }, { environment: 'lab-refrigerado', margin: 1 }])

  await page.getByRole('button', { name: 'Estoque', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Limites de temperatura de Estoque' })).toBeVisible()
  await expect(minimum).toHaveValue('0')
  await margin.fill('2')
  await save.click()
  await expect(page.getByText('Limites de Estoque salvos.')).toBeVisible()
  expect(writes.at(-1)).toEqual({ environment: 'estoque', margin: 2 })
})
