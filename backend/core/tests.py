import threading
from unittest import mock

from django.db import connections
from django.test import TestCase, TransactionTestCase
from rest_framework import serializers as drf_serializers
from rest_framework.test import APIClient

from accounts.models import User

from .models import ClothRoll, DipRun, Loft
from .serializers import ClothRollSerializer


def make_loft(name="东间", **kwargs):
    return Loft.objects.create(name=name, **kwargs)


def make_roll(loft, code="R-001", **kwargs):
    defaults = {"fabric_weight_gsm": 380}
    defaults.update(kwargs)
    return ClothRoll.objects.create(loft=loft, roll_code=code, **defaults)


def roll_payload(loft, code, **extra):
    payload = {"loftId": loft.id, "rollCode": code, "fabricWeightGsm": 380}
    payload.update(extra)
    return payload


class LoftDeleteTests(TestCase):
    """删间：整间连卷带浸渍一起消失，不允许间没了卷还在。"""

    def setUp(self):
        self.user = User.objects.create_user(username="keeper", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_delete_loft_cascades_rolls_and_dip_runs(self):
        loft = make_loft()
        roll_a = make_roll(loft, "R-001")
        roll_b = make_roll(loft, "R-002")
        DipRun.objects.create(
            roll=roll_a, started_at="2026-10-01T08:00:00Z", resin_pct="28.5"
        )
        DipRun.objects.create(
            roll=roll_b, started_at="2026-10-02T08:00:00Z", resin_pct="30.0"
        )
        other = make_loft(name="西间")
        other_roll = make_roll(other, "R-001")
        DipRun.objects.create(
            roll=other_roll, started_at="2026-10-03T08:00:00Z", resin_pct="29.0"
        )

        resp = self.client.delete(f"/api/lofts/{loft.id}/")

        self.assertEqual(resp.status_code, 204)
        # 间、卷、浸渍全部真正消失，不是改名标记
        self.assertFalse(Loft.objects.filter(id=loft.id).exists())
        self.assertEqual(ClothRoll.objects.filter(loft_id=loft.id).count(), 0)
        self.assertEqual(DipRun.objects.filter(roll__loft_id=loft.id).count(), 0)
        # 别间数据不受影响
        self.assertTrue(Loft.objects.filter(id=other.id).exists())
        self.assertTrue(ClothRoll.objects.filter(id=other_roll.id).exists())
        self.assertEqual(DipRun.objects.filter(roll=other_roll).count(), 1)

    def test_deleted_loft_gone_from_ledger_and_dip_feed(self):
        loft = make_loft()
        roll = make_roll(loft, "GONE-9")
        DipRun.objects.create(
            roll=roll, started_at="2026-10-01T08:00:00Z", resin_pct="28.5"
        )

        self.client.delete(f"/api/lofts/{loft.id}/")

        rolls = self.client.get("/api/rolls/").data["results"]
        self.assertNotIn("GONE-9", [r["rollCode"] for r in rolls])
        dips = self.client.get("/api/dips/").data["results"]
        self.assertEqual(dips, [])

    def test_roll_code_reusable_in_new_loft_after_delete(self):
        loft = make_loft()
        make_roll(loft, "R-777")
        self.client.delete(f"/api/lofts/{loft.id}/")

        new_loft = make_loft(name="东间")
        resp = self.client.post(
            "/api/rolls/", roll_payload(new_loft, "R-777"), format="json"
        )

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(ClothRoll.objects.filter(roll_code="R-777").count(), 1)


class RollUniquenessTests(TestCase):
    """同间卷码唯一：撞码必须挡住，不许覆盖旧卷。"""

    def setUp(self):
        self.user = User.objects.create_user(username="keeper", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.loft = make_loft()

    def test_duplicate_code_rejected_and_existing_roll_untouched(self):
        resp = self.client.post(
            "/api/rolls/",
            roll_payload(self.loft, "R-100", notes="原始卷", fabricWeightGsm=380),
            format="json",
        )
        self.assertEqual(resp.status_code, 201)

        resp = self.client.post(
            "/api/rolls/",
            roll_payload(self.loft, "R-100", notes="撞码新卷", fabricWeightGsm=999),
            format="json",
        )

        self.assertEqual(resp.status_code, 400)
        self.assertIn("rollCode", resp.data)
        # 旧卷字段不被改写
        roll = ClothRoll.objects.get(loft=self.loft, roll_code="R-100")
        self.assertEqual(roll.notes, "原始卷")
        self.assertEqual(roll.fabric_weight_gsm, 380)
        self.assertEqual(ClothRoll.objects.filter(loft=self.loft).count(), 1)

    def test_duplicate_code_rejected_on_update(self):
        make_roll(self.loft, "R-1")
        roll_b = make_roll(self.loft, "R-2")

        resp = self.client.patch(
            f"/api/rolls/{roll_b.id}/", {"rollCode": "R-1"}, format="json"
        )

        self.assertEqual(resp.status_code, 400)
        roll_b.refresh_from_db()
        self.assertEqual(roll_b.roll_code, "R-2")

    def test_same_code_allowed_in_different_lofts(self):
        make_roll(self.loft, "R-1")
        other = make_loft(name="西间")

        resp = self.client.post(
            "/api/rolls/", roll_payload(other, "R-1"), format="json"
        )

        self.assertEqual(resp.status_code, 201)

    def test_update_keeping_own_code_ok(self):
        roll = make_roll(self.loft, "R-1")

        resp = self.client.patch(
            f"/api/rolls/{roll.id}/",
            {"rollCode": "R-1", "notes": "改备注"},
            format="json",
        )

        self.assertEqual(resp.status_code, 200)
        roll.refresh_from_db()
        self.assertEqual(roll.notes, "改备注")

    def test_race_fallback_integrity_error_returns_400(self):
        """校验通过到落库之间被抢先写入同码卷：约束兜底，返回 400 而非 500。"""
        serializer = ClothRollSerializer(
            data=roll_payload(self.loft, "RACE-1")
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        # 校验通过后、保存前，另一请求已写入同码卷
        make_roll(self.loft, "RACE-1")

        with self.assertRaises(drf_serializers.ValidationError):
            serializer.save()

        self.assertEqual(
            ClothRoll.objects.filter(loft=self.loft, roll_code="RACE-1").count(), 1
        )


class ConcurrentCreateTests(TransactionTestCase):
    """两名仓管交叉在同一间新建同一卷码：只许一笔进库。"""

    def test_concurrent_same_code_only_one_commits(self):
        loft = make_loft()
        User.objects.create_user(username="keeper_a", password="pw")
        User.objects.create_user(username="keeper_b", password="pw")

        # 让两个请求都先通过应用层校验，再同时落库，稳定复现竞态窗口
        barrier = threading.Barrier(2)
        original_validate = ClothRollSerializer.validate

        def gated_validate(serializer, attrs):
            attrs = original_validate(serializer, attrs)
            barrier.wait(timeout=10)
            return attrs

        results = {}

        def worker(name, username, notes):
            try:
                client = APIClient()
                client.force_authenticate(
                    User.objects.get(username=username)
                )
                resp = client.post(
                    "/api/rolls/",
                    roll_payload(loft, "RACE-1", notes=notes),
                    format="json",
                )
                results[name] = resp.status_code
            finally:
                connections.close_all()

        with mock.patch.object(ClothRollSerializer, "validate", gated_validate):
            t1 = threading.Thread(
                target=worker, args=("a", "keeper_a", "仓管甲")
            )
            t2 = threading.Thread(
                target=worker, args=("b", "keeper_b", "仓管乙")
            )
            t1.start()
            t2.start()
            t1.join(20)
            t2.join(20)

        self.assertFalse(t1.is_alive() or t2.is_alive(), "并发请求未在限时内完成")
        # 一笔进库，一笔被干净地拒绝
        self.assertEqual(sorted(results.values()), [201, 400])
        rolls = ClothRoll.objects.filter(loft=loft, roll_code="RACE-1")
        self.assertEqual(rolls.count(), 1)
