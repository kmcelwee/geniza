# Generated by Django 3.1.6 on 2021-02-04 20:36

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Library',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
                ('abbrev', models.CharField(max_length=255, unique=True, verbose_name='Abbreviation')),
                ('url', models.URLField(blank=True, verbose_name='URL')),
            ],
            options={
                'verbose_name_plural': 'Libraries',
            },
        )
    ]