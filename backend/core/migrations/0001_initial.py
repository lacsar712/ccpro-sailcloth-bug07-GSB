import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Loft",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=120)),
                ("location", models.CharField(blank=True, default="", max_length=200)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="ClothRoll",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("roll_code", models.CharField(max_length=40)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("raw", "原布"),
                            ("dipping", "浸渍中"),
                            ("cured", "已固化"),
                        ],
                        default="raw",
                        max_length=20,
                    ),
                ),
                ("fabric_weight_gsm", models.PositiveIntegerField(default=380)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "loft",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rolls",
                        to="core.loft",
                    ),
                ),
            ],
            options={"ordering": ["loft_id", "roll_code"]},
        ),
        migrations.CreateModel(
            name="DipRun",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("started_at", models.DateTimeField()),
                ("resin_pct", models.DecimalField(decimal_places=2, max_digits=5)),
                (
                    "cure_hours",
                    models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True),
                ),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "roll",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dip_runs",
                        to="core.clothroll",
                    ),
                ),
            ],
            options={"ordering": ["-started_at"]},
        ),
        migrations.AddConstraint(
            model_name="clothroll",
            constraint=models.UniqueConstraint(
                fields=("loft", "roll_code"), name="uniq_roll_code_per_loft"
            ),
        ),
    ]
