# User configuration
DISCORD_BOT_TOKEN     = '<your_bot_token>'
DISCORD_USER_OWNER    = 000000000000000000 # ID of the user to follow
GRACE_PERIOD_FOR_MUTE = 6000
PROC_MEMORY_POLL_RATE = 250

# Stuff that might change between game updates

ADDR_BASE_OFFSET = 0x00DA5ACC
ADDR_OFFSETS     = [0x5C, 0x00, 0x98, 0x0C]

# Implementation
import asyncio
import discord
import os
import time
import pymem

GRACE_PERIOD_FOR_MUTE_IN_SECONDS = GRACE_PERIOD_FOR_MUTE / 1000
PROC_MEMORY_POLL_RATE_IN_SECONDS = PROC_MEMORY_POLL_RATE / 1000

def PtrFromOffsets(pm, basePtr, offsets):
	for v in offsets:
		basePtr = pm.read_int(basePtr)
		basePtr += v
	return basePtr

def GetModuleByName(pm, modName):
	for module in list(pm.list_modules()):
		if module.name == modName:
			return module

class AmongUsBot(discord.Client):
	def __init__(self, pm, addr_base):
		super().__init__()
		self.pm = pm
		self.addr_base = addr_base
	
	def GetOwner(self):
		for guild in self.guilds:
			member = guild.get_member(DISCORD_USER_OWNER)
			if member != None:
				return member
		return None
	
	async def mute_one(self, member):
		if member.voice != None:
			await member.edit(mute=True)
	
	async def unmute_one(self, member):
		if member.voice != None:
			await member.edit(mute=False)
	
	async def mute_everybody(self):
		for member in self.vc_member_list:
			await self.mute_one(member)
	
	async def unmute_everybody(self):
		for member in self.vc_member_list:
			await self.unmute_one(member)
	
	async def mute_everybody_with_delay(self):
		try:
			await asyncio.sleep(GRACE_PERIOD_FOR_MUTE_IN_SECONDS)
		except asyncio.CancelledError:
			return
		await self.mute_everybody()
	
	async def poll_game_memory(self):
		while True:
			try:
				addr = PtrFromOffsets(self.pm, self.addr_base, ADDR_OFFSETS)
				# 0 == Menu
				# 1 == In-Game
				# 2 == Lobby
				state = self.pm.read_int(addr)
				is_discussing = ((self.pm.read_int(addr - 0x80) - 3) % 3) == 1
				self.should_talk_previous = self.should_talk
				self.should_talk = is_discussing or state != 1
			except:
				print('Game was closed or an error reading memory occured.')
				self.loop.stop()
				return
			if self.should_talk_previous != self.should_talk:
				if self.should_talk == True:
					if self.mute_everybody_task != None and self.mute_everybody_task.done() == False:
						self.mute_everybody_task.cancel()
					self.loop.create_task(self.unmute_everybody())
				else:
					self.mute_everybody_task = self.loop.create_task(self.mute_everybody_with_delay())
			await asyncio.sleep(PROC_MEMORY_POLL_RATE_IN_SECONDS)
	
	async def on_ready(self):
		print('Logged on as {0}!'.format(self.user))
		owner = self.GetOwner()
		self.owner_channel = owner.voice.channel if owner.voice != None else None
		self.vc_member_list = self.owner_channel.members if self.owner_channel != None else None
		self.should_talk_previous = False
		self.should_talk = False
		self.mute_everybody_task = None
		self.loop.create_task(self.poll_game_memory())
	
	async def on_voice_state_update(self, member, before, after):
		if member.id == DISCORD_USER_OWNER:
			previous_channel = self.owner_channel
			self.owner_channel = after.channel
			if previous_channel != self.owner_channel:
				await self.unmute_everybody()
				if self.owner_channel != None:
					self.vc_member_list = self.owner_channel.members
				else:
					self.vc_member_list = []
		elif self.owner_channel != None and before.channel != after.channel: # If channel changed
			if after.channel == self.owner_channel: # If new channel is our channel
				if member not in self.vc_member_list:
					self.vc_member_list.append(member)
					if self.should_talk == False:
						await self.mute_one(member)
			elif before.channel == self.owner_channel: # If old channel was our channel
				if member in self.vc_member_list:
					self.vc_member_list.remove(member)
					await self.unmute_one(member)

if __name__ == '__main__':
	try:
		pm = pymem.Pymem('Among Us.exe')
		mod = GetModuleByName(pm, 'GameAssembly.dll')
		addr_base = mod.lpBaseOfDll + ADDR_BASE_OFFSET
		bot = AmongUsBot(pm, addr_base)
		bot.run(DISCORD_BOT_TOKEN)
	except pymem.exception.ProcessNotFound:
		print('Unable to open Among Us game process. Are you running the game?')
	finally:
		os.system('pause')

