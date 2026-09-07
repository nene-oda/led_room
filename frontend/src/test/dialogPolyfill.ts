/**
 * Emulacion minima de `<dialog>` para jsdom.
 *
 * jsdom 30 declara `HTMLDialogElement` y refleja el atributo `open`, pero **no
 * implementa `show()`, `showModal()` ni `close()`**, ni la tecla Escape. Sin
 * esto, cualquier prueba que abra un modal revienta con
 * `dialog.showModal is not a function`.
 *
 * Es un doble de **plataforma**, no de la aplicacion: emula lo que el navegador
 * hace y que el componente da por hecho, igual que `FakeSocket` emula el
 * WebSocket. Se limita a lo que `ui/Modal` usa:
 *
 *   - `showModal()` abre y lleva el foco al primer elemento enfocable (el
 *     algoritmo de "focus delegate" del HTML);
 *   - Escape emite `cancel` cancelable y, si nadie lo detiene, cierra;
 *   - `close()` emite `close`.
 *
 * **No emula dos cosas a proposito**, para que ninguna prueba las de por
 * probadas:
 *
 *   - la *inercia* del fondo (capa superior). Es la garantia por la que se usa
 *     `showModal()` y no `show()`, y ningun entorno sin motor de layout puede
 *     ejercitarla; la prueba correspondiente comprueba que se llama a
 *     `showModal()`.
 *   - la devolucion del foco al cerrar. El navegador solo la ejecuta si el
 *     dialogo se cierra estando en el DOM, y aqui **se desmonta**, que es
 *     justamente el caso en el que no ocurre: por eso la hace el componente y
 *     por eso la prueba de "el foco vuelve al disparador" prueba codigo nuestro.
 */

/** Orden de apertura: Escape cierra el de arriba, como la capa superior. */
const openModals: HTMLDialogElement[] = []

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

export function installDialogPolyfill(): void {
  const proto = HTMLDialogElement.prototype

  // Si algun dia jsdom lo implementa, gana el de verdad.
  if (typeof proto.showModal === 'function') return

  proto.show = function show(this: HTMLDialogElement): void {
    if (this.open) return
    this.open = true
  }

  proto.showModal = function showModal(this: HTMLDialogElement): void {
    if (this.open) {
      throw new DOMException('The dialog is already open', 'InvalidStateError')
    }
    this.open = true
    openModals.push(this)

    const delegate = this.querySelector<HTMLElement>(FOCUSABLE)
    if (delegate === null) this.focus()
    else delegate.focus()
  }

  proto.close = function close(this: HTMLDialogElement): void {
    if (!this.open) return
    this.open = false

    const index = openModals.indexOf(this)
    if (index !== -1) openModals.splice(index, 1)

    this.dispatchEvent(new Event('close'))
  }

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return

    const top = openModals.at(-1)
    if (top === undefined) return

    // `cancel` es cancelable: si alguien lo detiene, el dialogo sigue abierto.
    const proceed = top.dispatchEvent(new Event('cancel', { cancelable: true }))
    if (proceed) top.close()
  })
}
