class Object:
    """Base object class
    May be created as substitute for functions.
    """

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
