"""
ASGI config for webapp project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

# myproject/asgi.py
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webapp.settings")
django_asgi_app = get_asgi_application()

from socketio import ASGIApp
from webapp.socket_server import sio


application = ASGIApp(sio, django_asgi_app)
