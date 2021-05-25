from adminsortable2.admin import SortableInlineAdminMixin
from django import forms
from django.conf.urls import url
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.contrib.contenttypes.admin import GenericTabularInline
from django.contrib.sites.models import Site
from django.db import models
from django.db.models import Count
from django.db.models.fields import CharField, TextField
from django.db.models.functions import Concat
from django.db.models.query import Prefetch
from django.forms.widgets import TextInput, Textarea
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from modeltranslation.admin import TabbedTranslationAdmin
from tabular_export.admin import export_to_csv_response

from geniza.footnotes.models import (
    Authorship,
    Creator,
    Footnote,
    Source,
    SourceLanguage,
    SourceType,
)
from geniza.common.admin import custom_empty_field_list_filter


class AuthorshipInline(SortableInlineAdminMixin, admin.TabularInline):
    model = Authorship
    autocomplete_fields = ["creator"]
    fields = ("creator", "sort_order")
    extra = 1


class SourceFootnoteInline(admin.TabularInline):
    """Footnote inline for the Source admin"""

    model = Footnote
    fields = (
        "object_link",
        "content_type",
        "object_id",
        "location",
        "doc_relation",
        "has_transcription",
        "notes",
    )
    readonly_fields = ("object_link", "has_transcription")
    formfield_overrides = {
        CharField: {"widget": TextInput(attrs={"size": "10"})},
        TextField: {"widget": Textarea(attrs={"rows": 3})},
    }

    def object_link(self, obj):
        """edit link with string display method for associated content object"""
        # return empty spring for unsaved footnote with no  content object
        if not obj.content_object:
            return ""
        content_obj = obj.content_object
        edit_url = "admin:%s_%s_change" % (
            content_obj._meta.app_label,
            content_obj._meta.model_name,
        )
        edit_path = reverse(edit_url, args=[obj.object_id])
        return format_html(
            f'<a href="{edit_path}">{content_obj} '
            + '<img src="/static/admin/img/icon-changelink.svg" alt="Change"></a>'
        )

    object_link.short_description = "object"


class DocumentFootnoteInline(GenericTabularInline):
    """Footnote inline for the Document admin"""

    model = Footnote
    autocomplete_fields = ["source"]
    fields = (
        "source",
        "location",
        "doc_relation",
        "has_transcription",
        "notes",
    )
    readonly_fields = ("has_transcription",)
    extra = 1
    formfield_overrides = {
        CharField: {"widget": TextInput(attrs={"size": "10"})},
        TextField: {"widget": Textarea(attrs={"rows": 3})},
    }


@admin.register(Source)
class SourceAdmin(TabbedTranslationAdmin, admin.ModelAdmin):
    footnote_admin_url = "admin:footnotes_footnote_changelist"

    list_display = ("all_authors", "title", "journal", "volume", "year", "footnotes")
    list_display_links = ("all_authors", "title")
    search_fields = (
        "title",
        "authors__first_name",
        "authors__last_name",
        "year",
        "journal",
        "notes",
        "other_info",
        "languages__name",
    )

    fields = (
        "source_type",
        "title",
        "year",
        "edition",
        "journal",
        "volume",
        "other_info",
        "languages",
        "notes",
    )
    list_filter = (
        "source_type",
        "languages",
        ("authors", admin.RelatedOnlyFieldListFilter),
    )

    inlines = [AuthorshipInline, SourceFootnoteInline]

    class Media:
        css = {"all": ("css/admin-local.css",)}

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .filter(
                models.Q(authorship__isnull=True) | models.Q(authorship__sort_order=1)
            )
            .annotate(
                Count("footnote", distinct=True),
                first_author=Concat(
                    "authorship__creator__last_name", "authorship__creator__first_name"
                ),
            )
            .select_related("source_type")
            .prefetch_related(
                Prefetch(
                    "authorship_set",
                    queryset=Authorship.objects.select_related("creator"),
                )
            )
        )

    def footnotes(self, obj):
        return format_html(
            '<a href="{0}?source__id__exact={1!s}">{2}</a>',
            reverse(self.footnote_admin_url),
            str(obj.id),
            obj.footnote__count,
        )

    footnotes.short_description = "# footnotes"
    footnotes.admin_order_field = "footnote__count"

    csv_fields = [
        "source_type",
        "authors",
        "title",
        "journal_book",
        "volume",
        "year",
        "edition",
        "other_info",
        "page_range",
        "languages",
        "url",
        "notes",
        "num_footnotes",
        "admin_url",
    ]

    def csv_filename(self):
        """Generate filename for CSV download"""
        return f'geniza-sources-{timezone.now().strftime("%Y%m%dT%H%M%S")}.csv'

    def tabulate_queryset(self, queryset):
        """Generator of source data for csv export"""

        # generate absolute urls locally with a single db call,
        # instead of calling out to absolutize_url method
        site_domain = Site.objects.get_current().domain.rstrip("/")
        # qa / prod always https
        url_scheme = "https://"

        for source in queryset:
            yield [
                source.source_type,
                # authors in order, lastname first
                ";".join([str(a.creator) for a in source.authorship_set.all()]),
                source.title,
                source.journal,
                source.volume,
                source.year,
                source.edition,
                source.other_info,
                source.page_range,
                ";".join([lang.name for lang in source.languages.all()]),
                source.url,
                source.notes,
                source.footnote__count,  # via annotated queryset
                f"{url_scheme}{site_domain}/admin/footnotes/source/{source.id}/change/",
            ]

    def export_to_csv(self, request, queryset=None):
        """Stream source records as CSV"""
        queryset = self.get_queryset(request) if queryset is None else queryset
        return export_to_csv_response(
            self.csv_filename(),
            self.csv_fields,
            self.tabulate_queryset(queryset),
        )

    export_to_csv.short_description = "Export selected sources to CSV"

    def get_urls(self):
        """Return admin urls; adds a custom URL for exporting all sources
        as CSV"""
        urls = [
            url(
                r"^csv/$",
                self.admin_site.admin_view(self.export_to_csv),
                name="footnotes_source_csv",
            )
        ]
        return urls + super(SourceAdmin, self).get_urls()

    actions = (export_to_csv,)


