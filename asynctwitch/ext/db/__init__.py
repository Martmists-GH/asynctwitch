from contextlib import suppress

from asynctwitch.ext.db.base_db import BaseDB

all_list = ["BaseDB", "SQLiteDB"]

with suppress(ImportError):
    from asynctwitch.ext.db.mysql import MySQLDB
    all_list.append("MySQLDB")

with suppress(ImportError):
    from asynctwitch.ext.db.postgres import PostgreSQLDB
    all_list.append("PostgreSQLDBb")

__all__ = tuple(all_list)
