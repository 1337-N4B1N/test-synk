from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Submission
from .serializers import SubmissionSerializer, UnsafeSubmissionSerializer


class BaseSubmissionView(APIView):
    """Shared create logic. Subclasses set `variant` and `serializer_class`."""

    variant = None
    # Which serializer validates the incoming data. Subclasses override this
    # to choose whether the upload is checked server-side.
    serializer_class = SubmissionSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        submission = serializer.save(variant=self.variant)
        return Response(
            SubmissionSerializer(submission).data,
            status=status.HTTP_201_CREATED,
        )


class SaySafeSubmissionView(BaseSubmissionView):
    """The secure endpoint: /api/saysafe/

    Validates the upload on the SERVER (SubmissionSerializer.validate_cv), so a
    disallowed file is rejected even when the frontend check is bypassed with a
    tool like Burp. This is defense in depth: never trust the client.
    """

    variant = Submission.Variant.SAYSAFE
    serializer_class = SubmissionSerializer


class UnsafeSubmissionView(BaseSubmissionView):
    """The deliberately unsafe endpoint: /api/unsafe/

    Demonstrates THREE planted problems:
      1. SCA  -> requirements.txt pins PyYAML 5.3.1 (CVE-2020-14343),
                 which `pip-audit` flags.
      2. SAST -> the yaml.load() call below on user input is an unsafe
                 pattern that `bandit` flags (B506: yaml_load).
      3. Insecure file upload -> this view uses UnsafeSubmissionSerializer,
                 which does NOT validate the uploaded file. The frontend blocks
                 bad files, but that check is client-side and bypassable (Burp).
                 A request sent straight to this endpoint with shell.py is
                 accepted and the file is stored. /saysafe validates on the
                 server and rejects it. That contrast is the lesson.

    This is intentional and lives only in this educational demo. In real
    code you would validate uploads server-side, use yaml.safe_load(), and
    keep dependencies patched.
    """

    variant = Submission.Variant.UNSAFE
    serializer_class = UnsafeSubmissionSerializer

    def post(self, request):
        # --- intentionally vulnerable block (for the demo) ---
        raw_meta = request.data.get("metadata")
        if raw_meta:
            import yaml  # vulnerable version pinned in requirements.txt

            # B506: using yaml.load without SafeLoader on untrusted input.
            parsed = yaml.load(raw_meta)  # nosec-intentional-for-demo  # noqa
            # (parsed is ignored; the point is that scanners flag this code.)
            _ = parsed
        # --- end vulnerable block ---
        return super().post(request)
