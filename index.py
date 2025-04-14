import discord
from discord.ext import commands
import os
import json
import asyncio
import datetime
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

DATA_DIR = "data"
APPLICATIONS_FILE = f"{DATA_DIR}/applications.json"
TICKETS_FILE = f"{DATA_DIR}/tickets.json"

os.makedirs(DATA_DIR, exist_ok=True)

def load_applications():
    if os.path.exists(APPLICATIONS_FILE):
        with open(APPLICATIONS_FILE, 'r') as f:
            return json.load(f)
    return {"applications": [], "settings": {"category_id": None, "log_channel_id": None}}

def load_tickets():
    if os.path.exists(TICKETS_FILE):
        with open(TICKETS_FILE, 'r') as f:
            return json.load(f)
    return {"tickets": [], "settings": {"category_id": None, "log_channel_id": None}}

def save_applications(data):
    with open(APPLICATIONS_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def save_tickets(data):
    with open(TICKETS_FILE, 'w') as f:
        json.dump(data, f, indent=4)

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    await bot.change_presence(activity=discord.Game(name="!help for commands"))

class ApplicationSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.applications = load_applications()
        
    @commands.group(name="application", aliases=["apply"])
    async def application(self, ctx):
        """Application system commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send("Please use a subcommand: `setup`, `start`, `list`, `view`, `accept`, `deny`")
    
    @application.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def setup_applications(self, ctx, category: discord.CategoryChannel = None, log_channel: discord.TextChannel = None):
        """Setup the application system"""
        if category:
            self.applications["settings"]["category_id"] = category.id
        if log_channel:
            self.applications["settings"]["log_channel_id"] = log_channel.id
        
        save_applications(self.applications)
        
        await ctx.send(f"Application system setup complete!\n"
                      f"Category: {category.name if category else 'Not set'}\n"
                      f"Log Channel: {log_channel.mention if log_channel else 'Not set'}")
    
    @application.command(name="start")
    async def start_application(self, ctx):
        """Start a new application"""
        if not self.applications["settings"]["category_id"]:
            return await ctx.send("The application system has not been set up yet!")
        
        category = ctx.guild.get_channel(self.applications["settings"]["category_id"])
        if not category:
            return await ctx.send("Application category not found. Please ask an admin to set it up again.")
        
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        channel = await category.create_text_channel(f"application-{ctx.author.name}", overwrites=overwrites)
        
        application_id = str(len(self.applications["applications"]) + 1)
        application_data = {
            "id": application_id,
            "user_id": ctx.author.id,
            "channel_id": channel.id,
            "status": "open",
            "created_at": datetime.datetime.now().isoformat(),
            "responses": {}
        }
        
        self.applications["applications"].append(application_data)
        save_applications(self.applications)
        
        embed = discord.Embed(
            title="Application Started",
            description=f"Welcome to your application, {ctx.author.mention}!\n\n"
                       f"Please answer the following questions one by one.",
            color=discord.Color.blue()
        )
        
        await channel.send(embed=embed)
        
        questions = [
            "What is your name?",
            "How old are you?",
            "Why do you want to join our team?",
            "What experience do you have?",
            "How many hours per week can you dedicate?"
        ]
        
        for i, question in enumerate(questions):
            embed = discord.Embed(
                title=f"Question {i+1}/{len(questions)}",
                description=question,
                color=discord.Color.blue()
            )
            await channel.send(embed=embed)
            
            try:
                response = await self.bot.wait_for(
                    'message',
                    check=lambda m: m.author == ctx.author and m.channel == channel,
                    timeout=300.0
                )
                
                application_data["responses"][f"question_{i+1}"] = response.content
                save_applications(self.applications)
                
                await channel.send("✅ Answer recorded!")
                
            except asyncio.TimeoutError:
                await channel.send("You took too long to respond. You can continue your application later.")
                break
        
        if len(application_data["responses"]) == len(questions):
            embed = discord.Embed(
                title="Application Completed",
                description="Thank you for completing your application! Our staff will review it soon.",
                color=discord.Color.green()
            )
            await channel.send(embed=embed)
            
            if self.applications["settings"]["log_channel_id"]:
                log_channel = ctx.guild.get_channel(self.applications["settings"]["log_channel_id"])
                if log_channel:
                    embed = discord.Embed(
                        title="New Application Submitted",
                        description=f"User: {ctx.author.mention}\nApplication ID: {application_id}",
                        color=discord.Color.blue()
                    )
                    embed.add_field(name="Review", value=f"Use `!application view {application_id}` to review")
                    await log_channel.send(embed=embed)
    
    @application.command(name="view")
    @commands.has_permissions(administrator=True)
    async def view_application(self, ctx, application_id: str):
        """View an application by ID"""
        application = None
        for app in self.applications["applications"]:
            if app["id"] == application_id:
                application = app
                break
        
        if not application:
            return await ctx.send("Application not found!")
        
        user = ctx.guild.get_member(application["user_id"])
        user_name = user.name if user else f"User ID: {application['user_id']}"
        
        embed = discord.Embed(
            title=f"Application #{application_id}",
            description=f"Submitted by: {user_name}\nStatus: {application['status']}",
            color=discord.Color.blue()
        )
        
        for question, answer in application["responses"].items():
            q_num = question.split("_")[1]
            embed.add_field(name=f"Question {q_num}", value=answer, inline=False)
        
        embed.add_field(
            name="Actions",
            value=f"Accept: `!application accept {application_id}`\nDeny: `!application deny {application_id}`",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @application.command(name="accept")
    @commands.has_permissions(administrator=True)
    async def accept_application(self, ctx, application_id: str, *, reason: str = "No reason provided"):
        """Accept an application"""
        application = None
        for i, app in enumerate(self.applications["applications"]):
            if app["id"] == application_id:
                application = app
                application_index = i
                break
        
        if not application:
            return await ctx.send("Application not found!")
        
        if application["status"] != "open":
            return await ctx.send(f"This application is already {application['status']}!")
        
        self.applications["applications"][application_index]["status"] = "accepted"
        self.applications["applications"][application_index]["closed_by"] = ctx.author.id
        self.applications["applications"][application_index]["close_reason"] = reason
        save_applications(self.applications)
        
        user = ctx.guild.get_member(application["user_id"])
        if user:
            try:
                embed = discord.Embed(
                    title="Application Accepted!",
                    description=f"Your application has been accepted!\nReason: {reason}",
                    color=discord.Color.green()
                )
                await user.send(embed=embed)
            except:
                pass
        
        channel = ctx.guild.get_channel(application["channel_id"])
        if channel:
            embed = discord.Embed(
                title="Application Accepted",
                description=f"This application has been accepted by {ctx.author.mention}.\nReason: {reason}",
                color=discord.Color.green()
            )
            await channel.send(embed=embed)
        
        await ctx.send(f"Application #{application_id} has been accepted!")
    
    @application.command(name="deny")
    @commands.has_permissions(administrator=True)
    async def deny_application(self, ctx, application_id: str, *, reason: str = "No reason provided"):
        """Deny an application"""
        application = None
        for i, app in enumerate(self.applications["applications"]):
            if app["id"] == application_id:
                application = app
                application_index = i
                break
        
        if not application:
            return await ctx.send("Application not found!")
        
        if application["status"] != "open":
            return await ctx.send(f"This application is already {application['status']}!")
        
        self.applications["applications"][application_index]["status"] = "denied"
        self.applications["applications"][application_index]["closed_by"] = ctx.author.id
        self.applications["applications"][application_index]["close_reason"] = reason
        save_applications(self.applications)
        
        user = ctx.guild.get_member(application["user_id"])
        if user:
            try:
                embed = discord.Embed(
                    title="Application Denied",
                    description=f"Your application has been denied.\nReason: {reason}",
                    color=discord.Color.red()
                )
                await user.send(embed=embed)
            except:
                pass
        
        channel = ctx.guild.get_channel(application["channel_id"])
        if channel:
            embed = discord.Embed(
                title="Application Denied",
                description=f"This application has been denied by {ctx.author.mention}.\nReason: {reason}",
                color=discord.Color.red()
            )
            await channel.send(embed=embed)
        
        await ctx.send(f"Application #{application_id} has been denied!")

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tickets = load_tickets()
    
    @commands.group(name="ticket")
    async def ticket(self, ctx):
        """Ticket system commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send("Please use a subcommand: `setup`, `create`, `close`, `add`, `remove`")
    
    @ticket.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def setup_tickets(self, ctx, category: discord.CategoryChannel = None, log_channel: discord.TextChannel = None):
        """Setup the ticket system"""
        if category:
            self.tickets["settings"]["category_id"] = category.id
        if log_channel:
            self.tickets["settings"]["log_channel_id"] = log_channel.id
        
        save_tickets(self.tickets)
        
        embed = discord.Embed(
            title="Support Tickets",
            description="React with 🎫 to create a new support ticket",
            color=discord.Color.blue()
        )
        
        panel_message = await ctx.send(embed=embed)
        await panel_message.add_reaction("🎫")
        
        self.tickets["settings"]["panel_message_id"] = panel_message.id
        self.tickets["settings"]["panel_channel_id"] = panel_message.channel.id
        save_tickets(self.tickets)
        
        await ctx.send(f"Ticket system setup complete!\n"
                      f"Category: {category.name if category else 'Not set'}\n"
                      f"Log Channel: {log_channel.mention if log_channel else 'Not set'}")
    
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return
        
        if not self.tickets["settings"].get("panel_message_id"):
            return
        
        if (payload.message_id == self.tickets["settings"]["panel_message_id"] and 
            str(payload.emoji) == "🎫"):
            
            guild = self.bot.get_guild(payload.guild_id)
            if not guild:
                return
            
            member = guild.get_member(payload.user_id)
            if not member:
                return
            
            channel = guild.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            await message.remove_reaction(payload.emoji, member)
            
            await self.create_ticket(guild, member)
    
    async def create_ticket(self, guild, member):
        if not self.tickets["settings"]["category_id"]:
            return
        
        category = guild.get_channel(self.tickets["settings"]["category_id"])
        if not category:
            return
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        if "support_role_id" in self.tickets["settings"] and self.tickets["settings"]["support_role_id"]:
            support_role = guild.get_role(self.tickets["settings"]["support_role_id"])
            if support_role:
                overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        ticket_id = str(len(self.tickets["tickets"]) + 1).zfill(4)
        channel_name = f"ticket-{ticket_id}"
        
        channel = await category.create_text_channel(channel_name, overwrites=overwrites)
        
        ticket_data = {
            "id": ticket_id,
            "user_id": member.id,
            "channel_id": channel.id,
            "status": "open",
            "created_at": datetime.datetime.now().isoformat(),
            "messages": []
        }
        
        self.tickets["tickets"].append(ticket_data)
        save_tickets(self.tickets)
        
        embed = discord.Embed(
            title=f"Ticket #{ticket_id}",
            description=f"Welcome {member.mention}! Please describe your issue and a staff member will assist you shortly.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Type !ticket close to close this ticket when resolved")
        
        control_row = discord.ui.ActionRow(
            discord.ui.Button(style=discord.ButtonStyle.danger, label="Close Ticket", custom_id=f"close_ticket_{ticket_id}")
        )
        
        await channel.send(embed=embed, components=[control_row])
        
        if self.tickets["settings"]["log_channel_id"]:
            log_channel = guild.get_channel(self.tickets["settings"]["log_channel_id"])
            if log_channel:
                embed = discord.Embed(
                    title="New Ticket Created",
                    description=f"User: {member.mention}\nTicket ID: #{ticket_id}\nChannel: {channel.mention}",
                    color=discord.Color.blue()
                )
                await log_channel.send(embed=embed)
    
    @ticket.command(name="create")
    async def create_ticket_command(self, ctx):
        """Create a new support ticket"""
        await self.create_ticket(ctx.guild, ctx.author)
        await ctx.send("Your ticket has been created!", delete_after=5)
    
    @ticket.command(name="close")
    async def close_ticket(self, ctx, *, reason: str = "Ticket resolved"):
        """Close a ticket"""
        ticket_data = None
        for ticket in self.tickets["tickets"]:
            if ticket["channel_id"] == ctx.channel.id and ticket["status"] == "open":
                ticket_data = ticket
                break
        
        if not ticket_data:
            return await ctx.send("This command can only be used in an open ticket channel!")
        
        ticket_data["status"] = "closed"
        ticket_data["closed_by"] = ctx.author.id
        ticket_data["close_reason"] = reason
        ticket_data["closed_at"] = datetime.datetime.now().isoformat()
        save_tickets(self.tickets)
        
        embed = discord.Embed(
            title="Ticket Closed",
            description=f"This ticket has been closed by {ctx.author.mention}.\nReason: {reason}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        
        if self.tickets["settings"]["log_channel_id"]:
            log_channel = ctx.guild.get_channel(self.tickets["settings"]["log_channel_id"])
            if log_channel:
                user = ctx.guild.get_member(ticket_data["user_id"])
                user_mention = user.mention if user else f"User ID: {ticket_data['user_id']}"
                
                embed = discord.Embed(
                    title=f"Ticket #{ticket_data['id']} Closed",
                    description=f"Ticket from {user_mention} was closed by {ctx.author.mention}.\nReason: {reason}",
                    color=discord.Color.red()
                )
                await log_channel.send(embed=embed)
        
        await ctx.send("This channel will be archived in 5 seconds...")
        await asyncio.sleep(5)
        
        try:
            messages = []
            async for message in ctx.channel.history(limit=500, oldest_first=True):
                if not message.author.bot or message.author == self.bot.user:
                    messages.append(f"[{message.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {message.author.name}: {message.content}")
            
            transcript = "\n".join(messages)
            
            transcript_file = f"{DATA_DIR}/transcript-{ticket_data['id']}.txt"
            with open(transcript_file, "w", encoding="utf-8") as f:
                f.write(f"Ticket #{ticket_data['id']} Transcript\n")
                f.write(f"Created by: {user_mention if 'user' in locals() else ticket_data['user_id']}\n")
                f.write(f"Closed by: {ctx.author.name}\n")
                f.write(f"Reason: {reason}\n")
                f.write("-" * 50 + "\n\n")
                f.write(transcript)
            
            if self.tickets["settings"]["log_channel_id"]:
                log_channel = ctx.guild.get_channel(self.tickets["settings"]["log_channel_id"])
                if log_channel:
                    await log_channel.send(
                        f"Transcript for Ticket #{ticket_data['id']}",
                        file=discord.File(transcript_file)
                    )
            
            await ctx.channel.delete()
            
        except Exception as e:
            await ctx.send(f"Error archiving channel: {e}")
    
    @ticket.command(name="add")
    async def add_to_ticket(self, ctx, user: discord.Member):
        """Add a user to the current ticket"""
        ticket_data = None
        for ticket in self.tickets["tickets"]:
            if ticket["channel_id"] == ctx.channel.id and ticket["status"] == "open":
                ticket_data = ticket
                break
        
        if not ticket_data:
            return await ctx.send("This command can only be used in an open ticket channel!")
        
        await ctx.channel.set_permissions(user, read_messages=True, send_messages=True)
        await ctx.send(f"{user.mention} has been added to the ticket.")
    
    @ticket.command(name="remove")
    async def remove_from_ticket(self, ctx, user: discord.Member):
        """Remove a user from the current ticket"""
        ticket_data = None
        for ticket in self.tickets["tickets"]:
            if ticket["channel_id"] == ctx.channel.id and ticket["status"] == "open":
                ticket_data = ticket
                break
        
        if not ticket_data:
            return await ctx.send("This command can only be used in an open ticket channel!")
        
        if user.id == ticket_data["user_id"]:
            return await ctx.send("You cannot remove the ticket creator!")
        

        await ctx.channel.set_permissions(user, overwrite=None)
        await ctx.send(f"{user.mention} has been removed from the ticket.")
    
    @ticket.command(name="setsuprole")
    @commands.has_permissions(administrator=True)
    async def set_support_role(self, ctx, role: discord.Role):
        """Set the support team role for tickets"""
        self.tickets["settings"]["support_role_id"] = role.id
        save_tickets(self.tickets)
        await ctx.send(f"Support role set to {role.mention}!")

@bot.event
async def setup_hook():
    """Setup hook that runs when the bot is first connected"""
    await bot.add_cog(ApplicationSystem(bot))
    await bot.add_cog(TicketSystem(bot))

@bot.event
async def on_message(message):
    if message.guild is None:
        return
    
    await bot.process_commands(message)

if __name__ == '__main__':
    if not TOKEN:
        print("No Discord token found. Please set the DISCORD_TOKEN environment variable.")
        exit(1)
    
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("Invalid Discord token. Please check your DISCORD_TOKEN environment variable.")
    except Exception as e:
        print(f"Error starting bot: {e}")
