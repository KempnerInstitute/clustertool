"""Storage quota command construction."""

VAST_ROOT = "/n/netscratch"
LUSTRE_MOUNT = "/n/holylfs06"


def vast_quota_cmd(account: str) -> list[str]:
    """Return the command to report VAST (netscratch) quota for an account."""
    return ["quota", f"{VAST_ROOT}/{account}"]


def lustre_quota_cmd(account: str, mount: str = LUSTRE_MOUNT) -> list[str]:
    """Return the command to report Lustre quota for an account group."""
    return ["lfs", "quota", "-hg", account, mount]
