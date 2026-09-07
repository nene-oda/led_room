"""Infraestructura Bluetooth: el UNICO paquete del backend que importa `bleak`.

La frontera la vigila un test (`test_device_registry.py`): cualquier `import
bleak` fuera de aqui rompe la build. El motivo es concreto -- la factoria de
dispositivos tiene que poder importarse en un host sin radio y en la CI -- y por
eso `registry.py` importa este paquete de forma diferida, solo cuando la
configuracion elige de verdad el descubrimiento BLE.

**Descubrir no es controlar.** Hoy solo existe `scanner.py`: leer anuncios BLE
no necesita ningun UUID de servicio ni ningun byte de comando, asi que no choca
con la regla de ARCHITECTURE 8 de no inventar protocolo. `connection.py`,
`protocol.py` y `lotus_lantern.py` siguen sin existir porque esos si necesitan
el protocolo verificado contra el hardware (Fase 0).
"""
