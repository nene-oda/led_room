import { Home } from './pages/Home'
import { LightStateProvider } from './state/LightStateProvider'

/**
 * Raiz de la aplicacion: proveedor + pantalla.
 *
 * El proveedor esta aqui y no dentro de `Home` para que sea evidente que hay
 * **uno solo**: una unica conexion WebSocket y un unico estado compartido para
 * toda la aplicacion. Cuando llegue una segunda pantalla (Fases 6-7), el router
 * se montara debajo de este proveedor, no encima.
 */
export function App() {
  return (
    <LightStateProvider>
      <Home />
    </LightStateProvider>
  )
}
