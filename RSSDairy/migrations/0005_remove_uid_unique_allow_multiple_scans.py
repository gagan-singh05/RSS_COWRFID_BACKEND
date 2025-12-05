# Generated migration to remove unique constraint on uid
# This allows multiple scans per UID (one per event), supporting IN/OUT tracking

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('RSSDairy', '0004_rfidscan_direction_alter_rfidscan_uid'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rfidscan',
            name='uid',
            field=models.CharField(max_length=50),  # removed unique=True
        ),
    ]
