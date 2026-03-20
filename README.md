# wp-plugin-hunting-tool
## 구성
- `downloader.py`: 워드프레스 플러그인 사이트에서 태그 기반으로 검색하여 플러그인 ZIP 파일 다운로드 후 `plugins/`에 압축 해제 및 ZIP 파일 삭제
- `scanner.py`: `plugins/` 내 PHP 파일을 정해진 규칙(`rules.json`)으로 스캔하여 결과를 `findings.db`에 저장
- `init_findings_db.py`: `findings.db`의 `findings` 테이블 초기화(생성)

## 사용법
```bash
python init_findings_db.py
python downloader.py
python scanner.py
```
scanner.py 실행 후 터미널에 노출된 예상 취약 코드(규칙 매칭 결과)를 확인하고, 해당 플러그인 코드를 수동으로 분석
원하는 규칙만 스캔하려면 rules.json에서 불필요한 rule의 enabled 값을 false로 변경
