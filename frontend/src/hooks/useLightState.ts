import { useContext } from 'react'

import { LightStateContext, type LightControls, type LightView } from '../state/lightStateContext'

function useLightContext() {
  const value = useContext(LightStateContext)
  if (value === null) {
    throw new Error('useLightState debe usarse dentro de <LightStateProvider>')
  }
  return value
}

/**
 * Lo que la pantalla muestra. Solo lectura.
 *
 * Esta separado de `useLightControls` a proposito: un componente que solo pinta
 * no deberia poder mutar el estado del dispositivo por accidente, y uno que
 * solo actua no necesita volver a renderizarse con cada evento del servidor.
 */
export function useLightState(): LightView {
  return useLightContext().view
}

/** Acciones del usuario. Su identidad es estable entre renders. */
export function useLightControls(): LightControls {
  return useLightContext().controls
}
