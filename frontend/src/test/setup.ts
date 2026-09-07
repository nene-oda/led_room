import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

import { installDialogPolyfill } from './dialogPolyfill'

// jsdom no implementa `<dialog>`: sin esto, abrir un modal falla antes de
// llegar a la primera comprobacion. Ver `dialogPolyfill.ts` para el alcance
// exacto de la emulacion y para lo que deja fuera a proposito.
installDialogPolyfill()

afterEach(() => {
  cleanup()
})
