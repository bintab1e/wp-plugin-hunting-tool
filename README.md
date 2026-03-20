# wp-plugin-hunting-tool
## 구성
- `downloader.py`: 워드프레스 플러그인 사이트에서 태그 기반으로 검색하여 플러그인 ZIP 파일 다운로드 후 `plugins/`에 압축 해제 및 ZIP 파일 삭제
- `scanner.py`: `plugins/` 내 PHP 파일을 정해진 규칙(`rules.json`)으로 스캔하여 결과를 `findings.db`에 저장
- `init_findings_db.py`: `findings.db`의 `findings` 테이블 초기화(생성)
