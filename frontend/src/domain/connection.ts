/**
 * Vocabulario de conectividad, compartido por el transporte y la UI.
 *
 * Vive en `domain/` y no en `api/` por una razon concreta: `components/**` no
 * puede importar `api/**` (regla de ESLint), y `DeviceStatus` necesita nombrar
 * estos estados. El transporte los produce; la UI los pinta.
 *
 * **Las tres señales son independientes y no se colapsan en un punto verde.**
 * "Backend inalcanzable", "WebSocket caido" y "dispositivo BLE desconectado"
 * son tres fallos distintos con tres soluciones distintas, y mezclarlos deja al
 * usuario sin saber que arreglar.
 */

/** Estado del socket de tiempo real. `reconnecting` es visible a proposito. */
export type RealtimeStatus = 'connecting' | 'open' | 'reconnecting' | 'closed'

/** Alcanzabilidad del backend por HTTP, deducida de la ultima peticion REST. */
export type BackendStatus = 'checking' | 'reachable' | 'unreachable'