@admin.register(SourceType)
class SourceTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(SourceLanguage)
class SourceLanguageAdmin(admin.ModelAdmin):
    list_display = ("name", "code")


class DocumentRelationTypesFilter(SimpleListFilter):
    """A custom filter to allow filter footnotes based on
    document relation, no matter how they are used in combination"""

    title = "document relationship"
    parameter_name = "doc_relation"

    def lookups(self, request, model_admin):
        return model_admin.model.DOCUMENT_RELATION_TYPES

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(doc_relation__contains=self.value())


class FootnoteForm(forms.ModelForm):
    class Meta:
        model = Footnote
        exclude = ()
        widgets = {
            "location": TextInput(attrs={"size": "10"}),
        }


@admin.register(Footnote)
class FootnoteAdmin(admin.ModelAdmin):
    form = FootnoteForm
    list_display = (
        "__str__",
        "source",
        "location",
        "notes",
        "has_transcription",
        "has_url",
    )
    list_filter = (
        DocumentRelationTypesFilter,
        (
            "content",
            custom_empty_field_list_filter(
                "transcription", "Digitized", "Not digitized"
            ),
        ),
        (
            "url",
            custom_empty_field_list_filter("url", "Has URL", "No URL"),
        ),
    )
    readonly_fields = ["content_object"]

    search_fields = (
        "source__title",
        "source__authors__first_name",
        "source__authors__last_name",
        "content",
        "notes",
        "document__id",
        "document__fragments__shelfmark",
    )

    # Add help text to the combination content_type and object_id
    CONTENT_LOOKUP_HELP = """Select the kind of record you want to attach
    a footnote to, and then use the object id search button to select an item."""
    fieldsets = [
        (
            None,
            {
                "fields": ("content_type", "object_id", "content_object"),
                "description": f'<div class="help">{CONTENT_LOOKUP_HELP}</div>',
            },
        ),
        (
            None,
            {
                "fields": (
                    "source",
                    "location",
                    "doc_relation",
                    "url",
                    "notes",
                )
            },
        ),
    ]

    class Media:
        css = {"all": ("css/admin-local.css",)}

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("source")
            .prefetch_related("content_object", "source__authors")
        )

    def doc_relation_list(self, obj):
        # Casting the multichoice object as string to return a reader-friendly
        #  comma-delimited list.
        return str(obj.doc_relation)

    doc_relation_list.short_description = "Document Relation"
    doc_relation_list.admin_order_field = "doc_relation"


@admin.register(Creator)
class CreatorAdmin(TabbedTranslationAdmin):
    list_display = ("last_name", "first_name")
    search_fields = ("first_name", "last_name")
    fields = ("last_name", "first_name")
