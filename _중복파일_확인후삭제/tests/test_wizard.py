"""설치 마법사의 입력 처리 테스트.

여기가 틀리면 초보 사용자가 첫 화면에서 막힌다. 특히 비밀번호에
@ : / ? # 같은 기호가 있을 때 URL 인코딩을 빠뜨리면 접속이 실패하는데,
에러 메시지만 보고는 원인을 알 수 없다.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import wizard  # noqa: E402


class TestNormalizeDsn(unittest.TestCase):
    BASE = "postgresql://postgres.abcd:pw@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres"

    def test_adds_sslmode(self):
        dsn, notes = wizard.normalize_dsn(self.BASE)
        self.assertIn("sslmode=require", dsn)
        self.assertTrue(any("sslmode" in n for n in notes))

    def test_keeps_existing_sslmode(self):
        dsn, _ = wizard.normalize_dsn(self.BASE + "?sslmode=verify-full")
        self.assertEqual(dsn.count("sslmode"), 1)

    def test_strips_quotes_and_whitespace(self):
        dsn, _ = wizard.normalize_dsn(f'  "{self.BASE}"  ')
        self.assertTrue(dsn.startswith("postgresql://"))
        self.assertNotIn('"', dsn)

    def test_strips_psql_prefix(self):
        # Supabase 화면에서 'psql "postgresql://..."' 통째로 복사하는 일이 흔하다
        dsn, notes = wizard.normalize_dsn(f'psql "{self.BASE}"')
        self.assertTrue(dsn.startswith("postgresql://"))
        self.assertTrue(any("psql" in n for n in notes))

    def test_removes_embedded_newlines(self):
        # 메모장을 거치면 줄바꿈이 끼어든다
        broken = self.BASE[:40] + "\n   " + self.BASE[40:]
        dsn, _ = wizard.normalize_dsn(broken)
        self.assertNotIn("\n", dsn)
        self.assertNotIn(" ", dsn)
        self.assertTrue(dsn.startswith(self.BASE))

    def test_warns_on_wrong_scheme(self):
        _, notes = wizard.normalize_dsn("https://supabase.com/dashboard")
        self.assertTrue(any("postgresql://" in n for n in notes))

    def test_localhost_keeps_no_sslmode(self):
        dsn, _ = wizard.normalize_dsn("postgresql://postgres@localhost:5432/db")
        self.assertNotIn("sslmode", dsn)


class TestSupabaseMode(unittest.TestCase):
    """Supabase 화면 라벨은 바뀐다. 주소 모양으로 판정해야 한다."""

    DIRECT = "postgresql://postgres:pw@db.abcdefgh.supabase.co:5432/postgres"
    TRANSACTION = ("postgresql://postgres.abcdefgh:pw"
                   "@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres")
    SESSION = ("postgresql://postgres.abcdefgh:pw"
               "@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres")

    def test_classify(self):
        self.assertEqual(wizard.classify_dsn(self.DIRECT), "direct")
        self.assertEqual(wizard.classify_dsn(self.TRANSACTION), "transaction")
        self.assertEqual(wizard.classify_dsn(self.SESSION), "session")

    def test_transaction_is_converted_to_session(self):
        dsn, notes = wizard.fix_supabase_mode(self.TRANSACTION)
        self.assertEqual(wizard.classify_dsn(dsn), "session")
        self.assertIn(":5432", dsn)
        self.assertNotIn(":6543", dsn)
        self.assertTrue(notes)

    def test_session_is_left_alone(self):
        dsn, notes = wizard.fix_supabase_mode(self.SESSION)
        self.assertEqual(dsn, self.SESSION)
        self.assertEqual(notes, [])

    def test_direct_warns_but_still_works(self):
        dsn, notes = wizard.fix_supabase_mode(self.DIRECT)
        self.assertEqual(dsn, self.DIRECT, "임의로 고치지 않는다 — 경고만 한다")
        self.assertTrue(any("Direct" in n for n in notes))

    def test_normalize_applies_the_fix(self):
        dsn, notes = wizard.normalize_dsn(self.TRANSACTION)
        self.assertIn(":5432", dsn)
        self.assertIn("sslmode=require", dsn)
        self.assertTrue(any("Session pooler" in n for n in notes))

    def test_non_supabase_untouched(self):
        other = "postgresql://u:p@my-own-server.example.com:6543/db"
        dsn, notes = wizard.fix_supabase_mode(other)
        self.assertEqual(dsn, other, "Supabase 가 아니면 포트를 건드리지 않는다")
        self.assertEqual(notes, [])

    def test_password_containing_6543_is_not_mangled(self):
        dsn = ("postgresql://postgres.abcd:my6543pw"
               "@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres")
        fixed, _ = wizard.fix_supabase_mode(dsn)
        self.assertIn("my6543pw", fixed, "비밀번호 안의 숫자를 건드리면 안 된다")

    def test_password_with_colon_6543_on_transaction_url(self):
        # 비밀번호가 ':6543' 을 품고 있어도 호스트 포트만 바뀌어야 한다
        dsn = ("postgresql://postgres.abcd:pw%3A6543x"
               "@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres")
        fixed, _ = wizard.fix_supabase_mode(dsn)
        self.assertIn("pw%3A6543x", fixed)
        self.assertIn("pooler.supabase.com:5432", fixed)
        self.assertEqual(fixed.count("5432"), 1)


class TestPasswordPlaceholder(unittest.TestCase):
    TEMPLATE = ("postgresql://postgres.abcd:[YOUR-PASSWORD]"
                "@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres")

    def _fill(self, password: str) -> str:
        answers = iter([password])
        original = wizard.ask
        wizard.ask = lambda *a, **k: next(answers)   # type: ignore[assignment]
        try:
            return wizard.fill_password(self.TEMPLATE)
        finally:
            wizard.ask = original                    # type: ignore[assignment]

    def test_simple_password(self):
        self.assertIn(":sumo1234@", self._fill("sumo1234"))

    def test_at_sign_is_encoded(self):
        # 인코딩하지 않으면 @ 가 호스트 구분자로 읽혀 주소가 깨진다
        dsn = self._fill("pa@ss")
        self.assertIn("pa%40ss", dsn)
        self.assertEqual(dsn.count("@"), 1, "호스트 구분자 @ 는 하나뿐이어야 한다")

    def test_special_characters_are_encoded(self):
        dsn = self._fill("a/b?c#d:e")
        for raw in ("/", "?", "#"):
            self.assertNotIn(raw + "b", dsn.split("@")[0].split(":")[-1])
        self.assertIn("a%2Fb%3Fc%23d%3Ae", dsn)

    def test_no_placeholder_is_untouched(self):
        plain = "postgresql://postgres:pw@host:5432/db"
        self.assertEqual(wizard.fill_password(plain), plain)

    def test_rejects_literal_placeholder_then_accepts(self):
        answers = iter(["[YOUR-PASSWORD]", "realpw"])
        original = wizard.ask
        wizard.ask = lambda *a, **k: next(answers)    # type: ignore[assignment]
        try:
            dsn = wizard.fill_password(self.TEMPLATE)
        finally:
            wizard.ask = original                     # type: ignore[assignment]
        self.assertIn(":realpw@", dsn)


class TestMask(unittest.TestCase):
    def test_password_is_hidden(self):
        masked = wizard.mask("postgresql://user:secret123@host:5432/db")
        self.assertNotIn("secret123", masked)
        self.assertIn("host:5432/db", masked)

    def test_no_password_is_safe(self):
        self.assertEqual(wizard.mask("postgresql://host/db"),
                         "postgresql://host/db")


class TestEnvFile(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path

        self._tmp = tempfile.TemporaryDirectory()
        self._orig = wizard.ENV_PATH
        wizard.ENV_PATH = Path(self._tmp.name) / ".env"

    def tearDown(self):
        wizard.ENV_PATH = self._orig
        self._tmp.cleanup()

    def test_roundtrip(self):
        wizard.write_env({"DATABASE_URL": "postgresql://a@b/c", "SHEET_ID": ""})
        got = wizard.read_env()
        self.assertEqual(got["DATABASE_URL"], "postgresql://a@b/c")
        self.assertEqual(got["SHEET_ID"], "")

    def test_comments_ignored(self):
        wizard.ENV_PATH.write_text(
            "# 주석\n\nDATABASE_URL=postgresql://x\n", encoding="utf-8")
        self.assertEqual(wizard.read_env()["DATABASE_URL"], "postgresql://x")

    def test_value_with_equals_survives(self):
        wizard.write_env({"DATABASE_URL": "postgresql://a@b/c?x=1&y=2"})
        self.assertEqual(wizard.read_env()["DATABASE_URL"],
                         "postgresql://a@b/c?x=1&y=2")

    def test_missing_file_is_empty(self):
        self.assertEqual(wizard.read_env(), {})


class TestRanges(unittest.TestCase):
    def test_ranges_are_sane(self):
        for label, start, n, mins in wizard.RANGES:
            self.assertRegex(start, r"^\d{6}$")
            self.assertEqual(int(start[4:]) % 2, 1, "본바쇼는 홀수 달에만 열린다")
            self.assertGreater(n, 0)
            self.assertGreater(mins, 0)

    def test_ranges_are_ordered_oldest_last(self):
        starts = [int(r[1]) for r in wizard.RANGES]
        self.assertEqual(starts, sorted(starts, reverse=True),
                         "짧은 범위가 위에 와야 초보자가 고르기 쉽다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
