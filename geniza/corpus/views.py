from django.db.models.query import Prefetch
from django.views.generic.detail import DetailView
from tabular_export.admin import export_to_csv_response

from geniza.corpus.models import Document, TextBlock
from geniza.corpus.admin import DocumentAdmin
from geniza.footnotes.models import Footnote


class DocumentDetailView(DetailView):
    """public display of a single :class:`~geniza.corpus.models.Document`"""

    model = Document

    context_object_name = "document"

    def get_queryset(self, *args, **kwargs):
        """Don't show document if it isn't public"""
        queryset = super().get_queryset(*args, **kwargs)
        return queryset.filter(status=Document.PUBLIC)


# --------------- Publish CSV to sync with old PGP site --------------------- #


def old_pgp_edition(editions):
    """output footnote and source information in a format similar to
    old pgp metadata editor/editions."""
    if editions:
        # label as translation if edition also supplies translation;
        # include url if any
        edition_list = [
            "%s%s%s"
            % (
                "and trans. " if Footnote.TRANSLATION in fn.doc_relation else "",
                fn.display().strip("."),
                " %s" % fn.url if fn.url else "",
            )
            for fn in editions
        ]
        # combine multiple editons as Ed. ...; also ed. ...
        return "".join(["Ed. ", "; also ed. ".join(edition_list), "."])

    return ""


def old_pgp_tabulate_data(queryset):
    """Takes a :class:`~geniza.corpus.models.Document` queryset and
    yields rows of data for serialization as csv in :method:`pgp_metadata_for_old_site`"""
    # NOTE: This logic assumes that documents will always have a fragment
    for doc in queryset:
        primary_fragment = doc.textblock_set.first().fragment
        num_fragments = len([tb for tb in doc.textblock_set.all() if tb.certain])
        # library abbreviation; use collection abbreviation as fallback
        library = ""
        if primary_fragment.collection:
            library = (
                primary_fragment.collection.lib_abbrev
                or primary_fragment.collection.abbrev
            )

        yield [
            doc.id,  # pgpid
            library,  # library / collection
            primary_fragment.shelfmark,  # shelfmark
            primary_fragment.old_shelfmarks,  # shelfmark_alt
            doc.textblock_set.first().get_side_display(),  # recto_verso
            doc.doctype,  # document type
            " ".join("#" + t.name for t in doc.tags.all()),  # tags
            doc.shelfmark if num_fragments > 1 else "",  # join
            doc.description,  # description
            old_pgp_edition(doc.editions()),  # editor
        ]


def pgp_metadata_for_old_site(request):
    """Stream metadata in CSV format for index and display in the old PGP site."""

    # limit to documents with associated fragments, since the output
    # assumes a document has at least one frgment
    queryset = (
        Document.objects.filter(status=Document.PUBLIC, fragments__isnull=False)
        .order_by("id")
        .distinct()
        .select_related("doctype")
        .prefetch_related(
            "tags",
            "footnotes",
            # see corpus admin for notes on nested prefetch
            Prefetch(
                "textblock_set",
                queryset=TextBlock.objects.select_related(
                    "fragment", "fragment__collection"
                ),
            ),
        )
    )
    # return response
    return export_to_csv_response(
        DocumentAdmin.csv_filename(DocumentAdmin),
        [
            "pgpid",
            "library",
            "shelfmark",
            "shelfmark_alt",
            "recto_verso",
            "type",
            "tags",
            "joins",
            "description",
            "editor",
        ],
        old_pgp_tabulate_data(queryset),
    )


# --------------------------------------------------------------------------- #
