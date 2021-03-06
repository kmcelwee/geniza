# Generated by Django 3.1.7 on 2021-04-27 15:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("corpus", "0010_remove_old_inputby_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="textblock",
            name="certain",
            field=models.BooleanField(
                default=True,
                help_text="Are you certain that this fragment belongs to this document? Uncheck this box if you are uncertain of a potential join.",
            ),
        ),
        migrations.AlterField(
            model_name="document",
            name="fragments",
            field=models.ManyToManyField(
                related_name="documents",
                through="corpus.TextBlock",
                to="corpus.Fragment",
            ),
        ),
    ]
