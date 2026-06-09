"""Autonomous bot process — separate from the API, shares the DB.

runner.py: APScheduler 1h tick loop. command_listener.py: polls DB flags.
May import from application/. Slice 5, hardening in Slice 6.
"""
