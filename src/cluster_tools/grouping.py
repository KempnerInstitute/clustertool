"""Help formatting, command markers, and typo suggestions for the CLI."""

import difflib
from collections.abc import Callable
from typing import ClassVar

import click


def admin(command: click.Command) -> click.Command:
    """Mark a command as operator-only so help lists it under Admin Commands."""
    command.scope = "admin"
    return command


def keywords(*terms: str) -> Callable[[click.Command], click.Command]:
    """Attach extra search terms to a command, used by 'clustertools search'."""

    def decorator(command: click.Command) -> click.Command:
        command.search_keywords = tuple(terms)
        return command

    return decorator


class SectionedGroup(click.Group):
    """Group whose help splits user and admin commands, with typo suggestions.

    Commands marked with the admin decorator are shown under Admin Commands and
    the rest under User Commands, each sorted alphabetically. A group with no
    admin commands keeps a single Commands section. Names in the aliases map
    resolve to their target command, and an unknown subcommand is reported with
    a "did you mean" suggestion.
    """

    aliases: ClassVar[dict[str, str]] = {}

    def get_command(self, ctx: click.Context, name: str) -> click.Command | None:
        command = super().get_command(ctx, name)
        if command is None and name in self.aliases:
            command = super().get_command(ctx, self.aliases[name])
        return command

    def resolve_command(self, ctx, args):
        name = args[0] if args else ""
        if (
            name
            and not name.startswith("-")
            and not ctx.resilient_parsing
            and self.get_command(ctx, name) is None
        ):
            close = difflib.get_close_matches(name, list(self.list_commands(ctx)), n=3, cutoff=0.5)
            if close:
                ctx.fail(f"No such command {name!r}. Did you mean: {', '.join(close)}?")
        return super().resolve_command(ctx, args)

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        commands = []
        for name in self.list_commands(ctx):
            cmd = self.get_command(ctx, name)
            if cmd is None or cmd.hidden:
                continue
            commands.append((name, cmd))
        if not commands:
            return
        limit = formatter.width - 6 - max(len(name) for name, _ in commands)
        user_rows = []
        admin_rows = []
        for name, cmd in commands:
            row = (name, cmd.get_short_help_str(limit))
            if getattr(cmd, "scope", "user") == "admin":
                admin_rows.append(row)
            else:
                user_rows.append(row)
        if admin_rows:
            if user_rows:
                with formatter.section("User Commands"):
                    formatter.write_dl(user_rows)
            with formatter.section("Admin Commands"):
                formatter.write_dl(admin_rows)
        else:
            with formatter.section("Commands"):
                formatter.write_dl(user_rows)
