# -*- coding: utf-8 -*-
# Generated by Django 1.9.5 on 2017-05-30 15:47
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('seed', '0001_initial'),
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('data_importer', '0001_initial'),
        ('orgs', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='importrecord',
            name='last_modified_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='modified_import_records', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='importrecord',
            name='owner',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='importrecord',
            name='super_organization',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='import_records', to='orgs.Organization'),
        ),
        migrations.AddField(
            model_name='importfile',
            name='cycle',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='seed.Cycle'),
        ),
        migrations.AddField(
            model_name='importfile',
            name='import_record',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='data_importer.ImportRecord'),
        ),
        migrations.AddField(
            model_name='datacoercionmapping',
            name='table_column_mapping',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='data_importer.TableColumnMapping'),
        ),
        migrations.AddField(
            model_name='buildingimportrecord',
            name='building_model_content_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.ContentType'),
        ),
        migrations.AddField(
            model_name='buildingimportrecord',
            name='import_record',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='data_importer.ImportRecord'),
        ),
    ]