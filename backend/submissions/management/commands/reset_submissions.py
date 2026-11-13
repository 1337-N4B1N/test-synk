import shutil

from django.conf import settings
from django.core.management.base import BaseCommand

from submissions.models import Submission


class Command(BaseCommand):
    help = (
        "Delete all submissions and their uploaded files, for a clean demo. "
        "Use --no-input to skip the confirmation prompt."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-input",
            action="store_true",
            dest="no_input",
            help="Skip the confirmation prompt (useful in scripts).",
        )

    def handle(self, *args, **options):
        count = Submission.objects.count()

        if count and not options["no_input"]:
            answer = input(
                f"Delete {count} submission(s) and all uploaded files? [y/N] "
            )
            if answer.strip().lower() not in {"y", "yes"}:
                self.stdout.write("Aborted. Nothing was deleted.")
                return

        deleted, _ = Submission.objects.all().delete()

        # Remove the uploaded files from disk too (the DB delete alone leaves
        # the files behind).
        removed = []
        for sub in ("assets", "cv"):
            path = settings.MEDIA_ROOT / sub
            if path.exists():
                shutil.rmtree(path)
                removed.append(sub + "/")

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted} row(s); cleared files: "
                f"{', '.join(removed) if removed else 'none'}."
            )
        )
