# Generated by Django 3.1.7 on 2021-04-01 21:46

from django.db import migrations
import sortedm2m.fields


class Migration(migrations.Migration):

    dependencies = [
        ('footnotes', '0005_add_permissions_source_sourcetype_footnotes'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='creator',
            options={'ordering': ['last_name']},
        ),
        migrations.AlterModelOptions(
            name='source',
            options={},
        ),
        migrations.RemoveField(
            model_name='source',
            name='author',
        ),
        migrations.AddField(
            model_name='source',
            name='authors',
            field=sortedm2m.fields.SortedManyToManyField(help_text=None, to='footnotes.Creator'),
        ),
    ]
