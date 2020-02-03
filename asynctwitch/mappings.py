# External Libraries
import asks


class EmoteMapping:
    emotes = {}

    async def load(self):
        async with asks.get(
                "https://twitchemotes.com/api_cache/v2/global.json") as resp:
            self.emotes = resp.json()["emotes"]
