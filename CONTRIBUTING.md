# Contributing

Thanks for adding a tool. This guide shows how to turn a cluster script into a
`clustertool` command via a pull request.

## Principles

- One umbrella CLI. Every task is a subcommand under a group.
- Commands are thin. Put reusable logic (Slurm queries, parsing) in a helper
  module such as `src/clustertool/slurm.py` so it can be shared and tested.
- Read the official documentation (Slurm, Python, a library's own docs) for how
  a command or API behaves. Do not guess flags or output formats.

## Command groups

Every command belongs to a group. Pick the group whose scope fits; create a new
group only when none does. A group's module is added when its first command
lands, so `--help` never shows an empty group.

| Group | Scope |
| --- | --- |
| `gpu` | GPU usage, availability, and sessions |
| `jobs` | Job queue, status, history, logs, and control |
| `account` | Account membership, fairshare, usage, limits, QOS |
| `nodes` | Node, partition, and reservation status |
| `storage` | Filesystem quotas, usage, and striping |
| `diag` | Diagnostics and benchmarks |
| `qos` | QoS holders, and admin provisioning and assignment |

## Style rules

- US spelling only.
- No extra comments in code. A simple docstring is enough.
- Type-hint public functions.
- Keep lines within 100 characters (enforced by ruff).
- Do not hardcode site-specific values (partition names, limits, paths). Add them
  to `src/clustertool/data/site.default.toml` and read them via `clustertool.site`
  (see [docs/configuration.md](docs/configuration.md)).

## Set up

```bash
uv sync
uv run clustertool --help
```

## Add a command

Each group is a package under `src/clustertool/commands/`: the group's
`__init__.py` defines the `click` group and registers its commands, and each
command lives in its own file.

1. Pick the group whose scope fits your command (see Command groups). You will
   add a file to that group's package, e.g. `src/clustertool/commands/env/`.

2. Write the command in its own file as a standalone `click` command. The
   docstring becomes `--help`, so it must explain what the command does, its use
   cases, and its inputs. A line containing only `\b` (a backspace escape in a
   normal, non-raw docstring) keeps the following block from being re-wrapped.

   `src/clustertool/commands/env/modules.py`:

   ```python
   """env modules command."""
   import click


   @click.command("modules")
   @click.argument("name", required=False)
   def modules(name: str | None) -> None:
       """List available modules, optionally filtered by name.

       \b
       Use cases:
         - Find which versions of a package are available.

       \b
       Inputs:
         NAME  Optional name filter (e.g. cuda).
       """
       ...
   ```

   Inputs: a command may take no input, or a required/optional list of inputs.
   Use `click.argument` for required inputs and `click.option` for optional
   ones. Document each input in the docstring.

   Privileged commands (those that change cluster state and need rights beyond
   an ordinary user's) should be marked with the `admin` decorator from
   `clustertool.grouping`, placed above `@click.command`, so `--help` lists
   them under Admin Commands rather than User Commands. A command that changes
   only the caller's own jobs or files, such as `jobs cancel` or `storage
   lfs-stripe`, is not privileged and stays user scope. Name the actual level in
   the docstring rather than assuming operator: `scontrol update node` and QoS
   definition changes need a Slurm or system admin, editing an account or
   assigning a QoS needs an operator or a coordinator of that account.

   Read-only commands can be privileged too. A command that ssh-es to nodes
   across a whole partition, rather than only the nodes running the caller's own
   jobs, is admin: where node login requires an allocation on that node, as
   `pam_slurm_adopt` enforces, an ordinary user cannot reach them. `diag ib` and
   `gpu monitor-partition` are admin for this reason, while `gpu monitor-job` and
   `gpu nvtop` stay user scope because they only touch the caller's own job.

   Add search keywords for words users might type that are not already in the
   help text, with the `keywords` decorator from `clustertool.grouping`, so
   `clustertool search` can find the command:

   ```python
   from clustertool.grouping import keywords

   @keywords("kill", "stop", "abort")
   @click.command("cancel")
   def cancel(...): ...
   ```

   For a parameter that takes a live value (a job ID, account, or partition),
   set `shell_complete` from `clustertool.completion` so tab completion
   suggests real values, for example
   `@click.argument("jobid", shell_complete=completion.complete_job_ids)`.

3. Register it in the group's `__init__.py`:

   ```python
   from clustertool.commands.env.modules import modules

   env.add_command(modules)
   ```

4. For a new group, create the package `__init__.py` with the group, then add
   the group in `src/clustertool/cli.py`:

   `src/clustertool/commands/env/__init__.py`:

   ```python
   """Environment commands."""
   import click

   from clustertool.commands.env.modules import modules
   from clustertool.grouping import SectionedGroup


   @click.group(cls=SectionedGroup)
   def env() -> None:
       """Inspect the software environment."""


   env.add_command(modules)
   ```

   `src/clustertool/cli.py`:

   ```python
   from clustertool.commands.env import env

   main.add_command(env)
   ```

   Adding a command to an existing group only needs the new file plus its
   `add_command` line in that group's `__init__.py`; no change in `cli.py`.

5. Put shared Slurm logic in `src/clustertool/slurm.py` and keep it read-only
   unless a command is explicitly meant to change cluster state. Run external
   tools through `clustertool.process`: `run` captures stdout for parsing, and
   `stream` passes a tool's output straight through to the user.

6. To ship a shell snippet, CUDA source, or other payload with a command, put
   the file under `src/clustertool/data/` and load it at runtime with
   `importlib.resources.files("clustertool") / "data" / "<file>"`. This keeps
   long verbatim payloads out of the Python source (that directory is excluded
   from ruff) and bundles them into the wheel.

7. Document the command in `docs/commands/<group>.md`, mirroring its `--help`: a
   `## ` heading with the command signature, the description, and **Use cases**
   and **Inputs** lists. For a new group, create that file, link it from
   `docs/commands/README.md`, and add a row to the README command table. For a
   new command in an existing group, add its name to that group's cell in the
   README table. Also add a row to `clustertool-commands-index.md` (command,
   scope, wraps, description).

   Changing a command takes the same pass. A flag, a unit, an exit code, or a
   tool that moves invalidates the same four places, and a doc that describes
   behavior the code no longer has is worse than one that says nothing.

## Add tests

Add tests under `tests/`. Mock external commands by monkeypatching the helper
(for example `slurm._run`, or `process.stream` for passthrough commands) so
tests do not depend on a live cluster. Use `click.testing.CliRunner` for
command tests.

Stub every query the command makes, not only the one it is about: a preflight
check that resolves a job's owner or a partition's existence will otherwise
reach the real scheduler. On a login node such a test passes for the wrong
reason and fails in CI, so prove the suite is isolated by running it with the
cluster tools genuinely off `PATH`, not merely with a directory prepended to
one that still contains them.

## Run checks before opening a PR

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## Open the pull request

Describe the command, its inputs, and example output. A maintainer will review
behavior, help text, and tests before merging.

## Release

Uploads to PyPI are manual. Trusted publishing does not work from this
organization: its enterprise adds a slug to the Actions OIDC issuer, and PyPI
accepts only the unsuffixed issuer, so the token exchange fails whatever the
project is configured with.

1. Raise `version` in `pyproject.toml`, run `uv lock`, and merge that.
2. Draft a GitHub release with tag `vX.Y.Z` targeting `main`, and publish it.
   The release check verifies the tag against the version, runs the tests,
   builds, and attaches both artifacts to the release.
3. Upload with a PyPI token scoped to this project where the scope is offered,
   and revoke it afterward:

```bash
uv build
uvx twine check --strict dist/*
uvx twine upload dist/*
```

A description cannot be edited after upload, so anything wrong in the README on
the project page stays wrong until the next release. The README serves its
pictures over absolute URLs and carries no mermaid, since PyPI resolves a
relative path against pypi.org and prints a mermaid fence as source text.
