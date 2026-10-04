"""删间级联 / 卷号唯一 / 并发撞码 的验收测试。

跑在真实 PostgreSQL 上（唯一约束的并发兜底只有在真库里才验证得到），
因此用 TransactionTestCase，保证各连接能看到已提交数据、并能开并发事务。
"""

from datetime import timedelta
from threading import Barrier, Thread

from django.db import connection, transaction
from django.db.models.signals import pre_delete
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework import serializers
from rest_framework.test import APIClient

from accounts.models import User
from core.models import ClothRoll, DipRun, Loft


class LoftDeletionTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="keeper", password="x")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.loft = Loft.objects.create(name="甲间")

    def _make_roll_with_dip(self, code):
        roll = ClothRoll.objects.create(loft=self.loft, roll_code=code)
        DipRun.objects.create(
            roll=roll,
            started_at=timezone.now(),
            resin_pct="28.00",
        )
        return roll

    def test_delete_loft_removes_loft_rolls_and_dips_together(self):
        self._make_roll_with_dip("A-1")
        self._make_roll_with_dip("A-2")

        resp = self.client.delete(f"/api/lofts/{self.loft.id}/")
        self.assertEqual(resp.status_code, 204)

        self.assertFalse(Loft.objects.filter(id=self.loft.id).exists())
        self.assertEqual(ClothRoll.objects.filter(loft_id=self.loft.id).count(), 0)
        self.assertEqual(DipRun.objects.count(), 0)

    def test_failed_delete_rolls_back_everything(self):
        # 级联删除中途抛错：间、卷、浸渍必须整笔退回，不得留下残卷。
        r1 = self._make_roll_with_dip("B-1")
        self._make_roll_with_dip("B-2")

        def blow_up(sender, instance, **kwargs):
            if instance.pk == r1.pk:
                raise RuntimeError("simulated cascade failure")

        pre_delete.connect(blow_up, sender=ClothRoll)
        try:
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    self.loft.delete()
        finally:
            pre_delete.disconnect(blow_up, sender=ClothRoll)

        self.assertTrue(Loft.objects.filter(id=self.loft.id).exists())
        self.assertEqual(ClothRoll.objects.filter(loft=self.loft).count(), 2)
        self.assertEqual(DipRun.objects.filter(roll__loft=self.loft).count(), 2)


class RollCodeUniquenessTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="keeper", password="x")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.loft = Loft.objects.create(name="甲间")

    def test_duplicate_code_on_create_is_rejected_and_does_not_overwrite(self):
        payload = {"loftId": self.loft.id, "rollCode": "X-1", "fabricWeightGsm": 380}
        resp = self.client.post("/api/rolls/", payload, format="json")
        self.assertEqual(resp.status_code, 201)

        clash = {"loftId": self.loft.id, "rollCode": "X-1", "fabricWeightGsm": 520}
        resp = self.client.post("/api/rolls/", clash, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("rollCode", resp.data)

        # 旧卷原样保留：仍只有一卷，克重未被改写。
        self.assertEqual(ClothRoll.objects.filter(loft=self.loft).count(), 1)
        original = ClothRoll.objects.get(loft=self.loft, roll_code="X-1")
        self.assertEqual(original.fabric_weight_gsm, 380)

    def test_same_code_in_other_loft_is_allowed(self):
        other = Loft.objects.create(name="乙间")
        ClothRoll.objects.create(loft=self.loft, roll_code="SAME")
        resp = self.client.post(
            "/api/rolls/",
            {"loftId": other.id, "rollCode": "SAME", "fabricWeightGsm": 380},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)

    def test_concurrent_duplicate_creation_only_one_persists(self):
        # 两名仓管同时在同一间新建同一个卷码：只许一笔进库。
        from core.serializers import ClothRollSerializer

        results = []
        barrier = Barrier(2)

        def attempt(gsm):
            serializer = ClothRollSerializer(
                data={
                    "loftId": self.loft.id,
                    "rollCode": "RACE-1",
                    "fabricWeightGsm": gsm,
                }
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)
            barrier.wait()  # 两人都过了应用层校验，再同时落库，逼出竞态
            try:
                serializer.save()
                results.append("created")
            except serializers.ValidationError:
                results.append("rejected")
            finally:
                connection.close()

        t1 = Thread(target=attempt, args=(380,))
        t2 = Thread(target=attempt, args=(520,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(sorted(results), ["created", "rejected"])
        rolls = ClothRoll.objects.filter(loft=self.loft, roll_code="RACE-1")
        self.assertEqual(rolls.count(), 1)

class CureRuleTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="keeper", password="x")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.loft = Loft.objects.create(name="甲间")

    def test_cannot_mark_cured_without_enough_cure_hours(self):
        roll = ClothRoll.objects.create(
            loft=self.loft, roll_code="C-1", status=ClothRoll.STATUS_DIPPING
        )
        DipRun.objects.create(
            roll=roll,
            started_at=timezone.now() - timedelta(hours=1),
            resin_pct="28.00",
            cure_hours="8.00",
        )
        resp = self.client.patch(
            f"/api/rolls/{roll.id}/", {"status": "cured"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("status", resp.data)
