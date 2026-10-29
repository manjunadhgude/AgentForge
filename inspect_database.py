
import os

import psycopg
from psycopg.conninfo import make_conninfo


connection_string = make_conninfo(
    host="127.0.0.1",
    port=5432,
    dbname="agentforge",
    user="agentforge",
    password=os.environ["AGENTFORGE_DB_PASSWORD"],
)

with psycopg.connect(connection_string) as connection:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
            ORDER BY table_name
            """,
            ("public",),
        )

        print("AgentForge tables:")
        for row in cursor.fetchall():
            print("-", row[0])
