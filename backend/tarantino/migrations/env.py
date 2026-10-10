from alembic import context
from sqlalchemy import create_engine

import tarantino.models  # noqa: F401  (registers tables on Base.metadata)
from tarantino.db import Base

target_metadata = Base.metadata


def run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


# The app passes an open connection (tarantino.db.migrate); for autogenerate
# during development a `sqlalchemy.url` option is used instead.
connection = context.config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    with create_engine(context.config.get_main_option("sqlalchemy.url")).connect() as conn:
        run(conn)
        conn.commit()
