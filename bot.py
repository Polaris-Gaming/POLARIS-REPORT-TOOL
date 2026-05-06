import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from sheets import (
    register_team,
    get_team,
    append_report,
    clear_teams,
    get_validated_players,
    refresh_validated_players_cache,
    set_team_closed_status,
    is_team_closed
)

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


async def player_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    try:
        players = get_validated_players(use_cache=True)

        current = current.strip().lower()

        if not current:
            matches = players[:25]
        else:
            starts_with = [name for name in players if name.lower().startswith(current)]
            contains = [name for name in players if current in name.lower() and name not in starts_with]
            matches = (starts_with + contains)[:25]

        return [app_commands.Choice(name=name, value=name) for name in matches]

    except Exception as e:
        print("AUTOCOMPLETE ERROR:", e)
        return []


class ReportModal(discord.ui.Modal):
    def __init__(self, team, map_number: int, map_name: str):
        super().__init__(title=f"Report - Team {team['Team Number']} | {map_name} Map {map_number}")
        self.team = team
        self.map_number = map_number
        self.map_name = map_name

        self.player1_input = discord.ui.TextInput(
            label=f"{team['Player 1']} Kills",
            required=True
        )
        self.player2_input = discord.ui.TextInput(
            label=f"{team['Player 2']} Kills",
            required=True
        )
        self.player3_input = discord.ui.TextInput(
            label=f"{team['Player 3']} Kills",
            required=True
        )
        self.player4_input = discord.ui.TextInput(
            label=f"{team['Player 4']} Kills",
            required=True
        )
        self.placement_input = discord.ui.TextInput(
            label="Placement",
            required=True
        )

        self.add_item(self.player1_input)
        self.add_item(self.player2_input)
        self.add_item(self.player3_input)
        self.add_item(self.player4_input)
        self.add_item(self.placement_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)

            append_report(
                reporter=interaction.user.name,
                team_number=self.team["Team Number"],
                map_number=self.map_number,
                map_name=self.map_name,
                p1_kills=int(self.player1_input.value),
                p2_kills=int(self.player2_input.value),
                p3_kills=int(self.player3_input.value),
                p4_kills=int(self.player4_input.value),
                placement=int(self.placement_input.value)
            )

            await interaction.followup.send(
                f"✅ Report submitted for Team {self.team['Team Number']} | {self.map_name} Map {self.map_number}",
                ephemeral=True
            )

        except ValueError:
            await interaction.followup.send(
                "❌ Kills and placement must be numbers only.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error: {e}",
                ephemeral=True
            )


@bot.tree.command(name="registerteam", description="Register a new team")
@app_commands.describe(
    player1="Select Player 1",
    player2="Select Player 2",
    player3="Select Player 3",
    player4="Select Player 4"
)
@app_commands.autocomplete(
    player1=player_autocomplete,
    player2=player_autocomplete,
    player3=player_autocomplete,
    player4=player_autocomplete
)
async def registerteam(
    interaction: discord.Interaction,
    player1: str,
    player2: str,
    player3: str,
    player4: str
):
    try:
        await interaction.response.defer(ephemeral=True)

        validated_players = get_validated_players(use_cache=True)
        validated_lookup = {name.lower(): name for name in validated_players}

        submitted = [player1, player2, player3, player4]

        normalized = []
        for player in submitted:
            key = player.strip().lower()
            if key not in validated_lookup:
                await interaction.followup.send(
                    f"❌ '{player}' is not in the validated player list.",
                    ephemeral=True
                )
                return
            normalized.append(validated_lookup[key])

        if len(set(name.lower() for name in normalized)) != 4:
            await interaction.followup.send(
                "❌ Each player must be unique. You selected a duplicate.",
                ephemeral=True
            )
            return

        new_team_number = register_team(
            normalized[0],
            normalized[1],
            normalized[2],
            normalized[3]
        )

        await interaction.followup.send(
            f"🎉 **Team Registered Successfully!**\n\n"
            f"**Team Number:** {new_team_number}\n"
            f"**Players:** {normalized[0]}, {normalized[1]}, {normalized[2]}, {normalized[3]}",
            ephemeral=True
        )

    except Exception as e:
        await interaction.followup.send(
            f"❌ Error: {e}",
            ephemeral=True
        )


@bot.tree.command(name="refreshplayers", description="Refresh validated player list from Google Sheets")
@app_commands.checks.has_permissions(administrator=True)
async def refreshplayers(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=True)
        count = refresh_validated_players_cache()
        await interaction.followup.send(
            f"✅ Refreshed validated players cache. Loaded {count} players.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(
            f"❌ Error refreshing player list: {e}",
            ephemeral=True
        )


