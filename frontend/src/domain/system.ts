/**
 * Lo que el SERVIDOR puede hacer, que no es lo mismo que lo que puede hacer el
 * dispositivo.
 *
 * `DeviceCapabilities` responde «¿esta tira admite color?». Esto responde
 * «¿este backend tiene siquiera una radio con la que buscar tiras?». Son dos
 * preguntas distintas y por eso son dos tipos distintos: el backend puede estar
 * corriendo con el adaptador nulo —sin radio— y en ese caso no hay ningun
 * dispositivo que descubrir, tenga la tira las capacidades que tenga.
 *
 * Es un hecho **conocido antes de escanear**, y ahi esta su valor: permite
 * decir la verdad antes de que el usuario pulse un boton que no puede
 * funcionar, en vez de explicarselo despues con una lista vacia.
 */
export interface SystemInfo {
  /**
   * Familia del adaptador con la que arranco el servidor (`null`, `lotus_lantern_ble`…).
   *
   * Informativo: **no decide nada de la UI**, igual que `Device.adapterType`.
   * Solo se enseña para que quien administre el servidor sepa que cambiar.
   * `null` si el servidor no lo publica.
   */
  readonly adapterType: string | null
  /**
   * `false` significa «este servidor no tiene radio y nunca encontrara nada».
   *
   * Es lo unico que decide si se ofrece buscar dispositivos.
   */
  readonly supportsDiscovery: boolean
  /** Techo real del escaneo, en segundos. Es lo que permite dibujar progreso. */
  readonly scanTimeoutSeconds: number
}
