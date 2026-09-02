"""
====================================================================
[FICC Daily Macro] 데이터 저장 전담 모듈 (Data Saver Module)
====================================================================
- 역할:
    1. 28개 지표 및 스프레드, 메타데이터를 표준화된 JSON 형식으로 직렬화
    2. Dual-Layer 저장 방식 구현:
        - 메인 최신본: data/YYYY-MM-DD/market_data.json
        - 실행 이력본: data/YYYY-MM-DD/runs/market_data_HHMMSS.json
    3. UTF-8 인코딩 및 가독성 높은 들여쓰기(indent=2) 보장
"""

import os
import json
import datetime
from pathlib import Path

def save_daily_market_data(payload: dict, base_dir: str = "data") -> dict:
    """
    수집된 28개 지표 및 스프레드 데이터를 지정된 경로에 JSON 파일로 저장합니다.
    
    Args:
        payload (dict): metadata, spreads, market_data를 포함하는 딕셔너리
        base_dir (str): 데이터 저장 루트 디렉토리 (기본값: 'data')
        
    Returns:
        dict: 저장 성공 여부, 파일 경로, 파일 크기 등의 메타정보
    """
    try:
        report_date = payload.get("metadata", {}).get("report_date", datetime.datetime.now().strftime("%Y-%m-%d"))
        
        # 현재 실행 시각 기준 HHMMSS 포맷 생성
        now = datetime.datetime.now()
        time_stamp_str = now.strftime("%H%M%S")
        
        # 디렉토리 경로 생성
        target_dir = Path(base_dir) / report_date
        runs_dir = target_dir / "runs"
        
        target_dir.mkdir(parents=True, exist_ok=True)
        runs_dir.mkdir(parents=True, exist_ok=True)
        
        # 파일 경로 정의
        main_file_path = target_dir / "market_data.json"
        history_file_path = runs_dir / f"market_data_{time_stamp_str}.json"
        
        # JSON 직렬화 (UTF-8, ensure_ascii=False, indent=2)
        json_content = json.dumps(payload, ensure_ascii=False, indent=2)
        
        # 1. 메인 최신 파일 저장 (market_data.json)
        with open(main_file_path, "w", encoding="utf-8") as f:
            f.write(json_content)
            
        # 2. 실행 이력 파일 저장 (runs/market_data_HHMMSS.json)
        with open(history_file_path, "w", encoding="utf-8") as f:
            f.write(json_content)
            
        file_size_bytes = os.path.getsize(main_file_path)
        
        return {
            "status": "SUCCESS",
            "report_date": report_date,
            "main_file": str(main_file_path.resolve()),
            "history_file": str(history_file_path.resolve()),
            "file_size_bytes": file_size_bytes,
            "equity_count": len(payload.get("market_data", {}).get("equity", [])),
            "fx_count": len(payload.get("market_data", {}).get("fx", [])),
            "bond_count": len(payload.get("market_data", {}).get("bond", [])),
            "commodity_count": len(payload.get("market_data", {}).get("commodity", [])),
            "spread_count": len(payload.get("spreads", {})),
            "message": "Dual-layer JSON 저장 완료 (최신본 + 실행이력)"
        }
        
    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
            "message": f"데이터 저장 중 예외 발생: {e}"
        }
