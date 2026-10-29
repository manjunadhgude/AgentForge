
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from action_ledger import initialize_ledger


database_url = URL.create(
    drivername="postgresql+psycopg",
    username="agentforge",
    password=os.environ["AGENTFORGE_DB_PASSWORD"],
    host="127.0.0.1",
    port=5432,
    database="agentforge",
)

engine = create_engine(database_url)

try:
    initialize_ledger(engine)
    print("Action ledger initialized successfully.")
finally:
    engine.dispose()
