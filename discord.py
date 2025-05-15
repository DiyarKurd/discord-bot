import discord
from discord.ext import commands
from flask import Flask, request
from threading import Thread
import json
import asyncio
import os

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

event_message = "Default event message."
event_role_name = "Notified about Events"
opted_in_users = set()

# Load event message from file
def load_event_message():
    global event_message
    if os.path.exists("event_message.json"):
        with open("event_message.json", "r") as f:
            event_message = json.load(f).get("message", event_message)

def save_event_message(message):
    with open("event_message.json", "w") as f:
        json.dump({"message": message}, f)

# Load opted-in users
def load_opted_in_users():
    global opted_in_users
    if os.path.exists("opted_in_users.json"):
        with open("opted_in_users.json", "r") as f:
            opted_in_users = set(json.load(f))

def save_opted_in_users():
    with open("opted_in_users.json", "w") as f:
        json.dump(list(opted_in_users), f)

@bot.event
async def on_ready():
    load_event_message()
    load_opted_in_users()
    print(f"Bot ready: {bot.user}")

# Admin check
def is_admin(ctx):
    return ctx.author.guild_permissions.administrator

# Opt-in and Opt-out
@bot.command()
async def notifyme(ctx):
    opted_in_users.add(ctx.author.id)
    save_opted_in_users()
    await ctx.send("You're now subscribed to event notifications!")

@bot.command()
async def stopnotify(ctx):
    opted_in_users.discard(ctx.author.id)
    save_opted_in_users()
    await ctx.send("You have unsubscribed from notifications.")

# Admin command: set message
@bot.command()
async def setmessage(ctx, *, msg):
    if not is_admin(ctx):
        return await ctx.send("Admins only.")
    global event_message
    event_message = msg
    save_event_message(msg)
    await ctx.send("Event message saved.")

# Admin command: preview
@bot.command()
async def previewevent(ctx):
    if not is_admin(ctx):
        return await ctx.send("Admins only.")
    try:
        await ctx.author.send(event_message, allowed_mentions=discord.AllowedMentions(roles=True))
        await ctx.send("Preview sent to your DMs.")
    except discord.Forbidden:
        await ctx.send("I can't DM you.")

# Admin command: send to all
@bot.command()
async def announceevent(ctx):
    if not is_admin(ctx):
        return await ctx.send("Admins only.")
    count = 0
    allowed = discord.AllowedMentions(roles=True)
    for user_id in opted_in_users:
        user = bot.get_user(user_id)
        if user:
            try:
                await user.send(event_message, allowed_mentions=allowed)
                count += 1
            except:
                continue
    for guild in bot.guilds:
        role = discord.utils.get(guild.roles, name=event_role_name)
        if role:
            for member in role.members:
                if member.id not in opted_in_users:
                    try:
                        await member.send(event_message, allowed_mentions=allowed)
                        count += 1
                    except:
                        continue
    await ctx.send(f"Message sent to {count} users.")

# Help command
@bot.command()
async def helpme(ctx):
    await ctx.send("""
!notifyme - Subscribe to event DMs  
!stopnotify - Unsubscribe  
!setmessage [text] - Set the event message (admin)  
!previewevent - Preview in your DM (admin)  
!announceevent - Send to all opted-in/role users (admin)  
!eventembed [json] - Send Discohook-style embed to yourself  
(you can also upload a .json file with this command)
""")

# Embed command
@bot.command()
async def eventembed(ctx, *, json_code=None):
    if not is_admin(ctx):
        return await ctx.send("Admins only.")
    try:
        if not json_code:
            if ctx.message.attachments:
                a = ctx.message.attachments[0]
                if a.filename.endswith(".json"):
                    content = await a.read()
                    data = json.loads(content)
                else:
                    return await ctx.send("File must be .json")
            else:
                return await ctx.send("Please upload a .json file or paste JSON.")
        else:
            data = json.loads(json_code)

        if "embeds" in data:
            for e in data["embeds"]:
                embed = discord.Embed.from_dict(e)
                await ctx.author.send(embed=embed)
            await ctx.send("Embed sent to your DM.")
        else:
            await ctx.send("Invalid embed JSON.")
    except Exception as e:
        await ctx.send(f"Error: {e}")

# Flask server for UptimeRobot + dashboard
app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def dashboard():
    global event_message
    msg = ""
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save":
            event_message = request.form.get("event_message", "")
            save_event_message(event_message)
            msg = "Saved!"
        elif action == "preview":
            asyncio.run_coroutine_threadsafe(preview_event_to_owner(), bot.loop)
            msg = "Preview sent."
        elif action == "send":
            future = asyncio.run_coroutine_threadsafe(send_event_to_all(), bot.loop)
            try:
                total = future.result(timeout=20)
                msg = f"Sent to {total} users."
            except:
                msg = "Failed to send."
    optin = len(opted_in_users)
    rolecount = 0
    for guild in bot.guilds:
        role = discord.utils.get(guild.roles, name=event_role_name)
        if role:
            rolecount += len(role.members)
    html = f"""
    <html><body style='font-family:sans-serif;padding:2em;'>
    <h2>Bot Dashboard</h2>
    <form method="POST">
    <textarea name="event_message" style="width:100%;height:100px;">{event_message}</textarea><br>
    <button name="action" value="save">Save</button>
    <button name="action" value="preview">Preview to Owner</button>
    <button name="action" value="send">Send to All</button>
    </form>
    <p>{msg}</p>
    <hr>
    <p>Opted-in users: {optin}</p>
    <p>Users with role '{event_role_name}': {rolecount}</p>
    </body></html>
    """
    return html

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

# Dashboard helpers
async def preview_event_to_owner():
    owner = (await bot.application_info()).owner
    try:
        await owner.send(event_message, allowed_mentions=discord.AllowedMentions(roles=True))
    except:
        print("Preview failed")

async def send_event_to_all():
    count = 0
    allowed = discord.AllowedMentions(roles=True)
    for uid in opted_in_users:
        user = bot.get_user(uid)
        if user:
            try:
                await user.send(event_message, allowed_mentions=allowed)
                count += 1
            except:
                continue
    for guild in bot.guilds:
        role = discord.utils.get(guild.roles, name=event_role_name)
        if role:
            for m in role.members:
                if m.id not in opted_in_users:
                    try:
                        await m.send(event_message, allowed_mentions=allowed)
                        count += 1
                    except:
                        continue
    return count

# Start the bot
import os
bot.run(os.getenv("DISCORD_BOT_TOKEN"))
