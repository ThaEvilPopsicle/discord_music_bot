import asyncio
import functools
import itertools
from functools import partial
import math
import random
import os
import string
import disnake
from disnake.ext.commands import bot,Bot, has_permissions, has_guild_permissions, base_core, core,InteractionBot
from disnake.ext import commands
from disnake.ext import tasks
from disnake import Option, OptionChoice, Interaction, Intents,ApplicationCommandInteraction,abc
import yt_dlp as youtube_dl
from async_timeout import timeout
from googleapiclient.discovery import build
from disnake.ext.commands import slash_command

from disnake import emoji
import re
import time
from datetime import datetime



# flat-playlist:True?
# extract_flat:True
# audioquality 0 best 9 worst
# format bestaudio/best or worstaudio
# 'noplaylist': None
ytdl_format_options = {
    'audioquality': 0,
    'format': 'bestaudio',
    'outtmpl': '{}',
    'restrictfilenames': True,
    'flatplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    "extractaudio": True,
    "audioformat": "opus",
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    # bind to ipv4 since ipv6 addresses cause issues sometimes
    'source_address': '0.0.0.0'
}

# Download youtube-dl options
ytdl_download_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': 'downloads/%(title)s.mp3',
    'reactrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    # bind to ipv4 since ipv6 addreacses cause issues sometimes
    'source_address': '0.0.0.0',
    'output': r'youtube-dl',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '240',
        }]
}

stim = {
    'default_search': 'auto',
    "ignoreerrors": True,
    'quiet': True,
    "no_warnings": True,
    "simulate": True,  # do not keep the video files
    "nooverwrites": True,
    "keepvideo": False,
    "noplaylist": False,
    "skip_download": True,
    # bind to ipv4 since ipv6 addresses cause issues sometimes
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
   
}

#ffmpeg_options = {
    #'options': '-vn -bufsize 32k'
#}


