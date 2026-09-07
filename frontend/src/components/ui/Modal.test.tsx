import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Modal } from './Modal'

/**
 * El dialogo generico, probado por lo que hace y no por como esta hecho.
 *
 * Dos avisos sobre el entorno, para que nadie lea de mas en estas pruebas:
 *
 *   - jsdom **no implementa `<dialog>`**; hay un doble de plataforma en
 *     `src/test/dialogPolyfill.ts`. Lo que emula (abrir, Escape, foco inicial)
 *     es del navegador, no de este componente.
 *   - la **inercia del fondo** —que el tabulador no salga del dialogo— la da la
 *     capa superior, y ningun entorno sin motor de layout la puede ejercitar.
 *     Lo que si se puede comprobar, y es la regresion real que importa, es que
 *     se abre con `showModal()` y no con `show()`: con `show()` el dialogo se
 *     dibuja igual pero el fondo sigue siendo enfocable y accesible.
 */

/** Lo minimo que hace falta para probar un modal: quien lo abre y algo dentro. */
function Harness({ dismissOnBackdrop }: { readonly dismissOnBackdrop?: boolean | undefined }) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setOpen(true)
        }}
      >
        Abrir
      </button>

      {open && (
        <Modal
          title="Escenas"
          dismissOnBackdrop={dismissOnBackdrop}
          onClose={() => {
            setOpen(false)
          }}
        >
          <label>
            Nombre
            <input type="text" />
          </label>
          <button type="button">Guardar</button>
        </Modal>
      )}
    </>
  )
}

/** Abre el modal como lo abre un navegador: el clic enfoca antes el boton. */
function open(): HTMLElement {
  const trigger = screen.getByRole('button', { name: 'Abrir' })
  trigger.focus()
  fireEvent.click(trigger)
  return trigger
}

function pressEscape(): void {
  fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Modal', () => {
  it('no monta el contenido mientras esta cerrado', () => {
    render(<Harness />)

    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.queryByText('Guardar')).toBeNull()

    open()

    expect(screen.getByRole('dialog', { name: 'Escenas' })).toBeDefined()
    expect(screen.getByRole('button', { name: 'Guardar' })).toBeDefined()
  })

  it('cada apertura estrena el contenido, en vez de recordar lo escrito', () => {
    render(<Harness />)

    open()
    fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'a medias' } })
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar Escenas' }))

    open()

    // Es la consecuencia practica de no montar el contenido cerrado: un editor
    // no reaparece con el borrador de la vez anterior.
    expect(screen.getByLabelText('Nombre')).toHaveProperty('value', '')
  })

  it('se abre como modal, que es lo que deja el fondo fuera del tabulador', () => {
    const showModal = vi.spyOn(HTMLDialogElement.prototype, 'showModal')
    const show = vi.spyOn(HTMLDialogElement.prototype, 'show')
    render(<Harness />)

    open()

    expect(showModal).toHaveBeenCalledTimes(1)
    // `show()` abriria el mismo cuadro sin capa superior: el boton «Abrir» de
    // detras seguiria siendo alcanzable con el tabulador y con el lector.
    expect(show).not.toHaveBeenCalled()
  })

  it('se anuncia como dialogo modal con el titulo por nombre', () => {
    render(<Harness />)
    open()

    const dialog = screen.getByRole('dialog', { name: 'Escenas' })
    expect(dialog.getAttribute('aria-modal')).toBe('true')
  })

  it('Escape cierra', () => {
    render(<Harness />)
    open()

    pressEscape()

    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('devuelve el foco al elemento que lo abrio', () => {
    render(<Harness />)
    const trigger = open()

    // Precondicion, no la tesis: el foco inicial dentro del dialogo lo mueve la
    // plataforma (aqui, su doble).
    expect(screen.getByRole('dialog').contains(document.activeElement)).toBe(true)

    pressEscape()

    // Esto si es cosa del componente: al cerrar se desmonta el `<dialog>`, y
    // quitar del DOM un dialogo abierto NO ejecuta la restauracion de foco del
    // estandar. Sin ella, el foco caeria en `body` y se perderia el sitio.
    expect(document.activeElement).toBe(trigger)
  })

  it('el clic en el fondo cierra', () => {
    render(<Harness />)
    open()

    const dialog = screen.getByRole('dialog')
    // El clic en el `::backdrop` llega como un clic sobre el propio <dialog>.
    fireEvent.mouseDown(dialog)
    fireEvent.click(dialog)

    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('no cierra si el gesto empieza dentro y acaba en el fondo', () => {
    render(<Harness />)
    open()

    const dialog = screen.getByRole('dialog')
    // Seleccionar texto de un campo y soltar el raton fuera es el caso real:
    // el clic aterriza en el fondo sin que nadie haya querido cerrar nada.
    fireEvent.mouseDown(screen.getByLabelText('Nombre'))
    fireEvent.click(dialog)

    expect(screen.getByRole('dialog')).toBeDefined()
  })

  it('con cambios sin guardar el fondo no cierra, pero Escape si', () => {
    render(<Harness dismissOnBackdrop={false} />)
    open()

    const dialog = screen.getByRole('dialog')
    fireEvent.mouseDown(dialog)
    fireEvent.click(dialog)

    // Un clic accidental a dos centimetros del borde no puede costar lo escrito.
    expect(screen.getByRole('dialog')).toBeDefined()

    // Escape es deliberado —y en un movil ni siquiera existe—, asi que sigue
    // cerrando: un dialogo que no responde a Escape esta roto.
    pressEscape()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('bloquea el scroll del fondo y lo deja como estaba al cerrar', () => {
    document.body.style.overflow = 'auto'
    render(<Harness />)

    open()
    expect(document.body.style.overflow).toBe('hidden')

    pressEscape()
    // Se restaura el valor previo, no se borra: la pagina no da un salto.
    expect(document.body.style.overflow).toBe('auto')

    document.body.style.overflow = ''
  })
})
