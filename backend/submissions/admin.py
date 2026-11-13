from django import forms
from django.contrib import admin
from django.utils.html import format_html
from rest_framework.serializers import ValidationError as DRFValidationError

from .models import Submission
from .serializers import SubmissionSerializer, UnsafeSubmissionSerializer

# Which serializer validates each variant -- the SAME classes the API uses.
# saysafe -> real server-side checks; unsafe -> no file validation.
SERIALIZER_FOR_VARIANT = {
    Submission.Variant.SAYSAFE: SubmissionSerializer,
    Submission.Variant.UNSAFE: UnsafeSubmissionSerializer,
}


class SubmissionAdminForm(forms.ModelForm):
    """Admin add/edit form that reuses the API serializers to check the CV.

    When staff add a submission from the admin, the uploaded file is run
    through the exact same validate_cv the API uses for the chosen variant:
    pick 'saysafe' and a non-PDF (or a renamed file) is rejected; pick
    'unsafe' and anything is accepted -- identical to /api/saysafe/ vs
    /api/unsafe/. No duplicated validation logic.
    """

    class Meta:
        model = Submission
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        cv = cleaned.get("cv")
        variant = cleaned.get("variant")

        if cv and variant:
            serializer_class = SERIALIZER_FOR_VARIANT.get(
                variant, SubmissionSerializer
            )
            try:
                # Reuse the serializer's own field validation for this variant.
                cleaned["cv"] = serializer_class().validate_cv(cv)
            except DRFValidationError as exc:
                # Surface the serializer's message(s) on the cv field.
                messages = exc.detail if isinstance(exc.detail, list) else [exc.detail]
                self.add_error("cv", [str(m) for m in messages])

        return cleaned


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    form = SubmissionAdminForm
    list_display = ("id", "full_name", "email", "variant", "cv_link", "created_at")
    list_filter = ("variant", "created_at")
    search_fields = ("full_name", "email", "address")
    readonly_fields = ("cv_link", "created_at")

    @admin.display(description="CV file")
    def cv_link(self, obj):
        """Render the uploaded file as a clickable download/view link."""
        if not obj.cv:
            return "—"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">{}</a>',
            obj.cv.url,
            obj.cv.name,
        )

    # --- Make admin deletes also remove the uploaded file from disk ---------
    # Django's default delete only removes the DB row, leaving the file behind.
    # These overrides mean "Delete selected" (and single-object delete) clean
    # up the stored file too, so a demo reset is just: select all -> delete.

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            if obj.cv:
                obj.cv.delete(save=False)
        super().delete_queryset(request, queryset)

    def delete_model(self, request, obj):
        if obj.cv:
            obj.cv.delete(save=False)
        super().delete_model(request, obj)
