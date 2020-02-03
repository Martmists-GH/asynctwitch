# Stdlib
from typing import Any, List, Tuple

# Asynctwitch
from asynctwitch.bots.base import BotBase
from asynctwitch.ext.db.base_db import BaseDB


class IndexDBMeta(type):
    def __getitem__(cls, item):
        if issubclass(item, BaseDB):

            class SelectedDatabaseBot(DatabaseBot):  # pylint: disable=used-before-assignment
                def __init__(self,
                             *,
                             db_name: str = "asynctwitch",
                             db_user: str = "asynctwitch",
                             db_pass: str = "",
                             db_host: str = "localhost",
                             db_port: int = 0,
                             **kwargs):
                    super().__init__(**kwargs)
                    self.database: BaseDB = item()
                    self._db_args = (db_name, db_user, db_pass, db_host,
                                     db_port)

            return SelectedDatabaseBot
        raise TypeError("Expected instance of BaseDB")


class DatabaseBot(BotBase, metaclass=IndexDBMeta):
    database: BaseDB
    _db_args: Tuple[str, str, str, str, int]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print(
            "[AsyncTwitch] WARNING: All databases are implemented synchonously by default. "
            "For optimal performance, reimplement these using your async library of choice."
        )

    async def event_ready(self):
        await super().event_ready()
        await self.database.post_init(*self._db_args)

    async def query(self, query: str,
                    args: Tuple[Any, ...]) -> List[Tuple[Any, ...]]:
        return await self.database.query(query, args)
