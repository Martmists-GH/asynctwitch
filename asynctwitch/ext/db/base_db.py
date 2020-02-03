from abc import ABCMeta, abstractmethod
from typing import Tuple, Any, List


class BaseDB(metaclass=ABCMeta):
    @abstractmethod
    def post_init(self, db_name: str, db_user: str, db_pass: str, db_host: str, db_port: int):
        """Called when database needs to be initialized"""
        pass

    @abstractmethod
    async def query(self, query: str, args: Tuple[Any, ...]) -> List[Tuple[Any, ...]]:
        """Executes a query and returns any rows if matching

        Parameters
        ----------
        query : str
            The SQL query
        args : Tuple[Any, ...]
            Arguments to be escaped for the SQL query

        Returns : List[Tuple[Any, ...]]
            The resulting row
        """
        pass
