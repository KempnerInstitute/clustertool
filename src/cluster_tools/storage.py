"""Storage quota command construction."""

VAST_ROOT = "/n/netscratch"
LUSTRE_MOUNT = "/n/holylfs06"


def vast_quota_cmd(account: str) -> list[str]:
    """Return the command to report VAST (netscratch) quota for an account."""
    return ["quota", f"{VAST_ROOT}/{account}"]


def lustre_quota_cmd(name: str, mount: str = LUSTRE_MOUNT, user: bool = False) -> list[str]:
    """Return the command to report a Lustre group or user quota."""
    return ["lfs", "quota", "-hu" if user else "-hg", name, mount]
