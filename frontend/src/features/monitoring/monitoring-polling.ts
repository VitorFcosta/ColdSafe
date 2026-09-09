export const monitoringPollingIntervalMs = 5_000

/**
 * Atualiza o dashboard assim que ele aparece e mantém a consulta periódica.
 * A função retornada deve ser chamada no desmontar da tela para não deixar
 * requisições em segundo plano após a navegação.
 */
export function startMonitoringPolling(
  refresh: () => void | Promise<void>,
): () => void {
  void refresh()

  const intervalId = setInterval(() => {
    void refresh()
  }, monitoringPollingIntervalMs)

  return () => clearInterval(intervalId)
}
