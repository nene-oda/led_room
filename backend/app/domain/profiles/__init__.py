"""Perfiles: un contexto ("Gaming", "Sleep") que agrupa escenas.

Paquete **puro**, igual que `domain/scenes`. Un perfil no sabe activar nada: solo
sabe **cual** de sus escenas es la predeterminada. Activarla es un caso de uso, y
vive en `application/profile_service.py`.
"""
