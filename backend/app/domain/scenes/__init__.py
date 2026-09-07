"""Escenas: que efecto aplica cada dispositivo cuando el usuario pulsa un boton.

Paquete **puro**. No conoce BLE, ni adaptadores, ni `DeviceType`, ni SQLModel:
una escena es un nombre y una lista de objetivos, y un objetivo es una
referencia a un dispositivo, una referencia a un efecto y dos anulaciones. Esa
es exactamente la razon por la que añadir mañana una tira WLED no obliga a tocar
nada de aqui (ARCHITECTURE 4).
"""
