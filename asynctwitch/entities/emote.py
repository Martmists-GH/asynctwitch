# Asynctwitch
from asynctwitch.entities.object import Object
from asynctwitch.mappings import EmoteMapping


class Emote(Object):
    """
    A class to hold emote data

    Attributes
    ----------
    id : int
        The ID of the emote.
    location : str
        The location of the emote in the message.
    url : str
        The url of the emote.
    """
    def __init__(self, _id: str, loc: str):
        super().__init__()
        self.id = _id
        self.location = loc
        self.url = f"https://static-cdn.jtvnw.net/emoticons/v1/{_id}/3.0"

    def __str__(self):
        for k, v in EmoteMapping.emotes.items():
            if str(v['image_id']) == self.id:
                return k
        return ""
