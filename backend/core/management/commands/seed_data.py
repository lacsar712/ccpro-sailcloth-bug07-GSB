from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import ClothRoll, DipRun, Loft

User = get_user_model()


class Command(BaseCommand):
    help = "初始化演示账号与帆布浸渍种子数据"

    def handle(self, *args, **options):
        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@sailcloth.local",
                "role": User.ROLE_ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        admin.set_password("123456")
        admin.role = User.ROLE_ADMIN
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        self.stdout.write(self.style.SUCCESS(f"admin {'created' if created else 'updated'}"))

        worker, created = User.objects.get_or_create(
            username="worker",
            defaults={
                "email": "worker@sailcloth.local",
                "role": User.ROLE_WORKER,
            },
        )
        worker.set_password("123456")
        worker.role = User.ROLE_WORKER
        worker.save()
        self.stdout.write(self.style.SUCCESS(f"worker {'created' if created else 'updated'}"))

        if Loft.objects.exists():
            self.stdout.write("业务数据已存在，跳过业务种子写入。")
            return

        loft = Loft.objects.create(
            name="北岸帆布间",
            location="港区二号库",
            notes="浸渍防水台示范 loft",
        )
        south = Loft.objects.create(
            name="南坞帆布间",
            location="对岸料棚",
            notes="对照间，卷码与北岸可重复",
        )
        r1 = ClothRoll.objects.create(
            loft=loft, roll_code="R-01", status=ClothRoll.STATUS_DIPPING, fabric_weight_gsm=420
        )
        r2 = ClothRoll.objects.create(
            loft=loft, roll_code="R-02", status=ClothRoll.STATUS_RAW, fabric_weight_gsm=380
        )
        r3 = ClothRoll.objects.create(
            loft=loft, roll_code="R-03", status=ClothRoll.STATUS_CURED, fabric_weight_gsm=450
        )
        s1 = ClothRoll.objects.create(
            loft=south, roll_code="R-01", status=ClothRoll.STATUS_RAW, fabric_weight_gsm=390
        )
        s2 = ClothRoll.objects.create(
            loft=south, roll_code="R-04", status=ClothRoll.STATUS_DIPPING, fabric_weight_gsm=410
        )

        now = timezone.now()
        DipRun.objects.bulk_create(
            [
                DipRun(
                    roll=r1,
                    started_at=now - timedelta(hours=8),
                    resin_pct=Decimal("28.50"),
                    cure_hours=None,
                    notes="北岸 R-01 固化计时中",
                ),
                DipRun(
                    roll=r2,
                    started_at=now - timedelta(hours=1),
                    resin_pct=Decimal("26.00"),
                    cure_hours=Decimal("4.00"),
                    notes="北岸时长不足",
                ),
                DipRun(
                    roll=r3,
                    started_at=now - timedelta(days=2),
                    resin_pct=Decimal("30.00"),
                    cure_hours=Decimal("14.50"),
                    notes="北岸已完成固化",
                ),
                DipRun(
                    roll=s1,
                    started_at=now - timedelta(hours=3),
                    resin_pct=Decimal("22.00"),
                    cure_hours=Decimal("8.00"),
                    notes="南坞同码 R-01 树脂对照",
                ),
                DipRun(
                    roll=s2,
                    started_at=now - timedelta(hours=5),
                    resin_pct=Decimal("27.00"),
                    cure_hours=None,
                    notes="南坞浸渍中",
                ),
            ]
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"种子完成：帆布间 {Loft.objects.count()}，布卷 {ClothRoll.objects.count()}，"
                f"浸渍 {DipRun.objects.count()}"
            )
        )