class Downloader(disnake.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get("url")
        self.thumbnail = data.get('thumbnail')
        self.duration = data.get('duration')
        self.views = data.get('view_count')
        self.playlist = {}


    @classmethod
    async def video_url(cls, url, ytdl, *, loop=None, stream=True):
        """
        Prepare the song data for streaming
        """
        loop = loop or asyncio.get_event_loop()
        to_run = partial(ytdl.extract_info, url=url, download=False)
        #data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        data = await loop.run_in_executor(None, to_run)
        song_list = {'queue': []}
        #link_list = {'link_queue': []}
        playlist_links=[]
        def Merge(dict1, dict2):
            res = {**dict1, **dict2}
            return res

        if 'entries' in data:
            if len(data['entries']) > 1:
                playlist_titles = [title['title'] for title in data['entries']]
                playlist_links = [webpage_url['webpage_url'] for webpage_url in data['entries']]
                song_list = {'queue': playlist_titles}
                link_list ={'link_queue': playlist_links}
                song_list = Merge(song_list, link_list)
                song_list['queue'].pop(0)
                song_list['link_queue'].pop(0)
                #link_list['link_queue'].pop(0)

            data = data['entries'][0]
            #data = link_list['link_queue'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(disnake.FFmpegPCMAudio(filename,**ffmpeg_options), data=data), song_list
        
    async def get_info(self, url):
        """
        Get the info of the next song by not downloading the actual file but just the data of song/query
        """
        yt = youtube_dl.YoutubeDL(stim)
        down = yt.extract_info(url, download=False)
        data1 = {'queue': []}
        if 'entries' in down:
            if len(down['entries']) > 1:
                playlist_titles = [title['title'] for title in down['entries']]
                data1 = {'title': down['title'], 'queue': playlist_titles}

            down = down['entries'][0]['title']

        return down, data1
     


class MusicPlayer(commands.Cog, name='Music'):
    def __init__(self, bot):
        self.bot = bot
        # self.music=self.database.find_one('music')
        self.player = {
            "audio_files": []
        }
        # self.database_setup()
        self.voice_states = {}
        

    @property
    def random_color(self):
        return disnake.Color.from_rgb(random.randint(1, 255), random.randint(1, 255), random.randint(1, 255))

    @commands.Cog.listener('on_voice_state_update')
    async def music_voice(self, user, before, after):
        """
        Clear the server's playlist after bot leave the voice channel
        """
        if after.channel is None and user.id == self.bot.user.id:
            try:
                self.player[user.guild.id]['queue'].clear()
            except KeyError:
                # NOTE: server ID not in bot's local self.player dict
                # Server ID lost or was not in data before disconnecting
                print(f"Failed to get guild id {user.guild.id}")
    
    #helps us to parse through repeat songs
    async def filename_generator(self):
        """
        Generate a unique file name for the song file to be named as
        """
        chars = list(string.ascii_letters+string.digits)
        name = ''
        for i in range(random.randint(9, 25)):
            name += random.choice(chars)

        if name not in self.player['audio_files']:
            return name

        return await self.filename_generator()


    async def playlist(self, data, msg):
        """
        THIS FUNCTION IS FOR WHEN YOUTUBE LINK IS A PLAYLIST
        Add song into the server's playlist inside the self.player dict
        """
        if "link_queue" in data:
            for i in range(len(data['queue'])):
                title_to_write = data['queue'][i]
                link_to_write = data['link_queue'][i]
                #print(title_to_write)
                #print(link_to_write)
                    
            #print(i)
                self.player[msg.guild.id]['queue'].append(
                {'title': title_to_write, 'author': msg, 'url': link_to_write})
                continue

        else:
            for i in data['queue']:
            #print(i)
                self.player[msg.guild.id]['queue'].append(
                {'title': i, 'author': msg, 'url': None})


    async def add_links(self, links, msg):
        """
        THIS FUNCTION IS FOR WHEN YOUTUBE LINK IS A PLAYLIST
        Add song into the server's playlist inside the self.player dict
        """
        for j in links['link_queue']:
            self.player[msg.guild.id]['link_queue'].append(
            {'title': 'test','author':msg, 'url': [j]})

    async def queue(self, msg, song):
        """
        Add the query/song to the queue of the server
        """

        if msg.response._response_type ==False:
            await msg.response.defer()
        new_opts = ytdl_format_options.copy()
        if type(song) is dict:
            song = song['webpage_url']
        ytdl = youtube_dl.YoutubeDL(new_opts)
        title1 = await Downloader.get_info(self, url=song)
        title = title1[0]
        playlist_title = title1[1]
        #data = title1[1]
        download1 = await Downloader.video_url(song, ytdl=ytdl, loop=self.bot.loop)
        #title = download1[0]
        data = download1[1]
        # fix is below as if you search via a url, it comes through as a dictionary, but text search comes in as text.
        if data['queue']:
            await self.playlist(data, msg)
            # NOTE: needs to be embeded to make it better output
            return await msg.edit_original_message(content=f"**Added playlist {playlist_title['title']} to queue**")
        else:
            self.player[msg.guild.id]['queue'].append(
                {'title': title, 'author': msg})
        #print(title)
        if type(title) is dict:
            new_title = title['title']
        else:
            new_title = title

        if msg.application_command != None:
            return await msg.edit_original_message(content=f"**{new_title} added to queue**".title())
        else:
            return await msg.channel.send(f"**{new_title} added to queue**".title())

    async def voice_check(self, msg):
        """
        function used to make bot leave voice channel if music not being played for longer than 2 minutes
        """
        if msg.user.guild.voice_client is not None:
            await asyncio.sleep(120)
            if msg.user.guild.voice_client is not None and msg.user.guild.voice_client.is_playing() is False and msg.user.guild.voice_client.is_paused() is False:
                await msg.user.guild.voice_client.disconnect()

    async def clear_data(self, msg):
        """
        Clear the local dict data
            name - remove file name from dict
            remove file and filename from directory
            remove filename from global audio file names
        """
        name = self.player[msg.guild.id]['name']
        #os.remove(name)
        #self.player['audio_files'].remove(name)

    async def loop_song(self, msg):
        """
        Loop the currently playing song by replaying the same audio file via `disnake.PCMVolumeTransformer()`
        """
        #source = disnake.PCMVolumeTransformer(
            #disnake.FFmpegPCMAudio(self.player[msg.guild.id]['name']))
        #test_song = self.player[msg.guild.id]['player'].data['webpage_url']

        new_opts = ytdl_format_options.copy()
        audio_name = await self.filename_generator()

        self.player['audio_files'].append(audio_name)
        new_opts['outtmpl'] = new_opts['outtmpl'].format(audio_name)
        try:
            song_to_loop = self.player[msg.guild.id]['player'].data['webpage_url']
            if type(song_to_loop) is dict:
                song_to_loop = song_to_loop['webpage_url']
            ytdl = youtube_dl.YoutubeDL(new_opts)
            download1 = await Downloader.video_url(song_to_loop, ytdl=ytdl, loop=self.bot.loop)
            download = download1[0]
            data = download1[1]
        #webpage_url = download.data['webpage_url']
        #links = download1[2]
        
            self.player[msg.guild.id]['name'] = audio_name
            emb = disnake.Embed(colour=self.random_color, title='Now Playing',
                                description=download.title, url=download.data['webpage_url'])
            emb.set_thumbnail(url=download.thumbnail)
            emb.set_footer(
                text=f'Requested by {msg.author.display_name}', icon_url=msg.author.avatar.url)
            loop = asyncio.get_event_loop()

            if data['queue']:
                await self.playlist(data, msg)
        
            msgId = await msg.channel.send(embed=emb)

            self.player[msg.guild.id]['player'] = download
            self.player[msg.guild.id]['author'] = msg
            msg.guild.voice_client.play(
                download, after=lambda a: loop.create_task(self.done(msg, msgId.id)))

            # if str(msg.guild.id) in self.music: #NOTE adds user's default volume if in database
            #     msg.voice_client.source.volume=self.music[str(msg.guild.id)]['vol']/100
            msg.user.guild.voice_client.source.volume = self.player[msg.guild.id]['volume']
            return msg.user.guild.voice_client

        except Exception as Error:
            # Has no attribute play
            print(Error)  # NOTE: output back the error for later debugging

    async def done(self, msg, skip_flag, msgId: int = None):
        """
        Function to run once song completes
        Delete the "Now playing" message via ID
        """
        if msgId:
            try:
                message = await msg.channel.fetch_message(msgId)
                await message.delete()
            except Exception as Error:
                print("Failed to get the message")

        if self.player[msg.guild.id]['reset'] is True:
            self.player[msg.guild.id]['reset'] = False
            return await self.loop_song(msg)

        if msg.guild.id in self.player and self.player[msg.guild.id]['repeat'] is True:
            return await self.loop_song(msg)

        await self.clear_data(msg)

        if self.player[msg.guild.id]['queue']:
            queue_data = self.player[msg.guild.id]['queue'].pop(0)
        try:
            if "url" in queue_data: #and msg.user.guild.voice_client is not None:
                if queue_data['url'] != None:
                    return await self.start_song(msg=queue_data['author'],song=queue_data['url'],skip_flag=skip_flag)
            elif  "title" in queue_data:
                return await self.start_song(msg=queue_data['author'], song=queue_data['title'], skip_flag=skip_flag)
            #if self.player[msg.guild.id]['link_queue']:
                #link_data = self.player[msg.guild.id]['link_queue'].pop(0)

            #if link_data != None:
                #return await self.start_song(msg=link_data['author'], song=link_data['url'][0])
            #need fix to handle items added as a url and not text
            #elif link_data == None:
                #return await self.start_song(msg=queue_data['author'], song=queue_data['title'])

            else:
                skipped_song_message =  await msg.edit_original_message(content="No Songs left in the Queue!")
                return await skipped_song_message.add_reaction(emoji='✅')
                await self.voice_check(msg)
        #Just an exception handler. Need to redo to make it more robust
        except UnboundLocalError:
            print("Error Detected. Initiate Voice Check Module")
            await self.voice_check(msg)
            print("Mitigate Error from Bot Leaving")

    #This will play the song once it is received through the /play command
    async def start_song(self, msg, song, skip_flag):


        new_opts = ytdl_format_options.copy()
        audio_name = await self.filename_generator()

        self.player['audio_files'].append(audio_name)
        new_opts['outtmpl'] = new_opts['outtmpl'].format(audio_name)

        if type(song) is dict:
            song = song['webpage_url']
        ytdl = youtube_dl.YoutubeDL(new_opts)
        download1 = await Downloader.video_url(song, ytdl=ytdl, loop=self.bot.loop)
        download = download1[0]
        data = download1[1]
        #webpage_url = download.data['webpage_url']
        #links = download1[2]

        #When song is playing, we will send an embedded message to the text channel the bot was started in telling the user which song is starting to play
        #will attempt to add the user's avatar image to the message. 
        try:
            if msg.author.avatar is None:
                self.player[msg.guild.id]['name'] = audio_name
                emb = disnake.Embed(colour=self.random_color, title='Now Playing',
                            description=download.title, url=download.data['webpage_url'])
                emb.set_thumbnail(url=download.thumbnail)
                emb.set_footer(
                text=f'Requested by {msg.author.display_name}')
            else:
                self.player[msg.guild.id]['name'] = audio_name
                emb = disnake.Embed(colour=self.random_color, title='Now Playing',
                            description=download.title, url=download.data['webpage_url'])
                emb.set_thumbnail(url=download.thumbnail)
                emb.set_footer(
                text=f'Requested by {msg.author.display_name}', icon_url=msg.author.avatar.url)

        except:
            self.player[msg.guild.id]['name'] = audio_name
            emb = disnake.Embed(colour=self.random_color, title='Now Playing',
                            description=download.title, url=download.data['webpage_url'])
            emb.set_thumbnail(url=download.thumbnail)
            emb.set_footer(
                text=f'Requested by {msg.author.display_name}', icon_url=msg.author.avatar.url)
    

        loop = asyncio.get_event_loop()


        if data['queue']:
            await self.playlist(data, msg)
        
        #if links['link_queue']:
            #await self.add_links(links,msg)

            #self.player[msg.guild.id]['link_queue'] = links

        #msgId = await msg.channel.send(embed=emb)
        #if msg.application_command != None:
        #test = msg.application_command.name

        if skip_flag == None:
            msgId = await msg.edit_original_message(embed=emb)
        else:
            msgId = await msg.channel.send(embed=emb)

            
        

        self.player[msg.guild.id]['player'] = download
        self.player[msg.guild.id]['author'] = msg
        #This will play the song selected and then queue up the done definitition to execute once the song is done. 
        #This allows us to queue and play multiple songs/playlists in a row
        msg.guild.voice_client.play(
            download, after=lambda a: loop.create_task(self.done(msg, msgId.id)))

        # if str(msg.guild.id) in self.music: #NOTE adds user's default volume if in database
        #     msg.voice_client.source.volume=self.music[str(msg.guild.id)]['vol']/100
        msg.user.guild.voice_client.source.volume = self.player[msg.guild.id]['volume']
        return msg.user.guild.voice_client
        
    
    #@commands.has_any_role(INSERT ROLES HERE)
    # This command will make it be usable only by the bot owner, the specific user_id and only the people that have the specified role_id, 
    # for everyone else that doesn't meet any of these criteria the slash will be grayed out.
    # Make sure the bot has permission to see this by specifying the bot in the rold_ids field below
    # Probably a better way to do this. Feel free to use in your own setup.  
    #@commands.guild_permissions(SERVER_ID,role_ids={ROLE_ID: True, ROLE_ID: True}, owner=True)
    #async def check_permissions(msg):
        #await msg.response.defer()
       # if msg.guild.id == SERVER_ID:
            #for role in msg.author.roles:
                #if role.name == "ROLE":
                    #return True
               # elif role.name == "ROLE":
                   # return True
           # else:
                #embed = disnake.Embed(color=disnake.Color.random(), timestamp=datetime.now())
                #id_to_serve=SERVER_ID
                #embed.add_field(name='Error',value='**You do not have permission to use this commmand**. Please reach out to  ' + f"<@&{id_to_serve}>" + ' if you have any questions.')
                #embed.set_footer(text="If you have any questions, suggestions or bug reports, please dm ThaEvilPopsicle")
                #message_reaction_embed= await msg.edit_original_message(embed=embed)
        #else:
            #return True

    @commands.slash_command(name="play", 
    description='Play a song in your voice channel',
    #default_permission=False,
             options =[   
        Option(
            name='song',
            description='Play a song in your voice channel',
            required=True)])
    #Used to add permission check for access control. Not used. 
    #@commands.check(check_permissions)
    async def play(self, msg, *, song, skip_flag: int = None):
        """
        Play a song with given url or title from Youtube
        `Ex:` s.play Fireflies Owl City 
        `Command:` play(song_name)
        """
        #await msg.response.defer()

        #This checks to make sure we have the necessary pieces required for the play function to work. Otherwise, we will output a message telling the user what to do
        #to be able to use the bot. 
        await self.before_play(msg)
        
        #if the bot is already playing music, we will check to see if the queue is present. If so, add song/playlist to queue.
        #else, we will create the queue and add the song/playlist to it.
        if msg.guild.id in self.player:
            if msg.user.guild.voice_client.is_playing() is True:  # NOTE: SONG CURRENTLY PLAYING
                return await self.queue(msg, song)

            if self.player[msg.guild.id]['queue']:
                return await self.queue(msg, song)

            if msg.user.guild.voice_client.is_playing() is False and not self.player[msg.guild.id]['queue']:
                return await self.start_song(msg, song,skip_flag)

        else:
            # IMPORTANT: THE ONLY PLACE WHERE NEW `self.player[msg.guild.id]={}` IS CREATED
            self.player[msg.guild.id] = {
                'player': None,
                'queue': [],
                'author': msg,
                'name': None,
                "reset": False,
                'repeat': False,
                'volume': 0.5,
                'link_queue': []
            }
            
            return await self.start_song(msg, song,skip_flag)

    #@commands.before_invoke(play)
    async def before_play(self, msg):
        """
        Check voice_client
            - User voice = None:
                please join a voice channel
            - bot voice == None:
                joins the user's voice channel
            - user and bot voice NOT SAME:
                - music NOT Playing AND queue EMPTY
                    join user's voice channel
                - items in queue:
                    please join the same voice channel as the bot to add song to queue
        """

        if msg.author.voice is None:
            return await msg.channel.send('**Please join a voice channel to play music**'.title())

        if msg.user.guild.voice_client is None:
            return await msg.author.voice.channel.connect()
            

        if msg.user.guild.voice_client.channel != msg.author.voice.channel:

            # NOTE: Check player and queue
            if msg.user.guild.voice_client.is_playing() is False and not self.player[msg.guild.id]['queue']:
                return await msg.user.guild.voice_client.move_to(msg.author.voice.channel)
                # NOTE: move bot to user's voice channel if queue does not exist

            if self.player[msg.guild.id]['queue']:
                # NOTE: user must join same voice channel if queue exist
                return await msg.channel.send("Please join the same voice channel as the bot to add song to queue")



    @commands.slash_command(name='repeat', description="Repeat the current song")
    async def repeat(self, msg):
        #"""
        #Repeat the currently playing or turn off by using the command again
        #`Ex:` .repeat
        #`Command:` repeat()
        #"""
        #await msg.response.defer()
        if msg.guild.id in self.player:
            if msg.user.guild.voice_client.is_playing() is True:
                if self.player[msg.guild.id]['repeat'] is True:
                    self.player[msg.guild.id]['repeat'] = False
                    repeat_song= await msg.edit_original_message(content="The song will be repeated!")
                    return await repeat_song.add_reaction(emoji='✅')

                self.player[msg.guild.id]['repeat'] = True
                repeat_song= await msg.edit_original_message(content="The song will be repeated!")
                return await repeat_song.add_reaction(emoji='✅')

            return await msg.edit_original_message(content="No audio currently playing")
        return await msg.edit_original_message(content="Bot not in voice channel or playing music")

    #not currently used as there is an issue with losing the FFmpegPCMAudio Player object when we try to reset the bot.
    #@commands.command(name='reset',aliases=['restart-loop'])
    async def reset(self, msg):
        #"""
        #Restart the currently playing song  from the begining
        #`Ex:` s.reset
        #`Command:` reset()
        #"""
        if msg.voice_client is None:
            return await msg.channel.send(f"**{msg.author.display_name}, there is no audio currently playing from the bot.**")

        if msg.author.voice is None or msg.author.voice.channel != msg.voice_client.channel:
            return await msg.channel.send(f"**{msg.author.display_name}, you must be in the same voice channel as the bot.**")

        if self.player[msg.guild.id]['queue'] and msg.voice_client.is_playing() is False:
            return await msg.channel.send("**No audio currently playing or songs in queue**".title(), delete_after=25)

        self.player[msg.guild.id]['reset'] = True
        msg.voice_client.stop()


    
    @commands.slash_command(name='skip', description="Skips the current song")
    async def skip(self, msg): #skip_flag: int = 1):
       # """
        #Skip the current playing song
        #`Ex:` s.skip
        #`Command:` skip()
        #"""
        #await msg.response.defer()
        skip_flag =1
        if msg.user.guild.voice_client is None:
            return await msg.edit_original_message(content="**No music currently playing**".title(), delete_after=60)

        elif msg.author.voice is None or msg.author.voice.channel != msg.user.guild.voice_client.channel:
            return await msg.edit_original_message(content="Please join the same voice channel as the bot")

        elif not self.player[msg.guild.id]['queue'] and msg.user.guild.voice_client.is_playing() is False:
            return await msg.edit_original_message(content="**No songs in queue to skip**".title(), delete_after=60)

        else:
            self.player[msg.guild.id]['repeat'] = False
            #emoji_test = disnake.emoji
            msg.user.guild.voice_client.stop()
            #emoji = disnake.utils.get(self.bot.emojis, name=':white_check_mark:')
            skipped_song_message =  await msg.edit_original_message(content="Song has been Skipped!")
            return await skipped_song_message.add_reaction(emoji='✅')
            
        #return await message_reaction_embed.add_reaction(emoji)

    @commands.slash_command(name='stop', description="Stop the current song and clear the queue")
    async def stop(self, msg):
        #"""
        #Stop the current playing songs and clear the queue
       # `Ex:` s.stop
        #`Command:` stop()
        #"""
        #await msg.response.defer()
        if msg.user.guild.voice_client is None:
            return await msg.edit_original_message(content="Bot is not connect to a voice channel")

        if msg.author.voice is None:
            return await msg.edit_original_message(content="You must be in the same voice channel as the bot")

        if msg.author.voice is not None and msg.user.guild.voice_client is not None:
            if msg.user.guild.voice_client.is_playing() is True or self.player[msg.guild.id]['queue']:
                self.player[msg.guild.id]['queue'].clear()
                self.player[msg.guild.id]['repeat'] = False
                msg.user.guild.voice_client.stop()
                embed = disnake.Embed(
                        colour=self.random_color) #, title='queue')
                embed.add_field(name='Success', value='The current song has been stopped and the queue has been cleared!')
                embed.set_footer(text="If you have any questions, suggestions or bug reports, please dm Popsicle")
                stop_message=await msg.edit_original_message(embed=embed)
                return await stop_message.add_reaction(emoji='✅')
                
            embed = disnake.Embed(
                        colour=self.random_color)
            embed.add_field(name='Failure', value=f"There is no audio currently playing or songs in queue")
            embed.set_footer(text="If you have any questions, suggestions or bug reports, please dm Popsicle")
            fail_message = await msg.edit_original_message(embed=embed)
            return await fail_message.add_reaction(emoji='✅')


    @commands.slash_command(name='leave', description="Makes the Bot Leave the Voice Channel")
    async def leave(self, msg):
        #"""
        #Disconnect the bot from the voice channel
        #`Ex:` s.leave
        #`Command:` leave()
        #"""
        #await msg.response.defer()
        if msg.author.voice is not None and msg.user.guild.voice_client is not None:
            try:
                if msg.user.guild.voice_client.is_playing() is True or self.player[msg.guild.id]['queue']:
                    self.player[msg.guild.id]['queue'].clear()
                    msg.user.guild.voice_client.stop()
                    channel = msg.author.voice.channel
                    embed = disnake.Embed(
                            colour=self.random_color)
                    embed.add_field(name='Success', value=f'The Bot has left the {channel}!')
                    leave_message = await msg.edit_original_message(embed=embed)
                    await leave_message.add_reaction(emoji='✅')
                    return await msg.user.guild.voice_client.disconnect()
                else:
                    channel = msg.author.voice.channel
                    embed = disnake.Embed(
                            colour=self.random_color)
                    embed.add_field(name='Success', value=f'The Bot has left the {channel}!')
                    leave_message = await msg.edit_original_message(embed=embed)
                    await leave_message.add_reaction(emoji='✅')
            except KeyError:
                channel = msg.author.voice.channel
                embed = disnake.Embed(
                        colour=self.random_color)
                embed.add_field(name='Success', value=f'The Bot has left the {channel}!')
                leave_message = await msg.edit_original_message(embed=embed)
                await leave_message.add_reaction(emoji='✅')
                return await msg.user.guild.voice_client.disconnect()
                #return await msg.author.voice.channel.connect()

            #return await msg.user.guild.voice_client.disconnect(), await msg.message.add_reaction(emoji='✅')

        if msg.author.voice is None:
            return await msg.edit_original_message(content="You must be in the same voice channel as bot to disconnect it via command")


    @commands.slash_command(name='pause', description="Pauses the Current Song")
    async def pause(self, msg):
        #"""
        #Pause the currently playing audio
        #`Ex:` s.pause
        #`Command:` pause()
        #"""
        #await msg.response.defer()
        if msg.author.voice is not None and msg.user.guild.voice_client is not None:
            if msg.user.guild.voice_client.is_paused() is True:
                return await msg.edit_original_message(content="Song is already paused")

            if msg.user.guild.voice_client.is_paused() is False:
                msg.user.guild.voice_client.pause()
                pause_message = await msg.edit_original_message(content="The song has been Paused!")
                return await pause_message.add_reaction(emoji='✅')



    @commands.slash_command(name='resume', description="Resumes the Current Song")
    async def resume(self, msg):
        #"""
        #Resume the currently paused audio
        #`Ex:` s.resume
        #`Command:` resume()
        #"""
        #await msg.response.defer()
        if msg.author.voice is not None and msg.user.guild.voice_client is not None:
            if msg.user.guild.voice_client.is_paused() is False:
                return await msg.edit_original_message("Song is already playing")

            if msg.user.guild.voice_client.is_paused() is True:
                msg.user.guild.voice_client.resume()
                resume_mesage = await msg.edit_original_message(content="The song has resumed playing")
                return await resume_mesage.add_reaction(emoji='✅')

 
    @commands.slash_command(name='queue', description="Display the songs coming up")
    async def _queue(self, msg):
        await msg.response.defer()
        if msg.user.guild.voice_client is not None:
            if msg.guild.id in self.player:
                if self.player[msg.guild.id]['queue']:
                    #print(self.player[msg.guild.id]['queue'])
                    emb = disnake.Embed(
                        colour=self.random_color, title='queue')
                    emb.set_footer(
                        text=f'Command used by {msg.author.name}', icon_url=msg.author.avatar.url)
                    for i in self.player[msg.guild.id]['queue']:
                        #print(f"{i['author'].author.name}")
                        #for some reason playlists do not come in a dictionary....need this function to allow for that.
                        if type(i['title']) is not dict:
                            new_title = i['title']
                        else:
                            new_title = i['title']['title']
                        #print(f"{i['title']}")
                        emb.add_field(
                            #name=f"**{i['author'].author.name}**", value=i['title'], inline=False)
                            name=f"{i['author'].author.name}", value=new_title, inline=False)
                    return await msg.edit_original_message(embed=emb) #, delete_after=120)

        return await msg.edit_original_message(content="No songs in queue")


    @commands.slash_command(name='join', description="Makes the Bot join the Voice Channel you are in")
    async def join(self, msg, *, channel: disnake.VoiceChannel = None):
        #"""
        #Make bot join a voice channel you are in if no channel is mentioned
        #`Ex:` .join (If voice channel name is entered, it'll join that one)
        #`Command:` join(channel:optional)
        #"""

        #await msg.response.defer()
        embed = disnake.Embed(color=disnake.Color.random(), timestamp=datetime.now())
        if channel is None:
            channel = msg.author.voice.channel
        if msg.user.guild.voice_client is not None:
            embed.add_field(name='Failure', value=f"Bot is already in a voice channel!")
            embed.set_footer(text="If you have any questions, suggestions or bug reports, please dm Popsicle")

            return await msg.edit_original_message(embed=embed)

        if msg.user.guild.voice_client is None:
            if channel is None:
                embed.add_field(name='Success', value=f"Successfully Joined {channel}!")
                send_message = await msg.edit_original_message(embed=embed)
                return await msg.author.voice.channel.connect(), await send_message.add_reaction(emoji='✅')

            embed.add_field(name='Success', value=f"Successfully Joined {channel}!")
            embed.set_footer(text="If you have any questions, suggestions or bug reports, please dm Popsicle")

            send_message = await msg.edit_original_message(embed=embed)
            return await msg.author.voice.channel.connect(), await send_message.add_reaction(emoji='✅')
            #return await channel.connect(), await msg.message.add_reaction(emoji='✅')

        else:
            if msg.user.guild.voice_client.is_playing() is False and not self.player[msg.guild.id]['queue']:
                return await msg.author.voice.channel.connect(), await msg.message.add_reaction(emoji='✅')

    @join.before_invoke
    async def before_join(self, msg):
        if msg.author.voice is None:
            return await msg.edit_original_message(content="You are not in a voice channel")

    @join.error
    async def join_error(self, msg, error):
        if isinstance(error, commands.BadArgument):
            return msg.channel.send(error)

        if error.args[0] == 'Command raised an exception: Exception: playing':
            return await msg.channel.send("**Please join the same voice channel as the bot to add song to queue**".title())


    @commands.slash_command(name='volume', description='Adjust the Volume of the Bot for Everyone in the Voice Channel')
    async def volume(self, msg, vol: int):

        #await msg.response.defer()
        if vol > 200:
            vol = 200
        vol = vol/100
        if msg.author.voice is not None:
            if msg.user.guild.voice_client is not None:
                if msg.user.guild.voice_client.channel == msg.author.voice.channel and msg.user.guild.voice_client.is_playing() is True:
                    msg.user.guild.voice_client.source.volume = vol
                    self.player[msg.guild.id]['volume'] = vol
                    volume_metric = vol * 100
                    volume_metric = str(volume_metric)
                    #strip off the decimal value for better formatting
                    volume_metric = volume_metric.split('.', 1)[0]
                    embed = disnake.Embed(
                    colour=self.random_color)
                    embed.add_field(name='Volume', value=f"volume has been adjusted to {volume_metric}")
                    embed.set_footer(
                    text=f'Requested by {msg.author.display_name}', icon_url=msg.author.avatar.url)
                    volume_message = await msg.edit_original_message(embed=embed)
                    # if (msg.guild.id) in self.music:
                    #     self.music[str(msg.guild.id)]['vol']=vol
                    return await volume_message.add_reaction(emoji='✅')

        return await msg.edit_original_message(content="**Please join the same voice channel as the bot to use this command**".title()) #, delete_after=30)


    @commands.slash_command(name='np', description="shows the current playing song")
    async def now_playing_(self, ctx):
        """Display information about the currently playing song."""
        await ctx.response.defer()
        vc = ctx.user.guild.voice_client
        #tuple_access_test = tuple_access.webpage_url
        if not vc or not vc.is_connected():
            embed = disnake.Embed(title="", description="I'm not connected to a voice channel", color=disnake.Color.random())
            return await ctx.send(embed=embed)

        #player = self.player(ctx)
        if  len(self.player) ==0:
            embed = disnake.Embed(title="", description="I am currently not playing anything", color=disnake.Color.random())
            return await ctx.send(embed=embed)
        
        seconds = vc.source.duration % (24 * 3600) 
        hour = seconds // 3600
        seconds %= 3600
        minutes = seconds // 60
        seconds %= 60
        if hour > 0:
            duration = "%dh %02dm %02ds" % (hour, minutes, seconds)
        else:
            duration = "%02dm %02ds" % (minutes, seconds)

        url = vc.source.data['webpage_url']
        embed = disnake.Embed(colour=self.random_color, title='Now Playing',
                            description=vc.source.title, url=url)
        embed.set_thumbnail(url=vc.source.thumbnail)
        embed.add_field(name='Duration', value=duration)
        embed.set_footer(
            text=f'Requested by {ctx.author.display_name}', icon_url=ctx.author.avatar.url)

        #vc.source.data.webpage_url}
        #embed = disnake.Embed(title="",  description = f'[{url}]',color=disnake.Color.random())
        #embed.set_thumbnail(url=url)
        #embed.add_field(name=song_name, value =vc.source.data['webpage_url'])
        #embed.set_author(icon_url=self.bot.user.avatar.url, name=f"Now Playing 🎶")
        #embed.set_footer(
                        #text=f'Command used by {ctx.author.display_name}', icon_url=ctx.author.avatar.url)
 
        #await ctx.send("{ }".format(url), embed=embed)
        await ctx.edit_original_message( embed=embed)
    @volume.error
    async def volume_error(self, msg,error):
        if isinstance(error, commands.MissingPermissions):
            return await msg.channel.send("Manage channels or admin perms required to change volume", delete_after=30)

    #A quick way to delete messages on the server without MEE6.
    @commands.slash_command(name="clear_messages",description='Purge messages based on the number of messages specified.',
    options=[disnake.Option(name='limit',
    description='Select the number of messages to delete', required=True)])
    async def purge(self,ctx, limit):
        #"""Purge messages based on the number of messages specified."""
        #logger.info('purge', extra={'ctx': ctx})
     
        user_id=ctx.author.id
        def check_msg(msg):
            if msg.id == ctx.channel.last_message_id:
                return False
            #if ctx.author_id is not None:
            #if msg.author.id != ctx.author_id:
                #return False
            return True
        limit=int(limit)
        #add one to the limit since we prevent deleting the interaction message.
        limit_adjust=limit+1
        limit2=str(limit)
        deleted = await ctx.channel.purge(limit=limit_adjust, check=check_msg)
        num = str(len(deleted))
        msg = await ctx.edit_original_message(content='I Deleted '+ limit2 +' ' + 'messages!')
        #await ctx.response.followup
        time.sleep(5)
        #await msg.delete()

    #A quick way to test server ping
    @commands.slash_command(name="latency_test",description='Get Latency stats of the server you are connected to')
    #@commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def latency_ping(self,ctx):
        await ctx.response.defer()
        start_time = time.time()
        message = await ctx.edit_original_message(content="Testing Ping...")
        end_time = time.time()
        await ctx.edit_original_message(content=f"Pong! {round(ctx.bot.latency * 1000)}ms\nAPI: {round((end_time - start_time) * 1000)}ms")
  