@bot.tree.command(name="closeteam", description="Manually close a team")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(team_number="Enter the team number to close")
async def closeteam(interaction: discord.Interaction, team_number: str):
    try:
        await interaction.response.defer(ephemeral=True)

        team = get_team(team_number)
        if not team:
            await interaction.followup.send(
                "❌ Team not found.",
                ephemeral=True
            )
            return

        set_team_closed_status(team_number, True)

        await interaction.followup.send(
            f"🔒 Team {team_number} has been closed.",
            ephemeral=True
        )

    except Exception as e:
        await interaction.followup.send(
            f"❌ Error closing team: {e}",
            ephemeral=True
        )


@bot.tree.command(name="openteam", description="Reopen a closed team")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(team_number="Enter the team number to reopen")
async def openteam(interaction: discord.Interaction, team_number: str):
    try:
        await interaction.response.defer(ephemeral=True)

        team = get_team(team_number)
        if not team:
            await interaction.followup.send(
                "❌ Team not found.",
                ephemeral=True
            )
            return

        set_team_closed_status(team_number, False)

        await interaction.followup.send(
            f"🔓 Team {team_number} has been reopened.",
            ephemeral=True
        )

    except Exception as e:
        await interaction.followup.send(
            f"❌ Error opening team: {e}",
            ephemeral=True
        )


@bot.tree.command(name="report", description="Submit match report")
@app_commands.describe(
    team_number="Enter the team number",
    map_number="Enter the map number",
    map_name="Choose Avalon or Verdansk"
)
@app_commands.choices(
    map_name=[
        app_commands.Choice(name="Avalon", value="Avalon"),
        app_commands.Choice(name="Verdansk", value="Verdansk"),
    ]
)
async def report(
    interaction: discord.Interaction,
    team_number: str,
    map_number: int,
    map_name: app_commands.Choice[str]
):
    try:
        team = get_team(team_number)

        if not team:
            await interaction.response.send_message(
                "❌ Team not found.",
                ephemeral=True
            )
            return

        if is_team_closed(team_number):
            await interaction.response.send_message(
                f"❌ Team {team_number} is closed and cannot submit reports.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            ReportModal(team, map_number, map_name.value)
        )

    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(
                f"❌ Error opening report form: {e}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Error opening report form: {e}",
                ephemeral=True
            )


@bot.tree.command(name="viewteam", description="View a team by team number")
@app_commands.describe(team_number="Enter the team number")
async def viewteam(interaction: discord.Interaction, team_number: str):
    try:
        team = get_team(team_number)

        if not team:
            await interaction.response.send_message(
                "❌ Team not found.",
                ephemeral=True
            )
            return

        closed_status = "Yes" if is_team_closed(team_number) else "No"

        message = (
            f"**Team Number:** {team['Team Number']}\n"
            f"**Player 1:** {team['Player 1']}\n"
            f"**Player 2:** {team['Player 2']}\n"
            f"**Player 3:** {team['Player 3']}\n"
            f"**Player 4:** {team['Player 4']}\n"
            f"**Closed:** {closed_status}"
        )

        await interaction.response.send_message(message, ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(
            f"❌ Error: {e}",
            ephemeral=True
        )


@bot.tree.command(name="resetteams", description="Reset all registered teams")
@app_commands.checks.has_permissions(administrator=True)
async def resetteams(interaction: discord.Interaction):
    try:
        clear_teams()
        await interaction.response.send_message(
            "⚠️ All teams have been reset.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"❌ Error: {e}",
            ephemeral=True
        )


@closeteam.error
@openteam.error
@resetteams.error
@refreshplayers.error
async def admin_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        if interaction.response.is_done():
            await interaction.followup.send(
                "❌ You must be an administrator to use this command.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ You must be an administrator to use this command.",
                ephemeral=True
            )
    else:
        if interaction.response.is_done():
            await interaction.followup.send(
                f"❌ Error: {error}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Error: {error}",
                ephemeral=True
            )


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    print("APP COMMAND ERROR:", error)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(
                f"❌ Command error: {error}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Command error: {error}",
                ephemeral=True
            )
    except Exception as followup_error:
        print("FOLLOWUP ERROR:", followup_error)


@bot.event
async def on_ready():
    synced = await bot.tree.sync()
    try:
        count = refresh_validated_players_cache()
        print(f"Loaded {count} validated players into cache.")
    except Exception as e:
        print(f"Failed to preload validated players: {e}")
    print(f"Bot is online! Synced {len(synced)} global command(s).")


bot.run(TOKEN)