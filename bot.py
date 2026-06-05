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
    refresh_validated_players_cache
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
            starts_with = [
                name for name in players
                if name.lower().startswith(current)
            ]
            contains = [
                name for name in players
                if current in name.lower() and name not in starts_with
            ]
            matches = (starts_with + contains)[:25]

        return [app_commands.Choice(name=name, value=name) for name in matches]

    except Exception as e:
        print("AUTOCOMPLETE ERROR:", e)
        return []


class ReportStartModal(discord.ui.Modal):

    def __init__(self, tournament):
        super().__init__(title="Start Report")

        self.tournament = tournament

        self.team_number = discord.ui.TextInput(
            label="Team Number",
            required=True
        )

        self.map_number = discord.ui.TextInput(
            label="Map Number",
            required=True
        )

        self.add_item(self.team_number)
        self.add_item(self.map_number)

    async def on_submit(self, interaction: discord.Interaction):

        team = get_team(self.team_number.value)

        if not team:
            await interaction.response.send_message(
                "❌ Team not found.",
                ephemeral=True
            )
            return

        view = ReportContinueView(
            tournament=self.tournament,
            team=team,
            map_number=self.map_number.value
        )

        await interaction.response.send_message(
            f"✅ Team {self.team_number.value} | Map {self.map_number.value}\n\nClick below to enter results.",
            view=view,
            ephemeral=True
        )


class ReportContinueView(discord.ui.View):

    def __init__(self, tournament, team, map_number):
        super().__init__(timeout=300)

        self.tournament = tournament
        self.team = team
        self.map_number = map_number

    @discord.ui.button(
        label="Enter Results",
        style=discord.ButtonStyle.green
    )
    async def enter_results(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            ReportModal(
                tournament=self.tournament,
                team=self.team,
                map_number=self.map_number
            )
        )


class ReportModal(discord.ui.Modal):

    def __init__(
        self,
        tournament,
        team,
        map_number
    ):
        super().__init__(title="Match Results")

        self.tournament = tournament
        self.team = team
        self.map_number = map_number

        self.placement = discord.ui.TextInput(
            label="Placement"
        )

        self.p1 = discord.ui.TextInput(
    label=f"{self.team['Player 1']} Kills"
)

self.p2 = discord.ui.TextInput(
    label=f"{self.team['Player 2']} Kills"
)

self.p3 = discord.ui.TextInput(
    label=f"{self.team['Player 3']} Kills"
)

self.p4 = discord.ui.TextInput(
    label=f"{self.team['Player 4']} Kills"
)

        self.add_item(self.placement)
        self.add_item(self.p1)
        self.add_item(self.p2)
        self.add_item(self.p3)
        self.add_item(self.p4)

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):
        try:

            append_report(
                reporter=interaction.user.name,
                tournament=self.tournament,
                team_number=self.team["Team Number"],
                map_number=self.map_number,
                p1_kills=int(self.p1.value),
                p2_kills=int(self.p2.value),
                p3_kills=int(self.p3.value),
                p4_kills=int(self.p4.value),
                placement=int(self.placement.value)
            )

            await interaction.response.send_message(
                f"✅ {self.tournament} report submitted successfully.",
                ephemeral=True
            )

        except Exception as e:
            await interaction.response.send_message(
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


@bot.tree.command(
    name="br_report",
    description="Submit BR Report"
)
async def br_report(
    interaction: discord.Interaction
):

    await interaction.response.send_modal(
        ReportStartModal("BR")
    )


@bot.tree.command(
    name="resurgence_report",
    description="Submit Resurgence Report"
)
async def resurgence_report(
    interaction: discord.Interaction
):
    try:
        await interaction.response.send_modal(
            ReportStartModal("Resurgence")
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

        message = (
            f"**Team Number:** {team['Team Number']}\n"
            f"**Player 1:** {team['Player 1']}\n"
            f"**Player 2:** {team['Player 2']}\n"
            f"**Player 3:** {team['Player 3']}\n"
            f"**Player 4:** {team['Player 4']}"
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
