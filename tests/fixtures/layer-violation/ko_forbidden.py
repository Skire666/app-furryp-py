"""Imports breaking a forbidden contract."""

import app.infra
import app.infra.db
from app import infra, other
from app.infra import db, session

VALUES = (app, infra, other, db, session)
