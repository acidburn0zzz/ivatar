# Generated by Django 2.1.5 on 2019-03-08 14:01

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import ivatar.ivataraccount.models


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0009_alter_user_last_name_max_length'),
        ('ivataraccount', '0014_auto_20190218_1602'),
    ]

    operations = [
        migrations.CreateModel(
            name='APIKey',
            fields=[
                ('public_key', models.CharField(default=ivatar.ivataraccount.models.random_api_key, max_length=32, unique=True)),
                ('secret_key', models.CharField(default=ivatar.ivataraccount.models.random_api_key, max_length=32)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, serialize=False, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]