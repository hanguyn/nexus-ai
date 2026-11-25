import os
from collections.abc import Iterator

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


engine = create_engine(
    os.environ.get("DATABASE_URL")
    or URL.create(
        "postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        database=os.environ["POSTGRES_DB"],
    ),
    pool_pre_ping=True,
)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
