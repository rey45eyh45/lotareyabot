"""Aggregate handler registration."""
from __future__ import annotations

from telegram.ext import Application

from . import admin, user


def register_handlers(application: Application) -> None:
    """Hook all user and admin handlers into the application."""
    user.register_user_handlers(application)
    admin.register_admin_handlers(application)
