"""
[FICC Daily Macro] 데이터 저장 관리자 (Storage Saver)
- data/raw/YYYY-MM-DD_HHMMSS_{MODE}.json: 모든 실행 회차별 원천 스냅샷 영구 보존 (절대 덮어쓰지 않음)
- data/processed/YYYY-MM-DD.json: 해당 일자의 최신 가공 데이터 (AI/블로그 생성용 메인 입력)
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

class DataSaver:
    """일자별 수집 및 가공 데이터 영구 저장 관리자"""

    def __init__(self, base_data_dir: str = "data"):
        self.base_data_dir = base_data_dir
        self.raw_dir = os.path.join(base_data_dir, "raw")
        self.processed_dir = os.path.join(base_data_dir, "processed")
        self._ensure_directories()

    def _ensure_directories(self):
        """저장 디렉토리 존재 보장"""
        os.makedirs(self.raw_dir, exist_ok=True)
        os.makedirs(self.processed_dir, exist_ok=True)

    def save_raw(self, raw_records: List[Dict[str, Any]], run_time_kst: datetime, is_post_1630: bool) -> str:
        """
        원천 수집 데이터 타임스탬프 스냅샷 JSON 저장 (덮어쓰기 방지)
        - 16:30 이후: YYYY-MM-DD_HHMMSS_CONFIRMED.json
        - 16:30 이전: YYYY-MM-DD_HHMMSS_TEST.json
        """
        date_str = run_time_kst.strftime("%Y-%m-%d")
        time_suffix = run_time_kst.strftime("%Y-%m-%d_%H%M%S")
        mode_suffix = "CONFIRMED" if is_post_1630 else "TEST"
        file_name = f"{time_suffix}_{mode_suffix}.json"
        file_path = os.path.join(self.raw_dir, file_name)

        payload = {
            "report_date": date_str,
            "run_time_kst": run_time_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
            "execution_mode": "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST",
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "snapshot_file": file_name,
            "total_count": len(raw_records),
            "records": raw_records
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        return file_path

    def save_processed(self, processed_data: Dict[str, Any], run_time_kst: datetime, is_post_1630: bool, raw_snapshot_path: Optional[str] = None) -> str:
        """
        가공 및 스프레드 계산 결과 JSON 저장 (해당 날짜의 최신본 갱신)
        AI / 블로그 파이프라인에서 기본 입력으로 사용
        """
        date_str = run_time_kst.strftime("%Y-%m-%d")
        file_path = os.path.join(self.processed_dir, f"{date_str}.json")

        payload = {
            "report_date": date_str,
            "run_time_kst": run_time_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
            "execution_mode": "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST",
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source_raw_snapshot": os.path.basename(raw_snapshot_path) if raw_snapshot_path else "N/A",
            **processed_data
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        return file_path

    def load_processed(self, date_str: str) -> Optional[Dict[str, Any]]:
        """과거 특정 일자의 최신 가공 데이터 로드"""
        file_path = os.path.join(self.processed_dir, f"{date_str}.json")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def list_raw_snapshots(self, date_str: Optional[str] = None) -> List[str]:
        """저장된 원천 스냅샷 파일 목록 조회"""
        files = sorted(os.listdir(self.raw_dir))
        if date_str:
            return [f for f in files if f.startswith(date_str)]
        return files
