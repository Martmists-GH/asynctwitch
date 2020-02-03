# Stdlib
from typing import Any, Dict, List, Tuple

# External Libraries
from pymysql import Connection, connect, cursors

# Asynctwitch
from asynctwitch.ext.db.base_db import BaseDB


class MySQLDB(BaseDB):
    def __init__(self):
        self.connection: Connection = None

    def post_init(self, db_name: str, db_user: str, db_pass: str, db_host: str,
                  db_port: int):
        self.connection = connect(host=db_host,
                                  user=db_user,
                                  password=db_pass,
                                  db=db_name,
                                  charset='utf-8',
                                  cursorclass=cursors.DictCursor)

    async def query(self, query: str,
                    args: Tuple[Any, ...]) -> List[Dict[str, Any]]:
        with self.connection.cursor() as cursor:
            cursor.execute(query, args)
            self.connection.commit()
            return cursor.fetchall()
