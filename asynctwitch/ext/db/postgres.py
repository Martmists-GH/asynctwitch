from typing import Tuple, Any, List

from psycopg2 import connect

from asynctwitch.ext.db import BaseDB


class PostgreSQLDB(BaseDB):
    def __init__(self):
        self.connection = None
        self.cursor = None

    async def post_init(self, db_name: str, db_user: str, db_pass: str, db_host: str, db_port: int):
        self.connection = connect(dbname=db_name, user=db_user, password=db_pass, host=db_host, port=db_port)
        self.cursor = self.connection.cursor()

    async def query(self, query: str, args: Tuple[Any, ...]) -> List[Tuple[Any, ...]]:
        self.cursor.execute(query, args)
        self.connection.commit()
        return self.cursor.fetchall()
