from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_db_engine(
    host: str,
    port: int,
    name: str,
    user: str,
    password: str,
    schema: str,
) -> Engine:
    """Builds a SQLAlchemy engine from individual connection parameters.

    Args:
        host: Postgres host.
        port: Postgres port.
        name: Database name.
        user: Database user.
        password: Database password.
        schema: Default schema to use.

    Returns:
        A configured SQLAlchemy engine.
    """
    url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"
    return create_engine(url, connect_args={"options": f"-csearch_path={schema}"})


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Builds a session factory bound to the given engine."""
    return sessionmaker(bind=engine)
