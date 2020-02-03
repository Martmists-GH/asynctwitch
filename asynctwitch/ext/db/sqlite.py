# Stdlib
from sqlite3 import Cursor, Connection, connect
from typing import Any, List, Tuple

# Asynctwitch
from asynctwitch.ext.db.base_db import BaseDB


class SQLiteDB(BaseDB):
    def __init__(self):
        self.connection: Connection = None
        self.cursor: Cursor = None

    async def post_init(self, db_name: str, db_user: str, db_pass: str,
                        db_host: str, db_port: int):
        self.connection = connect(db_name + ".db")
        self.cursor = self.connection.cursor()

    async def query(self, query: str,
                    args: Tuple[Any, ...]) -> List[Tuple[Any, ...]]:
        self.cursor.execute(query, args)
        self.connection.commit()
        return self.cursor.fetchall()
