import discord
from discord.ext import commands
from flask import Flask, request
from threading import Thread
import json
import asyncio
import os

from keep_alive import keep_alive
keep_alive()
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

event_message = "Default event message."
event_role_name = "Notified about Events"
opted_in_users = set()
dm_roles = set()

# Load and Save Functions
def load_event_message():
    global event_message
    if os.path.exists("event_message.json"):
        with open("event_message.json", "r") as f:
            event_message = json.load(f).get("message", event_message)

def save_event_message(message):
    with open("event_message.json", "w") as f:
        json.dump({"message": message}, f)

def load_opted_in_users():
    global opted_in_users
    if os.path.exists("opted_in_users.json"):
        with open("opted_in_users.json", "r") as f:
            opted_in_users = set(json.load(f))

def save_opted_in_users():
    with open("opted_in_users.json", "w") as f:
        json.dump(list(opted_in_users), f)

def load_dm_roles():
    global dm_roles
    if os.path.exists("dm_roles.json"):
        with open("dm_roles.json", "r") as f:
            dm_roles = set(json.load(f))

def save_dm_roles():
    with open("dm_roles.json", "w") as f:
        json.dump(list(dm_roles), f)

@bot.event
async def on_ready():
    load_event_message()
    load_opted_in_users()
    load_dm_roles()
    print(f"Bot ready: {bot.user}")

def is_admin(ctx):
    return ctx.author.guild_permissions.administrator

# Opt-in / Opt-out
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

# Admin: Set message
@bot.command()
async def setmessage(ctx, *, msg):
    if not is_admin(ctx):
        return await ctx.send("Admins only.")
    global event_message
    event_message = msg
    save_event_message(msg)
    await ctx.send("Event message saved.")

# Admin: Preview
@bot.command()
async def previewevent(ctx):
    if not is_admin(ctx):
        return await ctx.send("Admins only.")
    try:
        await ctx.author.send(event_message, allowed_mentions=discord.AllowedMentions(roles=True))
        await ctx.send("Preview sent to your DMs.")
    except discord.Forbidden:
        await ctx.send("I can't DM you.")

# Admin: Announcement
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
        for role_name in dm_roles.union({event_role_name}):
            role = discord.utils.get(guild.roles, name=role_name)
            if role:
                for member in role.members:
                    if member.id not in opted_in_users:
                        try:
                            await member.send(event_message, allowed_mentions=allowed)
                            count += 1
                        except:
                            continue
    await ctx.send(f"Message sent to {count} users.")

# Admin: Add DM role
@bot.command()
async def addrole(ctx, *, role_name):
    if not is_admin(ctx):
        return await ctx.send("Admins only.")
    dm_roles.add(role_name)
    save_dm_roles()
    await ctx.send(f"Added role '{role_name}' to DM list.")

# Admin: Remove DM role
@bot.command()
async def removerole(ctx, *, role_name):
    if not is_admin(ctx):
        return await ctx.send("Admins only.")
    if role_name in dm_roles:
        dm_roles.remove(role_name)
        save_dm_roles()
        await ctx.send(f"Removed role '{role_name}' from DM list.")
    else:
        await ctx.send("Role not in DM list.")

# Admin: List DM roles
@bot.command()
async def listroles(ctx):
    if not is_admin(ctx):
        return await ctx.send("Admins only.")
    if dm_roles:
        roles = "\n".join(dm_roles)
        await ctx.send(f"Roles to be DMed:\n{roles}")
    else:
        await ctx.send("No roles are currently set to receive DMs.")

# Admin: Status
@bot.command()
async def status(ctx):
    if not is_admin(ctx):
        return await ctx.send("Admins only.")
    embed = discord.Embed(title="Bot Status", color=discord.Color.green())
    embed.add_field(name="Servers", value=str(len(bot.guilds)))
    embed.add_field(name="Opted-in Users", value=str(len(opted_in_users)))
    embed.add_field(name="Online", value="Yes")
    await ctx.send(embed=embed)

# Help
@bot.command()
async def helpme(ctx):
    embed = discord.Embed(
        title="Bot Help",
        description="Here are the commands you can use:",
        color=discord.Color.blue()
    )
    embed.add_field(name="!notifyme", value="Subscribe to event DMs", inline=False)
    embed.add_field(name="!stopnotify", value="Unsubscribe", inline=False)
    embed.add_field(name="!setmessage [text]", value="Set event message (admin)", inline=False)
    embed.add_field(name="!previewevent", value="Preview in your DMs (admin)", inline=False)
    embed.add_field(name="!announceevent", value="Send to all opted-in/role users (admin)", inline=False)
    embed.add_field(name="!eventembed [json]", value="Send Discohook-style embed to yourself", inline=False)
    embed.add_field(name="!status", value="Bot status (admin)", inline=False)
    embed.add_field(name="!addrole [role name]", value="Add role to DM list (admin)", inline=False)
    embed.add_field(name="!removerole [role name]", value="Remove role from DM list (admin)", inline=False)
    embed.add_field(name="!listroles", value="List roles in DM list (admin)", inline=False)
    await ctx.send(embed=embed)

# Admin: Embed
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

# Flask Dashboard
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
        for role_name in dm_roles.union({event_role_name}):
            role = discord.utils.get(guild.roles, name=role_name)
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
    <p>Users with roles: {rolecount}</p>
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
        for role_name in dm_roles.union({event_role_name}):
            role = discord.utils.get(guild.roles, name=role_name)
            if role:
                for m in role.members:
                    if m.id not in opted_in_users:
                        try:
                            await m.send(event_message, allowed_mentions=allowed)
                            count += 1
                        except:
                            continue
    return count

# Start bot
bot.run(os.getenv("DISCORD_BOT_TOKEN"))
