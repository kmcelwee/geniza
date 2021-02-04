# Generated by Django 3.1.6 on 2021-02-04 20:48

from django.contrib.auth.management import create_permissions
from django.db import migrations

CONTENT_EDITOR = 'Content Editor'
# permissions for content editor
content_editor_perms = {
    'docs': [
        'view_library'
    ]
}

CONTENT_ADMIN = 'Content Admin'
# additional permissions for content admin (also get content edit permissions)
content_admin_perms = {
    'docs': [
        'add_library', 'change_library', 'delete_library',
    ]
}


def create_content_editor_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    # make sure permissions are created before loading the fixture
    # which references them
    # (when running migrations all at once, permissions may not yet exist)
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    editor_group = Group.objects.create(name=CONTENT_EDITOR)
    permissions = []
    for model, codenames in content_editor_perms.items():
        # using explicit get so that there will be an error if an
        # expected permission is not found
        for codename in codenames:
            permissions.append(Permission.objects.get(codename=codename))
    editor_group.permissions.set(permissions)

    # update content admin group; add to content edit permissions
    admin_group = Group.objects.create(name=CONTENT_ADMIN)
    for model, codenames in content_editor_perms.items():
        for codename in codenames:
            permissions.append(Permission.objects.get(codename=codename))
    admin_group.permissions.set(permissions)


def remove_content_editor_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=[CONTENT_ADMIN, CONTENT_EDITOR]) \
        .delete()


class Migration(migrations.Migration):

    dependencies = [
        ('docs', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_content_editor_groups,
                             reverse_code=remove_content_editor_groups)
    ]
