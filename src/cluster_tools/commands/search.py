"""search command."""

import click

from cluster_tools import search as finder


@click.command("search")
@click.argument("query", nargs=-1, required=True, metavar="TERMS...")
def search(query: tuple[str, ...]) -> None:
    """Find commands by keyword, ranked by relevance.

    Searches every command's name, description, and keywords and prints the best
    matches with their one-line help. Use it when you know what you want to do
    but not which command does it. Also available as 'find' and 'lookup'.

    \b
    Use cases:
      - Discover the right command from a plain word, e.g. 'search fairshare'.
      - Explore an area, e.g. 'search gpu reservation' or 'search disk quota'.

    \b
    Inputs:
      TERMS...  One or more words to search for.
    """
    ctx = click.get_current_context()
    root = ctx.find_root().command
    records = [r for r in finder.collect_commands(root, ctx) if r["name"] != "search"]
    results = finder.rank(records, list(query))
    if not results:
        click.echo(f"No commands matched {' '.join(query)!r}.")
        hints = finder.suggest(records, list(query))
        if hints:
            click.echo("Closest commands: " + ", ".join(hints))
        click.echo("Run 'clustertools --help' to list all command groups.")
        return
    width = max(len(record["path"]) for record in results)
    for record in results:
        tag = "  [admin]" if record["scope"] == "admin" else ""
        click.echo(f"{record['path']:<{width}}  {record['short']}{tag}")
    click.echo("")
    click.echo("Run 'clustertools <command> --help' for details.")
