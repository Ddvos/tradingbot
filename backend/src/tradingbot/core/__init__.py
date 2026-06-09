"""Pure business logic — no I/O, no frameworks.

Imports: standard library + data libs (polars, numpy) only. Pydantic only where
truly needed; internally prefer a frozen dataclass / NamedTuple. No requests,
sqlalchemy, fastapi. See CLAUDE.md → Import rules.
"""
