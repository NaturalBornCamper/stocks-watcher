"""
Thin browser wrappers around the compile_sa_score* management commands.

The real work lives in the commands (apps/quant/management/commands/), which
the cron runner triggers on a schedule. These views just forward any query
params (?limit=, ?decay_base=, ...) to the matching command and return its
output as plain text, so the old /quant/cron/... URLs still work by hand.
"""
from io import StringIO

from django.core.management import call_command
from django.http import HttpResponse


# Reads the given query params off the request and returns them as command
# options, skipping any that weren't passed so the command's own defaults apply.
def _options_from_request(request, names):
    options = {}
    for name, cast in names.items():
        raw_value = request.GET.get(name)
        if raw_value is not None:
            options[name] = cast(raw_value)
    return options


# Runs a management command and returns its captured output as a plain-text response.
def _run_command(command_name, options):
    output = StringIO()
    call_command(command_name, stdout=output, **options)
    return HttpResponse(output.getvalue(), content_type="text/plain")


def compile_sa_score(request):
    options = _options_from_request(request, {"limit": int})
    return _run_command("compile_sa_score", options)


def compile_sa_score_decayed(request):
    options = _options_from_request(request, {
        "limit": int,
        "decay_months": int,
        "decay_base": float,
    })
    return _run_command("compile_sa_score_decayed", options)


def compile_sa_score_momentum(request):
    options = _options_from_request(request, {
        "limit": int,
        "window_months": int,
        "momentum_weight": float,
    })
    return _run_command("compile_sa_score_momentum", options)