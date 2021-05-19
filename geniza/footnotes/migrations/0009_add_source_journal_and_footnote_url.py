# Generated by Django 3.1 on 2021-05-19 14:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("footnotes", "0008_footnote_restrict_contenttype_to_corpus"),
    ]

    operations = [
        migrations.AddField(
            model_name="footnote",
            name="url",
            field=models.URLField(
                blank=True, help_text="Link to the source (optional)", max_length=300
            ),
        ),
        migrations.AddField(
            model_name="source",
            name="journal",
            field=models.CharField(
                blank=True,
                help_text="Title of the journal, for an article",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="source",
            name="other_info",
            field=models.TextField(
                blank=True, help_text="Additional citation information, if any"
            ),
        ),
        migrations.AlterField(
            model_name="source",
            name="volume",
            field=models.CharField(
                blank=True,
                help_text="Volume of a multivolume book, or journal volume for an article",
                max_length=255,
            ),
        ),
    ]