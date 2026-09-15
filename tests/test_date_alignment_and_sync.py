"""
[Tests] Date Alignment & Latest Output Sync Architecture Tests
==============================================================
- TEST A: 2026-09-05 최신 산출물 생성 및 latest preview가 2026-09-05를 가리키는지 확인
- TEST B: 2026-09-04 rerender 실행 시 data/output/2026-09-04만 변경되고 latest preview / 2026-09-05는 불변
- TEST C: 2026-09-04 validation + 2026-09-05 processed 의도적 조합 시 DateMismatchError 발생
- TEST D: 2026-09-05 validation + 2026-09-04 processed 의도적 조합 시 차단
- TEST E: 00:30 KST 실행과 23:00 KST 실행 모두 같은 날짜 원칙으로 정상 처리되는지 확인
"""

import os
import json
import unittest
import copy
from generators.blog_formatter import NaverBlogFormatter
from generators.report_generator import (
    get_latest_canonical_date,
    sync_latest_output,
    rerender_date_report
)

import tempfile
import shutil

class TestDateAlignmentAndSync(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_data_dir = self.temp_dir.name

        # 2026-09-04 및 2026-09-05 픽스처만 복사
        for sub in ["processed", os.path.join("generated", "2026-09-04"), os.path.join("generated", "2026-09-05"), os.path.join("output", "2026-09-04"), os.path.join("output", "2026-09-05")]:
            os.makedirs(os.path.join(self.base_data_dir, sub), exist_ok=True)

        for f in ["2026-09-04.json", "2026-09-05.json"]:
            src = os.path.join("data", "processed", f)
            if os.path.exists(src):
                shutil.copy(src, os.path.join(self.base_data_dir, "processed", f))

        for d in ["2026-09-04", "2026-09-05"]:
            src_val = os.path.join("data", "generated", d, "validation.json")
            if os.path.exists(src_val):
                shutil.copy(src_val, os.path.join(self.base_data_dir, "generated", d, "validation.json"))
            for out_f in ["blog_post.html", "blog_post.txt"]:
                src_out = os.path.join("data", "output", d, out_f)
                if os.path.exists(src_out):
                    shutil.copy(src_out, os.path.join(self.base_data_dir, "output", d, out_f))

        self.proc_04_path = os.path.join(self.base_data_dir, "processed", "2026-09-04.json")
        self.proc_05_path = os.path.join(self.base_data_dir, "processed", "2026-09-05.json")
        self.val_04_path = os.path.join(self.base_data_dir, "generated", "2026-09-04", "validation.json")
        self.val_05_path = os.path.join(self.base_data_dir, "generated", "2026-09-05", "validation.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_test_a_latest_preview_points_to_2026_09_05(self):
        """TEST A: 2026-09-05 최신 산출물 생성 및 latest preview가 2026-09-05를 가리키는지 확인"""
        latest_date = get_latest_canonical_date(self.base_data_dir)
        self.assertEqual(latest_date, "2026-09-05", "저장소의 canonical latest date는 2026-09-05여야 합니다.")

        res = sync_latest_output(self.base_data_dir)
        self.assertTrue(res["success"])
        self.assertTrue(res["synced"])
        self.assertEqual(res["canonical_latest_date"], "2026-09-05")

        # preview 파일 내용 검증
        preview_html_path = os.path.join(self.base_data_dir, "generated", "latest_preview.html")
        preview_txt_path = os.path.join(self.base_data_dir, "generated", "latest_preview.txt")
        blog_html_path = os.path.join(self.base_data_dir, "generated", "blog_post.html")

        self.assertTrue(os.path.exists(preview_html_path))
        self.assertTrue(os.path.exists(preview_txt_path))
        self.assertTrue(os.path.exists(blog_html_path))

        with open(preview_html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        with open(preview_txt_path, "r", encoding="utf-8") as f:
            txt_content = f.read()

        # 2026-09-05 헤더 및 NFP actual(+162K) 확인
        self.assertIn("2026-09-05 | 00:53 기준", html_content)
        self.assertIn("+162K", html_content)
        self.assertIn("+21K", html_content)
        self.assertIn("(수정)", html_content)
        self.assertIn("+162K", txt_content)
        self.assertIn("+21K(수정)", txt_content)

    def test_test_b_rerender_past_date_does_not_overwrite_latest_preview(self):
        """TEST B: 2026-09-04 rerender 실행 시 data/output/2026-09-04만 변경되고 latest preview / 2026-09-05는 불변"""
        # 먼저 latest preview가 2026-09-05로 동기화되어 있음을 보장
        sync_latest_output(self.base_data_dir)

        preview_html_path = os.path.join(self.base_data_dir, "generated", "latest_preview.html")
        blog_html_path = os.path.join(self.base_data_dir, "generated", "blog_post.html")
        out_05_html_path = os.path.join(self.base_data_dir, "output", "2026-09-05", "blog_post.html")

        with open(preview_html_path, "r", encoding="utf-8") as f:
            preview_before = f.read()
        with open(out_05_html_path, "r", encoding="utf-8") as f:
            out_05_before = f.read()

        # 2026-09-04 과거 날짜 rerender 실행
        rerender_res = rerender_date_report("2026-09-04", base_data_dir=self.base_data_dir, sync_if_latest=True)
        self.assertTrue(rerender_res["success"])
        self.assertEqual(rerender_res["report_date"], "2026-09-04")

        # 2026-09-04 산출물이 정상 갱신되었는지 확인
        out_04_html_path = os.path.join(self.base_data_dir, "output", "2026-09-04", "blog_post.html")
        self.assertTrue(os.path.exists(out_04_html_path))

        # latest preview 및 2026-09-05 output이 과거 데이터로 덮어씌워지지 않았는지 엄격 검증
        with open(preview_html_path, "r", encoding="utf-8") as f:
            preview_after = f.read()
        with open(out_05_html_path, "r", encoding="utf-8") as f:
            out_05_after = f.read()
        with open(blog_html_path, "r", encoding="utf-8") as f:
            blog_after = f.read()

        self.assertEqual(preview_before, preview_after, "2026-09-04 rerender는 latest_preview.html을 변경해서는 안 됩니다.")
        self.assertEqual(out_05_before, out_05_after, "2026-09-04 rerender는 2026-09-05 산출물을 변경해서는 안 됩니다.")
        self.assertIn("2026-09-05 | 00:53 기준", blog_after, "blog_post.html은 최신 2026-09-05를 유지해야 합니다.")
        self.assertIn("+162K", blog_after, "blog_post.html은 +162K 최신 지표를 유지해야 합니다.")

    def test_test_c_mismatch_val04_with_proc05_raises_error(self):
        """TEST C: 2026-09-04 validation + 2026-09-05 processed 의도적 조합 시 DateMismatchError 발생"""
        with open(self.val_04_path, "r", encoding="utf-8") as f:
            val_04 = json.load(f)
        with open(self.proc_05_path, "r", encoding="utf-8") as f:
            proc_05 = json.load(f)

        with self.assertRaises(ValueError) as ctx:
            NaverBlogFormatter.format_blog_html(val_04, proc_05)
        self.assertIn("DateMismatchError", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            NaverBlogFormatter.format_blog_text(val_04, proc_05)
        self.assertIn("DateMismatchError", str(ctx.exception))

    def test_test_d_mismatch_val05_with_proc04_raises_error(self):
        """TEST D: 2026-09-05 validation + 2026-09-04 processed 의도적 조합 시 차단"""
        with open(self.val_05_path, "r", encoding="utf-8") as f:
            val_05 = json.load(f)
        with open(self.proc_04_path, "r", encoding="utf-8") as f:
            proc_04 = json.load(f)

        with self.assertRaises(ValueError) as ctx:
            NaverBlogFormatter.format_blog_html(val_05, proc_04)
        self.assertIn("DateMismatchError", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            NaverBlogFormatter.format_blog_text(val_05, proc_04)
        self.assertIn("DateMismatchError", str(ctx.exception))

    def test_test_e_execution_at_different_times_with_same_date(self):
        """TEST E: 00:30 KST 실행과 23:00 KST 실행 모두 같은 날짜 원칙으로 정상 처리되는지 확인"""
        with open(self.val_05_path, "r", encoding="utf-8") as f:
            val_base = json.load(f)
        with open(self.proc_05_path, "r", encoding="utf-8") as f:
            proc_base = json.load(f)

        # 1) 00:30 KST 실행 시뮬레이션
        val_0030 = copy.deepcopy(val_base)
        proc_0030 = copy.deepcopy(proc_base)
        val_0030["report_date"] = "2026-09-05"
        val_0030["run_time_kst"] = "2026-09-05 00:30:00 KST"
        proc_0030["report_date"] = "2026-09-05"
        proc_0030["run_time_kst"] = "2026-09-05 00:30:00 KST"

        html_0030 = NaverBlogFormatter.format_blog_html(val_0030, proc_0030)
        txt_0030 = NaverBlogFormatter.format_blog_text(val_0030, proc_0030)
        self.assertIn("2026-09-05 | 00:30 기준", html_0030)
        self.assertIn("2026-09-05 | 00:30 기준", txt_0030)

        # 2) 23:00 KST 실행 시뮬레이션
        val_2300 = copy.deepcopy(val_base)
        proc_2300 = copy.deepcopy(proc_base)
        val_2300["report_date"] = "2026-09-05"
        val_2300["run_time_kst"] = "2026-09-05 23:00:00 KST"
        proc_2300["report_date"] = "2026-09-05"
        proc_2300["run_time_kst"] = "2026-09-05 23:00:00 KST"

        html_2300 = NaverBlogFormatter.format_blog_html(val_2300, proc_2300)
        txt_2300 = NaverBlogFormatter.format_blog_text(val_2300, proc_2300)
        self.assertIn("2026-09-05 | 23:00 기준", html_2300)
        self.assertIn("2026-09-05 | 23:00 기준", txt_2300)

if __name__ == "__main__":
    unittest.main()
