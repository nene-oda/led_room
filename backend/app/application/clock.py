"""Puerto de tiempo. Existe para que los tests no duerman de verdad.

El bucle de reproduccion necesita dos cosas del reloj y ninguna mas: saber
cuanto ha pasado y esperar. Separarlas en un puerto estrecho permite inyectar un
reloj manual y verificar una transicion de 4 s en microsegundos. Un test que
tarda 4 s en comprobar una transicion de 4 s es un test que nadie ejecuta
(NEXT_STEPS 6.9).

Se usa tiempo **monotono** y no el de pared: el reloj del sistema puede saltar
hacia atras con un ajuste NTP y la linea de tiempo del efecto se descuadraria.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Lo minimo que el motor necesita del tiempo."""

    def monotonic(self) -> float:
        """Segundos desde un origen arbitrario pero estable. Nunca retrocede."""
        ...

    async def sleep(self, seconds: float) -> None:
        """Cede el control durante `seconds`. Debe ser cancelable."""
        ...
