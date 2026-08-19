from gmail_ingest.cli import _run_stats, _run_update, build_parser


def test_update_subcommand_routes_to_run_update():
    args = build_parser().parse_args(["update"])
    assert args.command == "update"
    assert args.func is _run_update


def test_stats_subcommand_routes_to_run_stats():
    args = build_parser().parse_args(["stats"])
    assert args.command == "stats"
    assert args.func is _run_stats


def test_help_subcommand_has_no_func():
    args = build_parser().parse_args(["help"])
    assert args.command == "help"
    assert not hasattr(args, "func")


def test_no_subcommand_has_no_command():
    args = build_parser().parse_args([])
    assert args.command is None
