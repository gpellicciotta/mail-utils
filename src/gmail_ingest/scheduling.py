"""Cross-platform recurring-job registration: Windows Task Scheduler (via
PowerShell) or cron (Linux/macOS), each job identified by a name so several
independently-filtered/independently-databased jobs can coexist.

Command-construction is split from execution (the `build_*`/`*_line`
functions are pure - no subprocess calls) specifically so it's testable
without touching a real crontab or Task Scheduler.
"""

import shlex
import subprocess

ALLOWED_COMMANDS = ("import", "export")


class ScheduleError(Exception):
    """A schedule/unschedule operation failed, or the platform is unsupported."""


def _ps_quote(value) -> str:
    """Single-quote a string for embedding literally in a PowerShell script -
    PowerShell single-quoted strings don't interpret anything except a
    doubled '' for a literal quote, unlike double-quoted strings."""
    return "'" + str(value).replace("'", "''") + "'"


def windows_task_name(job_name: str) -> str:
    return f"GmailIngest-{job_name}"


def build_windows_register_script(job_name: str, interval_minutes: int, python_exe: str, working_dir, inner_args: list) -> str:
    full_args = ["-m", "gmail_ingest.cli", *inner_args]
    argument_string = subprocess.list2cmdline(full_args)
    task_name = windows_task_name(job_name)
    description = f"gmail-ingest scheduled job '{job_name}': {' '.join(inner_args)}"
    return f"""
$Action = New-ScheduledTaskAction -Execute {_ps_quote(python_exe)} -Argument {_ps_quote(argument_string)} -WorkingDirectory {_ps_quote(working_dir)}
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes {interval_minutes}) -RepetitionDuration (New-TimeSpan -Days 3650)
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName {_ps_quote(task_name)} -Action $Action -Trigger $Trigger -Settings $Settings -Description {_ps_quote(description)} -Force | Out-Null
"""


def build_windows_unregister_script(job_name: str) -> str:
    task_name = windows_task_name(job_name)
    return f"Unregister-ScheduledTask -TaskName {_ps_quote(task_name)} -Confirm:$false -ErrorAction SilentlyContinue"


def build_windows_list_script() -> str:
    return (
        'Get-ScheduledTask -TaskName "GmailIngest-*" -ErrorAction SilentlyContinue '
        "| Format-Table TaskName, State -AutoSize | Out-String -Width 200"
    )


def schedule_windows(job_name: str, interval_minutes: int, python_exe: str, working_dir, inner_args: list) -> None:
    script = build_windows_register_script(job_name, interval_minutes, python_exe, working_dir, inner_args)
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True)
    if result.returncode != 0:
        raise ScheduleError(f"Failed to register scheduled task: {result.stderr.strip()}")


def unschedule_windows(job_name: str) -> None:
    script = build_windows_unregister_script(job_name)
    subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True)


def list_windows_jobs() -> str:
    script = build_windows_list_script()
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True)
    return result.stdout.strip()


CRON_MARKER_PREFIX = "# gmail-ingest:"


def cron_marker(job_name: str) -> str:
    return f"{CRON_MARKER_PREFIX}{job_name}"


def cron_schedule_fields(interval_minutes: int) -> str:
    """Translate an interval in minutes into cron's minute/hour/day-of-month
    fields. Cron's fields are independent modulo-wheels (minutes wrap at 60,
    hours at 24), not a true elapsed-time interval like Windows Task
    Scheduler's - so only exact divisors translate to a simple expression;
    anything else (e.g. 90 minutes, or 100 minutes) is rejected rather than
    silently producing a broken schedule (cron itself just warns and
    misbehaves on an out-of-range step like */1440)."""
    if interval_minutes <= 0:
        raise ScheduleError("--interval-minutes must be positive.")

    if interval_minutes < 60:
        if 60 % interval_minutes != 0:
            raise ScheduleError(
                f"--interval-minutes {interval_minutes} doesn't divide evenly into 60 minutes; cron can't "
                "express that as a simple recurring interval. Use a divisor of 60 (1, 2, 3, 4, 5, 6, 10, "
                "12, 15, 20, 30) or a whole number of hours/days."
            )
        return f"*/{interval_minutes} * * * *"

    if interval_minutes < 1440:
        if interval_minutes % 60 != 0:
            raise ScheduleError(
                f"--interval-minutes {interval_minutes} is over an hour but not a whole number of hours; "
                "cron can't express that as a simple recurring interval."
            )
        hours = interval_minutes // 60
        if 24 % hours != 0:
            raise ScheduleError(
                f"{hours} hours doesn't divide evenly into 24; cron can't express that as a simple "
                "recurring interval. Use a divisor of 24 hours (1, 2, 3, 4, 6, 8, 12) or a whole number "
                "of days."
            )
        return f"0 */{hours} * * *"

    if interval_minutes % 1440 != 0:
        raise ScheduleError(
            f"--interval-minutes {interval_minutes} is over a day but not a whole number of days; cron "
            "can't express that as a simple recurring interval."
        )
    days = interval_minutes // 1440
    return f"0 0 */{days} * *"


def build_cron_line(job_name: str, interval_minutes: int, python_exe: str, working_dir, log_path, inner_args: list) -> str:
    schedule_fields = cron_schedule_fields(interval_minutes)
    full_args = ["-m", "gmail_ingest.cli", *inner_args]
    cmd = f"cd {shlex.quote(str(working_dir))} && {shlex.quote(python_exe)} {shlex.join(full_args)}"
    return f"{schedule_fields} {cmd} >> {shlex.quote(str(log_path))} 2>&1 {cron_marker(job_name)}"


def read_crontab() -> list:
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return []
    return result.stdout.splitlines()


def write_crontab(lines: list) -> None:
    content = ("\n".join(lines) + "\n") if lines else ""
    subprocess.run(["crontab", "-"], input=content, text=True, check=True)


def schedule_cron(job_name: str, interval_minutes: int, python_exe: str, working_dir, log_path, inner_args: list) -> str:
    marker = cron_marker(job_name)
    lines = [line for line in read_crontab() if marker not in line]
    line = build_cron_line(job_name, interval_minutes, python_exe, working_dir, log_path, inner_args)
    lines.append(line)
    write_crontab(lines)
    return line


def unschedule_cron(job_name: str) -> bool:
    marker = cron_marker(job_name)
    lines = read_crontab()
    new_lines = [line for line in lines if marker not in line]
    write_crontab(new_lines)
    return len(new_lines) != len(lines)


def list_cron_jobs() -> list:
    jobs = []
    for line in read_crontab():
        if CRON_MARKER_PREFIX in line:
            marker_idx = line.index(CRON_MARKER_PREFIX)
            job_name = line[marker_idx + len(CRON_MARKER_PREFIX):].strip()
            jobs.append((job_name, line[:marker_idx].strip()))
    return jobs
