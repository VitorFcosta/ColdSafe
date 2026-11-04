import { spawn } from 'node:child_process'
import { mkdtemp, readFile, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'
import assert from 'node:assert/strict'
const here = dirname(fileURLToPath(import.meta.url))
const base = process.env.RD02_BASE_URL ?? 'http://127.0.0.1:4175/experiments/rd02/'
const output = resolve(process.env.RD02_OUTPUT ?? join(here, '../../../docs/redesign/assets/rd-09'))
const profile = await mkdtemp(join(tmpdir(), 'coldsafe-rd09-cdp-'))
const proc = spawn(chromium.executablePath(), ['--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check', 'about:blank'], { stdio: 'ignore' })
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
let socket
try {
  let version
  for (let i=0;i<40;i++) {
    try {
      const port = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]
      version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json()
      break
    } catch { await delay(150) }
  }
  assert.ok(version)
  socket = new WebSocket(version.webSocketDebuggerUrl)
  await new Promise(resolve => socket.addEventListener('open', resolve, {once:true}))
  let id=0
  const pending=new Map()
  socket.addEventListener('message',event=>{ const message=JSON.parse(event.data); if(pending.has(message.id)) { const {resolve,reject}=pending.get(message.id); pending.delete(message.id); message.error?reject(message.error):resolve(message.result) } })
  const rpc=(method,params={},sessionId)=>new Promise((resolve,reject)=>{ const key=++id; pending.set(key,{resolve,reject}); socket.send(JSON.stringify({id:key,method,params,...(sessionId?{sessionId}:{})})) })
  const {targetId}=await rpc('Target.createTarget',{url:base})
  const {sessionId}=await rpc('Target.attachToTarget',{targetId,flatten:true})
  const evaluate=async expression=>{ const r=await rpc('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true},sessionId); if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails)); return r.result.value }
  await delay(1500)
  assert.ok(await evaluate('Boolean(window.rd02)'), 'Laboratório deve carregar antes do ensaio')
  const active=await evaluate('({time:Date.now(),hidden:document.hidden,state:window.rd02.snapshot(),probe:window.rd02.probe.snapshot()})')
  await rpc('Target.createTarget',{url:'about:blank'})
  await delay(500)
  const hiddenBefore=await evaluate('({time:Date.now(),hidden:document.hidden,state:window.rd02.snapshot(),probe:window.rd02.probe.snapshot()})')
  await delay(1500)
  const hiddenAfter=await evaluate('({time:Date.now(),hidden:document.hidden,state:window.rd02.snapshot(),probe:window.rd02.probe.snapshot()})')
  await rpc('Target.activateTarget',{targetId})
  await delay(400)
  const resumed=await evaluate('({time:Date.now(),hidden:document.hidden,state:window.rd02.snapshot(),probe:window.rd02.probe.snapshot()})')
  const report={date:new Date().toISOString(),protocol:'Chromium nativo via CDP, perfil temporário, sem Playwright/Emulation de foco; troca real para outra aba. Mesmo build otimizado da medição RD-09.',browser:version.Browser,active,hiddenBefore,hiddenAfter,resumed}
  report.criteria={active:active.hidden===false&&active.state.animating,actuallyHidden:hiddenBefore.hidden&&hiddenAfter.hidden,stopped:hiddenBefore.state.animating===false&&hiddenAfter.state.animating===false,zeroRenders:hiddenAfter.probe.totalRenders===hiddenBefore.probe.totalRenders,resumed:resumed.hidden===false&&resumed.state.animating}
  report.passed=Object.values(report.criteria).every(Boolean)
  await writeFile(join(output, 'visibility-native.json'),JSON.stringify(report,null,2))
  console.log(JSON.stringify(report,null,2))
  assert.ok(report.passed,'Visibilidade real deve passar')
} finally { socket?.close(); proc.kill() }
