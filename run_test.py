import asynctwitch as at


class Bot(at.CommandBot, at.RankedBot):
	pass


bot = Bot(
    user='justinfan100'  # read-only client
)


@bot.command("test", desc="Some test command")
async def test(m, arg1:int):
	pass


bot.add_rank("test rank", points=10)


@bot.override
async def raw_event(data):
    print(data)


@bot.override
async def event_roomstate(tags):
    bot.stop(exit=True)
    print('Failed to exit!')


bot.start()