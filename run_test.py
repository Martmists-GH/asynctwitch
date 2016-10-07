import asynctwitch as at

bot = at.Bot(
    user = 'justinfan100' # read-only client
)

@bot.override
async def raw_event(data):
    print(data)

@bot.override
async def event_roomstate(tags):
    bot.stop(exit=True)
    print('Failed to exit!')
    
bot.start()