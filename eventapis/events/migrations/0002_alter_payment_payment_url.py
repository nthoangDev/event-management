# Generated by Django 5.2 on 2025-04-26 15:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='payment',
            name='payment_url',
            field=models.URLField(blank=True, max_length=1000, null=True),
        ),
    ]
