from asynctwitch.entities.object import Object


class Badge(Object):
    """
    A class to hold badge data.

    Attributes
    ----------
    name : str
        Name of the badge.
    value : str
        Variant of the badge.
    """

    def __init__(self, name: str, value: str):
        super().__init__()
        self.name = name
        self.value = value

    def __str__(self):
        return f"{self.name}/{self.value}"

    @classmethod
    def from_str(cls, s):
        """ e.g. Moderator/1 """
        n, v = s.split("/")
        return cls(n, v)
