"""Puertos que la capa de aplicacion necesita del exterior (NEXT_STEPS A4).

Viven aqui, y no en `domain/`, porque son necesidades de los casos de uso, no
del modelo: el dominio no publica nada, se limita a describir lo ocurrido.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.app.domain.events import DomainEvent


@runtime_checkable
class EventPublisher(Protocol):
    """Difunde un evento de dominio a quien este escuchando.

    La capa de aplicacion depende de ESTE puerto y **nunca** de
    `websocket/manager.py`. La direccion de la dependencia es lo unico que
    impide que un servicio acabe importando FastAPI para mandar un mensaje;
    `ConnectionManager` sera una implementacion mas, y una implementacion nula o
    de test es igual de valida.

    `publish` no debe lanzar por culpa de un cliente lento o caido: un fallo de
    difusion no puede deshacer un cambio que el hardware ya acepto.
    """

    async def publish(self, event: DomainEvent, version: int) -> None:
        """Difunde `event` sellado con la `version` del estado que lo produjo.

        La version viaja en el sobre de TODOS los frames servidor -> cliente. Es
        lo unico que permite al cliente detectar que se perdio algo (un evento
        que gasto version sin publicarse, o un frame que su propia cola de
        salida descarto) y rehidratar con `GET /api/v1/state` en vez de quedarse
        mostrando un estado viejo.
        """
        ...
