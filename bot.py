import os

import discord
import random
import time
from datetime import datetime
from disnake.ext.commands.context import Context
from dotenv import load_dotenv
import asyncio

import logging

import disnake 
from disnake.ext.commands import bot
from disnake.ext import commands
from disnake.ext import tasks
from disnake import Option, OptionChoice, Interaction, Intents,ApplicationCommandInteraction
from MusicBot import musiccommands


from discord.ext import commands as commands_alt
from disnake.ext.commands import slash_command

logging.basicConfig(level=logging.INFO)

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD = os.getenv('DISCORD_GUILD_MYSELF')

activity = disnake.Activity(name='Stardew Valley!', type=disnake.ActivityType.playing)
bot = commands.InteractionBot(intents=disnake.Intents.all(),
activity=activity)


@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    
    for guild in bot.guilds:
        if guild.name == GUILD:
            break

        print(
            f'{bot.user} is connected to the following guild:\n'
            f'{guild.name}(id: {guild.id})'
    )



@bot.event
async def on_error(event, *args, **kwargs):
    with open('err.log', 'a') as f:
        if event == 'on_message':
            f.write(f'Unhandled message: {args[0]}\n')
        else:
            raise




#client.run(TOKEN)
bot.add_cog(musiccommands.MusicPlayer(bot))
bot.run(TOKEN)
