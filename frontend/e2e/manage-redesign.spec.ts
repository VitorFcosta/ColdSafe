import { mkdir, writeFile } from 'node:fs/promises'
import { expect, test, type Page } from '@playwright/test'
import { mockDashboardAccount } from './monitoring-api'

const environmentId = '00000000-0000-4000-8000-000000000001'
const secondEnvironmentId = '00000000-0000-4000-8000-000000000002'
const deviceId = '00000000-0000-4000-8000-000000000101'
const environmentName = 'Laboratório refrigerado'
const deviceName = 'Ventilador 01'
const catalog = { id:deviceId, environment_id:environmentId, name:deviceName, mqtt_device_id:'esp32-lab-01', is_active:true }

async function management(page:Page, options:{viewer?:boolean; empty?:boolean; fail?:'devices'|'rules'}={}) {
  await mockDashboardAccount(page)
  if(options.viewer) await page.route('**/api/v1/auth/me',route=>route.fulfill({json:{success:true,data:{user_id:'viewer',email:'viewer@example.invalid',role:'viewer'}}}))
  let active=true, failed=Boolean(options.fail), reads=0
  const writes:{method:string;body:unknown}[]=[]
  await page.route('**/api/v1/environments',route=>route.fulfill({json:{success:true,data:options.empty?[]:[{id:environmentId,name:environmentName},{id:secondEnvironmentId,name:'Estoque'}]}}))
  await page.route('**/api/v1/environments/*/devices',route=>{
    reads++
    if(failed&&options.fail==='devices') return route.fulfill({status:503,json:{success:false,error:{message:'Falha controlada na consulta de dispositivos.'}}})
    const second=route.request().url().includes(secondEnvironmentId)
    return route.fulfill({json:{success:true,data:second?[]:[{...catalog,is_active:active}]}})
  })
  await page.route('**/api/v1/environments/*/rules',route=>{
    if(failed&&options.fail==='rules') return route.fulfill({status:503,json:{success:false,error:{message:'Falha controlada na consulta de limites.'}}})
    if(route.request().method()==='PUT') writes.push({method:'PUT',body:route.request().postDataJSON()})
    return route.fulfill({json:{success:true,data:{min_c:2,max_c:8,attention_margin_c:.5}}})
  })
  await page.route('**/api/v1/devices/*',route=>{
    writes.push({method:route.request().method(),body:route.request().postData()})
    if(route.request().method()==='DELETE')active=false
    return route.fulfill({json:{success:true,data:{...catalog,is_active:active}}})
  })
  return {writes,reads:()=>reads,recover:()=>{failed=false}}
}

const confirmation=(page:Page)=>page.getByRole('dialog',{name:`Desativar ${deviceName}?`,exact:true})
const evidence=new URL('../../.impeccable/review/rd-11/',import.meta.url)

for(const width of [1440,390]) {
  test(`M-06 e confirmação segura de desativação (${width}px)`,async({page})=>{
    await page.setViewportSize({width,height:1024})
    await page.emulateMedia({reducedMotion:'reduce'})
    const mock=await management(page)
    // O par operacional recebido pela URL não escolhe o ambiente da Gestão.
    await page.goto(`/manage?environment=${secondEnvironmentId}&device=${deviceId}`)
    const devicesHeading=page.getByRole('heading',{name:`Dispositivos de ${environmentName}`,exact:true})
    await expect(devicesHeading).toBeVisible()
    await expect(page.getByRole('button',{name:'Adicionar dispositivo',exact:true})).toBeEnabled()
    await expect(page.getByLabel('Identificador MQTT')).toHaveCount(0)
    const environmentPanel=page.getByRole('region',{name:'Ambientes',exact:true})
    const devicesPanel=page.getByRole('region',{name:`Dispositivos de ${environmentName}`,exact:true})
    const rulesPanel=page.getByRole('region',{name:`Limites de temperatura de ${environmentName}`,exact:true})
    const boxes=await Promise.all([environmentPanel.boundingBox(),devicesPanel.boundingBox(),rulesPanel.boundingBox()])
    if(width===1440)expect(boxes[0]!.x).toBeLessThan(boxes[1]!.x)
    else {expect(boxes[0]!.y).toBeLessThan(boxes[1]!.y);expect(boxes[1]!.y).toBeLessThan(boxes[2]!.y)}
    await mkdir(evidence,{recursive:true})
    await page.screenshot({path:new URL(width===1440?'desktop.png':'mobile.png',evidence).pathname,fullPage:true})
    await page.screenshot({path:new URL(width===1440?'desktop-viewport.png':'mobile-viewport.png',evidence).pathname})
    if(width===1440)await page.screenshot({path:new URL('hero-repro.png',evidence).pathname})
    const trigger=page.getByRole('button',{name:`Desativar dispositivo ${deviceName}`,exact:true})
    await trigger.focus();await page.keyboard.press('Enter')
    const dialog=confirmation(page), cancel=dialog.getByRole('button',{name:'Cancelar',exact:true})
    await expect(cancel).toBeFocused()
    await expect(dialog).toContainText(catalog.mqtt_device_id)
    await expect(dialog).toContainText('não exclui o cadastro nem interrompe fisicamente')
    expect(await dialog.evaluate(el=>el.matches(':modal'))).toBe(true)
    await page.locator('[data-test="open-environment-form"]').evaluate(el=>(el as HTMLElement).focus())
    await expect(cancel).toBeFocused()
    await page.keyboard.press('Shift+Tab');expect(await dialog.evaluate(el=>el.contains(document.activeElement)||document.activeElement===document.body)).toBe(true)
    await page.keyboard.press('Tab');await expect(cancel).toBeFocused()
    await page.screenshot({path:new URL(width===1440?'dialog-desktop.png':'dialog-mobile.png',evidence).pathname})
    await page.keyboard.press('Escape');await expect(dialog).not.toBeVisible();await expect(trigger).toBeFocused()
    expect(mock.writes).toEqual([])
    await trigger.click();await cancel.click();await expect(trigger).toBeFocused();expect(mock.writes).toEqual([])
    await trigger.click()
    if(width===390){
      await page.setViewportSize({width:320,height:812});await page.addStyleTag({content:'html {font-size:200% !important}'})
      await expect.poll(()=>page.evaluate(()=>getComputedStyle(document.documentElement).fontSize)).toBe('32px')
      await expect(cancel).toBeFocused()
      const layout=await dialog.evaluate(el=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,dialogWidth:el.getBoundingClientRect().width,dialogScrollWidth:el.scrollWidth,fontSize:getComputedStyle(document.documentElement).fontSize}))
      expect(layout.scrollWidth).toBe(320);expect(layout.dialogScrollWidth).toBeLessThanOrEqual(288)
      await writeFile(new URL('reflow-dialog.json',evidence),JSON.stringify(layout,null,2))
      await page.screenshot({path:new URL('dialog-320-text-200-title.png',evidence).pathname})
      await cancel.scrollIntoViewIfNeeded();await expect(cancel).toBeInViewport()
      await page.screenshot({path:new URL('dialog-320-text-200.png',evidence).pathname})
    }
    await dialog.getByRole('button',{name:'Desativar dispositivo',exact:true}).click()
    await expect(trigger).toHaveCount(0);await expect(devicesHeading).toBeFocused()
    expect(mock.writes.map(x=>x.method)).toEqual(['DELETE']);expect(mock.reads()).toBeGreaterThanOrEqual(2)
    await expect(devicesPanel).toContainText('Desativado')
  })
}

