"""Audit chain integrity + notification scoping."""
from app.extensions import db
from app.models import AuditLog

from .conftest import h
