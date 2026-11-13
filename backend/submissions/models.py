from django.db import models


def cv_upload_path(instance, filename):
    # Store uploads under media/assets/<variant>/, grouped by which endpoint
    # received them. Viewable from the Django admin via the CV file link.
    return f"assets/{instance.variant}/{filename}"


class Submission(models.Model):
    """A single form submission.

    Note: the CV file is stored on disk (MEDIA_ROOT); only its path/metadata
    live in the database. Never store large binaries in DB columns.
    """

    class Variant(models.TextChoices):
        SAYSAFE = "saysafe", "saysafe (clean libraries)"
        UNSAFE = "unsafe", "unsafe (vulnerable libraries)"

    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    address = models.CharField(max_length=500)
    cv = models.FileField(upload_to=cv_upload_path)
    variant = models.CharField(
        max_length=20, choices=Variant.choices, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} <{self.email}> [{self.variant}]"
