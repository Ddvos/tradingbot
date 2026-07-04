"""Engine and session-factory construction for the Postgres adapter."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_db_engine(database_url: str) -> Engine:
    return create_engine(database_url)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False: repositories convert rows to frozen records
    # after commit; there is no lazy-loading to protect.
    return sessionmaker(engine, expire_on_commit=False)
