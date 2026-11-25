from alembic import context

from app.db import Base, engine
from app import models  # Register tables on Base.metadata.
from app.modules.anomaly import models as anomaly_models
from app.modules.assistant import models as assistant_models
from app.modules.rca import models as rca_models
from app.modules.simulator import models as simulator_models
from app.modules.troubleshooting import models as troubleshooting_models


def include_object(obj, name, type_, reflected, compare_to):
    # PostgreSQL is shared with Grafana. Exclude tables outside this backend.
    return type_ != "table" or name in Base.metadata.tables


options = {"target_metadata": Base.metadata, "include_object": include_object}
if context.is_offline_mode():
    context.configure(
        url=engine.url, literal_binds=True, dialect_opts={"paramstyle": "named"}, **options
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        context.configure(connection=connection, **options)
        with context.begin_transaction():
            context.run_migrations()
