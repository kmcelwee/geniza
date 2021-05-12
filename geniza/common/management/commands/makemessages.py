from django.core.management.commands import makemessages

from geniza import __version__


class Command(makemessages.Command):
    """Overrides `makemessages` to add metadata to .po files and exclude virtual
    environments from being automatically translated.
    """

    # For invocation options for xgettext, see:
    # https://www.gnu.org/software/gettext/manual/html_node/xgettext-Invocation.html
    xgettext_options = makemessages.Command.xgettext_options + [
        "--copyright-holder=The Trustees of Princeton University",
        "--msgid-bugs-address=cdhdevteam@princeton.edu",
        f"--package-version={__version__}",
        "--package-name=geniza",
    ]

    def handle(self, *args, **options):
        # Ignore virtual environments to make sure we don't end up translating
        # content from installed dependencies. For the other defaults, see:
        # https://github.com/django/django/blob/main/django/core/management/commands/makemessages.py#L294
        options["ignore_patterns"] += ["venv", "env"]
        return super().handle(*args, **options)
