import { nextTick } from 'vue'

type Link = Readonly<{ to: string; label: string }>
type Area = Link & Readonly<{ key: string; adminOnly?: boolean; links?: readonly Link[] }>
export const areas: readonly Area[] = [
  { key: 'monitoring', to: '/dashboard', label: 'Monitoramento', links: [
    { to: '/dashboard', label: 'Visão geral' }, { to: '/insights', label: 'Saúde e previsões' }, { to: '/digital-twin', label: 'Gêmeo digital' },
  ] },
  { key: 'manage', to: '/manage', label: 'Ambientes e dispositivos' },
  { key: 'data', to: '/laboratory', label: 'Dados e modelos', adminOnly: true, links: [
    { to: '/laboratory', label: 'Dados sintéticos' }, { to: '/training', label: 'Treinamento de modelos' },
  ] },
  { key: 'messaging', to: '/messaging', label: 'Filas e mensagens', adminOnly: true },
  { key: 'assistant', to: '/assistant', label: 'Assistente' },
]
export async function focusPageHeading() {
  await nextTick()
  document.querySelector<HTMLElement>('main h1')?.focus()
}
