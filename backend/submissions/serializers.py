import os

from django.conf import settings
from django.utils.text import get_valid_filename
from rest_framework import serializers

from .models import Submission

# Magic number (file signature): the first bytes a genuine file must start
# with. This is how we verify a file is REALLY a PDF instead of trusting its
# extension (which an attacker controls). Only PDF is accepted here -- no ZIP
# (DOCX) or OLE (DOC) containers.
#   - PDF : the ASCII bytes "%PDF-"
MAGIC_SIGNATURES = {
    ".pdf": [b"%PDF-"],
}


def sanitize_filename(name):
    """Return a safe filename: no directory parts, no null bytes, no tricks.

    Defends against path traversal (e.g. "../../etc/passwd"), null-byte
    injection, and double extensions (e.g. "resume.pdf.exe" would already be
    rejected by the extension check, but "evil.php.pdf" is collapsed to
    "evil_php.pdf" so there is no embedded second extension in the stored name).
    """
    # 1. Keep only the final path component (strips "../", "foo/bar", "C:\...").
    name = name.replace("\\", "/").split("/")[-1]
    # 2. Drop null bytes.
    name = name.replace("\x00", "")
    # 3. Split off the (already-validated) extension.
    stem, ext = os.path.splitext(name)
    ext = ext.lower()
    # 4. Slugify the stem to word-safe characters, and collapse any remaining
    #    dots so a second extension cannot hide inside it.
    safe_stem = get_valid_filename(stem).replace(".", "_") or "upload"
    return f"{safe_stem}{ext}"


def content_matches_extension(ext, header_bytes):
    """True if the file's real header bytes match its claimed extension."""
    signatures = MAGIC_SIGNATURES.get(ext, [])
    return any(header_bytes.startswith(sig) for sig in signatures)


class SubmissionSerializer(serializers.ModelSerializer):
    """Serializer for the SECURE endpoint (/api/saysafe/).

    validate_cv enforces real, layered server-side validation on the upload:
    extension allowlist -> size limit -> magic-byte content check -> filename
    sanitization. Because this runs on the server, it holds even when the
    browser-side check is bypassed (e.g. with Burp).
    """

    class Meta:
        model = Submission
        fields = [
            "id",
            "full_name",
            "email",
            "address",
            "cv",
            "variant",
            "created_at",
        ]
        read_only_fields = ["id", "variant", "created_at"]

    def validate_cv(self, value):
        name = value.name or ""

        # 1. Extension allowlist (read from the filename).
        ext = os.path.splitext(name)[1].lower()
        if ext not in settings.ALLOWED_CV_EXTENSIONS:
            allowed = ", ".join(sorted(settings.ALLOWED_CV_EXTENSIONS))
            raise serializers.ValidationError(
                f"Unsupported file type '{ext or '(none)'}'. Allowed: {allowed}."
            )

        # 2. Size limit.
        if value.size > settings.MAX_CV_SIZE_BYTES:
            mb = settings.MAX_CV_SIZE_BYTES / (1024 * 1024)
            raise serializers.ValidationError(
                f"File too large. Maximum size is {mb:.0f} MB."
            )

        # 3. Content check: the real bytes must match the claimed type. This is
        #    what stops "rename anything to .pdf and upload it". We read the
        #    header, then seek(0) so the whole file is still saved intact.
        header = value.read(8)
        value.seek(0)
        if not content_matches_extension(ext, header):
            kind = ext.lstrip(".").upper()
            raise serializers.ValidationError(
                f"File content is not a genuine {kind}. The bytes do not match "
                f"a real {kind} file (the extension may have been changed)."
            )

        # 4. Sanitize the stored filename (path traversal, odd chars, double
        #    extensions). The cleaned name is what gets written to disk.
        value.name = sanitize_filename(name)
        return value


class UnsafeSubmissionSerializer(SubmissionSerializer):
    """DELIBERATELY INSECURE serializer for /api/unsafe/.

    It inherits everything from SubmissionSerializer EXCEPT the file check:
    validate_cv is overridden to accept any file, any size, any content, with
    the original (unsanitized) filename. This is the whole point of the demo --
    the /unsafe endpoint trusts the frontend to have validated the upload, so a
    request crafted in Burp (any file, renamed however) sails straight through
    and is stored on disk. NEVER do this in real code: always validate uploads
    server-side, as /saysafe does above.
    """

    def validate_cv(self, value):
        # No server-side validation, on purpose. The file is accepted as-is.
        return value
