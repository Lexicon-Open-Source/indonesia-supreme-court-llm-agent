import asyncio
import subprocess
from functools import wraps
from pathlib import Path


async def run_async_command(command: str, cwd: Path) -> str:
    process = await asyncio.create_subprocess_shell(
        command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0 and process.returncode is not None:
        error_message = stderr.decode().strip()
        raise subprocess.CalledProcessError(
            returncode=process.returncode,
            cmd=command,
            output=stdout.decode().strip(),
            stderr=error_message,
        )

    return stdout.decode("utf-8")


def coroutine_wrapper(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))

    return wrapper
