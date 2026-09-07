"""DTOs de transporte de la API REST y del WebSocket.

Son una capa aparte del dominio y de los `*Record` de persistencia a proposito:
los tres describen cosas distintas y cambian por motivos distintos. El dominio
modela reglas, los `*Record` modelan filas y estos DTOs modelan **el cable**.

Contratos que fijan estos modelos (ARCHITECTURE 3.2, 3.3 y 3.4):

* `snake_case` en todas las claves.
* Color: `{r, g, b}` 0-255 en los cuerpos de mutacion, `#RRGGBB` en MAYUSCULAS
  en las lecturas y en el estado.
* Brillo: entero 0-100 siempre.
* `Device.id` viaja como cadena.

El paquete `websocket/` reutiliza estos mismos modelos: el formato del cable se
define UNA vez y REST y WebSocket no pueden divergir.
"""
