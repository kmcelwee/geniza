# Generated by Django 3.1.6 on 2021-04-07 13:20

from django.db import migrations, models
import django.db.models.deletion
import multiselectfield.db.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="Authorship",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=1)),
            ],
            options={
                "ordering": ("sort_order",),
            },
        ),
        migrations.CreateModel(
            name="Creator",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("first_name", models.CharField(max_length=255)),
                ("first_name_en", models.CharField(max_length=255, null=True)),
                ("first_name_he", models.CharField(max_length=255, null=True)),
                ("first_name_ar", models.CharField(max_length=255, null=True)),
                ("last_name", models.CharField(max_length=255)),
                ("last_name_en", models.CharField(max_length=255, null=True)),
                ("last_name_he", models.CharField(max_length=255, null=True)),
                ("last_name_ar", models.CharField(max_length=255, null=True)),
            ],
            options={
                "ordering": ["last_name", "first_name"],
            },
        ),
        migrations.CreateModel(
            name="SourceLanguage",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                (
                    "code",
                    models.CharField(help_text="ISO language code", max_length=10),
                ),
            ],
        ),
        migrations.CreateModel(
            name="SourceType",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("type", models.CharField(max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name="Source",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("title_en", models.CharField(max_length=255, null=True)),
                ("title_he", models.CharField(max_length=255, null=True)),
                ("title_ar", models.CharField(max_length=255, null=True)),
                ("year", models.PositiveIntegerField(blank=True, null=True)),
                ("edition", models.CharField(blank=True, max_length=255)),
                ("volume", models.CharField(blank=True, max_length=255)),
                (
                    "page_range",
                    models.CharField(
                        blank=True,
                        help_text="Page range for article or book section.",
                        max_length=255,
                    ),
                ),
                (
                    "author",
                    models.ManyToManyField(
                        through="footnotes.Authorship", to="footnotes.Creator"
                    ),
                ),
                (
                    "languages",
                    models.ManyToManyField(
                        help_text="The language(s) the source is written in",
                        to="footnotes.SourceLanguage",
                    ),
                ),
                (
                    "source_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="footnotes.sourcetype",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Footnote",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "page_range",
                    models.CharField(
                        blank=True,
                        help_text='The range of pages being cited. Do not include "p", "pg", etc. and follow the format # or #-#',
                        max_length=255,
                    ),
                ),
                (
                    "doc_relation",
                    multiselectfield.db.fields.MultiSelectField(
                        choices=[
                            ("E", "Edition"),
                            ("T", "Translation"),
                            ("D", "Discussion"),
                        ],
                        help_text="How does the source relate to this document?",
                        max_length=5,
                        verbose_name="Document relation",
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("object_id", models.PositiveIntegerField()),
                (
                    "content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="contenttypes.contenttype",
                    ),
                ),
                (
                    "source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="footnotes.source",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="creator",
            constraint=models.UniqueConstraint(
                fields=("first_name", "last_name"), name="creator_unique_name"
            ),
        ),
        migrations.AddField(
            model_name="authorship",
            name="creator",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="footnotes.creator"
            ),
        ),
        migrations.AddField(
            model_name="authorship",
            name="source",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="footnotes.source"
            ),
        ),
    ]
