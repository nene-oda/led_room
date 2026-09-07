import { useCallback, useState, type ReactNode } from 'react'

import { Button } from './Button'
import { Card } from './Card'
import { Modal } from './Modal'

export interface ModalCardProps {
  /** Titulo de la tarjeta y del dialogo: son la misma cosa vista dos veces. */
  readonly title: string
  /** Dato de estado que se lee sin abrir nada: cuantos hay, cual esta puesto. */
  readonly summary: string
  /** Texto visible del boton. Corto: la tarjeta ya da el contexto. */
  readonly actionText: string
  /**
   * Nombre accesible del boton.
   *
   * Las cinco tarjetas dicen «Gestionar»; quien navega por botones necesita
   * saber cual es cual sin leer el titulo de al lado.
   */
  readonly actionLabel: string
  /** Ver `Modal`: se apaga cuando dentro hay un borrador sin guardar. */
  readonly dismissOnBackdrop?: boolean | undefined
  /** Se llama al cerrar. Sirve para descartar lo que el dialogo dejo a medias. */
  readonly onClose?: (() => void) | undefined
  /** Contenido del dialogo. **No se monta** mientras esta cerrado. */
  readonly children: ReactNode
}

/**
 * Tarjeta cuya tarea secundaria se abre en un dialogo.
 *
 * Existe porque las cuatro bibliotecas —dispositivos, efectos, escenas y
 * perfiles— comparten exactamente el mismo gesto: un resumen que se lee, un
 * boton que abre y un modal que presenta. Escribirlo cuatro veces habria
 * dejado cuatro estados `open`, cuatro botones y cuatro formas de cerrar.
 *
 * Sigue sin saber nada del dominio: recibe textos e hijos. Lo que va dentro lo
 * decide quien la usa.
 */
export function ModalCard({
  title,
  summary,
  actionText,
  actionLabel,
  dismissOnBackdrop,
  onClose,
  children,
}: ModalCardProps) {
  const [open, setOpen] = useState(false)

  const close = useCallback(() => {
    setOpen(false)
    onClose?.()
  }, [onClose])

  return (
    <Card title={title} summary={summary}>
      <Button
        ariaLabel={actionLabel}
        onClick={() => {
          setOpen(true)
        }}
      >
        {actionText}
      </Button>

      {/* Montado solo al abrir: es lo que hace que el editor de dentro empiece
          limpio en vez de recordar el borrador de la vez anterior. */}
      {open && (
        <Modal title={title} dismissOnBackdrop={dismissOnBackdrop} onClose={close}>
          {children}
        </Modal>
      )}
    </Card>
  )
}
