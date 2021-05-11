# Generated by Django 3.1.7 on 2021-03-16 18:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("corpus", "0007_fragment_needs_review"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fragment",
            name="old_shelfmarks",
            field=models.CharField(
                blank=True,
                help_text="Semicolon-delimited list of previously used shelfmarks. This is autogenerated when shelfmark is updated",
                max_length=500,
                verbose_name="Historical Shelfmarks",
            ),
        ),
    ]