for(const empty of [true,false]) {
  test(`viewer consulta vazio sem convite à escrita (sem ambientes=${empty})`,async({page})=>{
    await page.setViewportSize({width:390,height:844})
    const mock=await management(page,{viewer:true,empty})
    await page.goto('/manage')
    if(!empty)await page.getByLabel('Ambiente',{exact:true}).selectOption(secondEnvironmentId)
    await expect(page.getByText(empty?'Nenhum ambiente cadastrado.':'Nenhum dispositivo cadastrado neste ambiente.',{exact:false})).toBeVisible()
    await expect(page.locator('main form')).toHaveCount(0)
    await expect(page.getByRole('button',{name:/Adicionar|Editar|Renomear|Desativar/})).toHaveCount(0)
    expect(mock.writes).toEqual([])
    await mkdir(evidence,{recursive:true})
    await page.screenshot({path:new URL(empty?'viewer-no-environments.png':'viewer-no-devices.png',evidence).pathname,fullPage:true})
  })
}

for(const fail of ['devices','rules'] as const) {
  test(`falha de ${fail} exige recuperação conjunta sem falso vazio`,async({page})=>{
    const mock=await management(page,{fail})
    await page.goto('/manage')
    await expect(page.getByText('A carga conjunta de dispositivos e limites não foi confirmada.',{exact:false})).toBeVisible()
    await expect(page.getByText('Nenhum dispositivo cadastrado neste ambiente.',{exact:false})).toHaveCount(0)
    await expect(page.getByLabel('Mínimo (°C)',{exact:true})).toHaveCount(0)
    const retry=page.getByRole('button',{name:'Consultar dispositivos e limites novamente',exact:true})
    await retry.focus();await page.keyboard.press('Enter');await expect(retry).toBeFocused()
    mock.recover();await page.getByRole('button',{name:'Consultar dispositivos e limites novamente',exact:true}).click()
    await expect(page.getByText(deviceName,{exact:true})).toBeVisible()
    await expect(page.getByLabel('Mínimo (°C)',{exact:true})).toHaveValue('2')
    await expect(page.getByRole('heading',{name:`Dispositivos de ${environmentName}`,exact:true})).toBeFocused()
    expect(mock.writes).toEqual([])
  })
}

test('Monitoramento revalida o catálogo após desativar, sem reutilizar dispositivo ativo anterior',async({page})=>{
  await management(page)
  await page.goto(`/dashboard?environment=${environmentId}&device=${deviceId}`)
  await expect(page.getByRole('combobox',{name:'Dispositivo',exact:true})).toHaveValue(deviceId)
  await page.getByRole('navigation',{name:'Navegação principal',exact:true}).getByRole('link',{name:'Ambientes e dispositivos',exact:true}).click()
  await expect(page).toHaveURL('/manage')
  await page.getByRole('button',{name:`Desativar dispositivo ${deviceName}`,exact:true}).click()
  await confirmation(page).getByRole('button',{name:'Desativar dispositivo',exact:true}).click()
  await expect(page.getByRole('button',{name:`Desativar dispositivo ${deviceName}`,exact:true})).toHaveCount(0)
  await page.getByRole('navigation',{name:'Navegação principal',exact:true}).getByRole('link',{name:'Monitoramento',exact:true}).click()
  await expect(page.getByRole('combobox',{name:'Dispositivo',exact:true})).toHaveValue('')
  expect(new URL(page.url()).searchParams.has('device')).toBe(false)
})
