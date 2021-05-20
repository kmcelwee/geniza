# Generated by Django 3.1 on 2021-06-02 13:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('corpus', '0013_document_old_pgpids'),
    ]

    operations = [
        migrations.RenameField(
            model_name="textblock",
            old_name="subfragment",
            new_name="multifragment",
        ),
        migrations.AlterField(
            model_name='textblock',
            name='multifragment',
            field=models.CharField(blank=True, help_text='Identifier for fragment part, if part of a multifragment', max_length=255),
        ),
    ]