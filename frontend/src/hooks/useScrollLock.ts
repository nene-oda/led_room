import { useEffect } from 'react'

/**
 * Bloquea el scroll del fondo mientras el componente que lo usa esta montado.
 *
 * `<dialog>` aporta la capa superior, el foco y Escape, pero **no** congela la
 * pagina de detras: sin esto, arrastrar sobre el modal en un movil hace rodar
 * la pantalla de abajo y al cerrar apareces en otro sitio.
 *
 * Dos detalles que evitan el salto que el usuario si nota:
 *
 *   - se compensa el ancho de la barra de scroll con `padding-right`, para que
 *     el contenido no se desplace lateralmente al ocultarla;
 *   - se restauran los **valores en linea previos** (no se ponen a `''`), asi
 *     que si alguien mas los habia fijado siguen como estaban.
 */
export function useScrollLock(): void {
  useEffect(() => {
    const { body } = document
    const previousOverflow = body.style.overflow
    const previousPaddingRight = body.style.paddingRight

    // Ancho real de la barra de scroll: 0 en moviles y en barras superpuestas.
    const scrollbar = window.innerWidth - document.documentElement.clientWidth

    body.style.overflow = 'hidden'
    if (scrollbar > 0) body.style.paddingRight = `${String(scrollbar)}px`

    return () => {
      body.style.overflow = previousOverflow
      body.style.paddingRight = previousPaddingRight
    }
  }, [])
}
