"""Help formatting that splits group commands into user and admin sections."""

import click


def admin(command: click.Command) -> click.Command:
    """Mark a command as operator-only so help lists it under Admin Commands."""
    command.scope = "admin"
    return command


class SectionedGroup(click.Group):
    """Group whose help lists user and admin commands in separate sections.

    Commands marked with the admin decorator are shown under Admin Commands and
    the rest under User Commands, each sorted alphabetically. A group with no
    admin commands keeps a single Commands section.
    """

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
