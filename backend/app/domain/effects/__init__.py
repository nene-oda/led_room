"""Motor de efectos: dominio puro.

```text
EffectDefinition -> build_plan -> EffectPlan -> Renderer -> Segmento -> LightFrame
```

Nada de este paquete conoce SQLModel, Bleak, FastAPI, el reloj ni el WebSocket:
la orquestacion temporal vive en `application/effect_runner.py` y la aplicacion
al hardware, detras de `LightDevicePort`. Un test recorre con `ast` todo
`domain/` y falla si eso deja de ser cierto.
"""

from __future__ import annotations
