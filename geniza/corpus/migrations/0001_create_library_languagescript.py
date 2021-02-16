# Generated by Django 3.1.6 on 2021-02-16 15:11

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='LanguageScript',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('language', models.CharField(max_length=255)),
                ('script', models.CharField(max_length=255)),
                ('display_name', models.CharField(blank=True, help_text='Option to override the autogenerated language-script name', max_length=255, null=True, unique=True)),
            ],
            options={
                'ordering': ['language'],
            },
        ),
        migrations.CreateModel(
            name='Library',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('library', models.CharField(max_length=255)),
                ('abbrev', models.CharField(max_length=255, unique=True, verbose_name='Abbreviation')),
                ('collection', models.CharField(blank=True, help_text='Collection name, if different than Library', max_length=255)),
                ('location', models.CharField(help_text='Current location of the collection', max_length=255)),
            ],
            options={
                'verbose_name_plural': 'Libraries',
                'ordering': ['abbrev'],
            },
        ),
        migrations.AddConstraint(
            model_name='library',
            constraint=models.UniqueConstraint(fields=('library', 'collection'), name='unique_library_collection'),
        ),
        migrations.AddConstraint(
            model_name='languagescript',
            constraint=models.UniqueConstraint(fields=('language', 'script'), name='unique_language_script'),
        ),
    ]
