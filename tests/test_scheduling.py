import pytest

from mail_utils.scheduling import (
    ScheduleError,
    build_cron_line,
    build_windows_register_script,
    build_windows_unregister_script,
    cron_marker,
    cron_schedule_fields,
    list_cron_jobs,
    windows_task_name,
)


def test_windows_task_name_prefixes_job_name():
    assert windows_task_name("work") == "MailUtils-work"


def test_windows_register_script_contains_task_name_and_argument():
    script = build_windows_register_script("work", 15, "C:\\venv\\python.exe", "C:\\proj", ["import", "--filter", "label:Work"])
    assert "MailUtils-work" in script
    assert "-m mail_utils.cli import --filter" in script
    assert "New-TimeSpan -Minutes 15" in script
    assert "-Force" in script


def test_windows_register_script_escapes_embedded_single_quotes():
    script = build_windows_register_script("o'brien", 30, "python.exe", "C:\\proj", ["import", "--filter", "from:o'brien"])
    # A single quote inside a PowerShell single-quoted string must be doubled.
    assert "o''brien" in script


def test_windows_unregister_script_targets_correct_task():
    script = build_windows_unregister_script("work")
    assert "MailUtils-work" in script
    assert "Unregister-ScheduledTask" in script


def test_cron_schedule_fields_minutes_under_an_hour():
    assert cron_schedule_fields(15) == "*/15 * * * *"
    assert cron_schedule_fields(1) == "*/1 * * * *"


def test_cron_schedule_fields_rejects_non_divisor_of_60():
    with pytest.raises(ScheduleError):
        cron_schedule_fields(90)  # what actually broke: */1440 silently misbehaved in cron


def test_cron_schedule_fields_whole_hours():
    assert cron_schedule_fields(60) == "0 */1 * * *"
    assert cron_schedule_fields(120) == "0 */2 * * *"


def test_cron_schedule_fields_rejects_hours_not_dividing_24():
    with pytest.raises(ScheduleError):
        cron_schedule_fields(300)  # 5 hours - doesn't divide 24 evenly


def test_cron_schedule_fields_whole_days():
    assert cron_schedule_fields(1440) == "0 0 */1 * *"  # the exact case that broke: daily export
    assert cron_schedule_fields(2880) == "0 0 */2 * *"


def test_cron_schedule_fields_rejects_non_positive():
    with pytest.raises(ScheduleError):
        cron_schedule_fields(0)


def test_cron_line_has_correct_interval_and_marker():
    line = build_cron_line("work", 15, "/venv/bin/python", "/proj", "/proj/logs/cron.log", ["import"])
    assert line.startswith("*/15 * * * *")
    assert "mail_utils.cli import" in line
    assert line.endswith(cron_marker("work"))


def test_cron_line_daily_export_uses_hour_field_not_broken_minute_step():
    line = build_cron_line("nightly", 1440, "/venv/bin/python", "/proj", "/proj/logs/cron.log", ["export", "/out"])
    assert line.startswith("0 0 */1 * *")


def test_cron_line_quotes_filter_with_spaces():
    line = build_cron_line(
        "work",
        30,
        "/venv/bin/python",
        "/proj",
        "/proj/logs/cron.log",
        ["import", "--filter", "label:Work from:jane"],
    )
    assert "'label:Work from:jane'" in line


def test_cron_line_different_job_names_have_distinct_markers():
    line1 = build_cron_line("a", 30, "python", "/proj", "/log", ["import"])
    line2 = build_cron_line("b", 30, "python", "/proj", "/log", ["import"])
    assert cron_marker("a") not in line2
    assert cron_marker("b") not in line1


def test_list_cron_jobs_parses_job_name_and_command(monkeypatch):
    from mail_utils import scheduling

    fake_line = build_cron_line("work", 15, "/venv/bin/python", "/proj", "/proj/logs/cron.log", ["import"])
    monkeypatch.setattr(scheduling, "read_crontab", lambda: ["# unrelated line", fake_line])

    jobs = list_cron_jobs()
    assert len(jobs) == 1
    name, command = jobs[0]
    assert name == "work"
    assert "mail_utils.cli import" in command
