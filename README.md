# Health Check Admin

건강 점수 관리자 대시보드입니다. 기존 화면 기능은 유지하면서 Google Apps Script/엑셀 직접 연동 대신 서버 API와 SQLite DB를 사용하도록 정리했습니다.

- 참여자별 설문 날짜 수
- 이름 검색 및 날짜별 최고 점수
- 최근 3일 설문자
- 최근 4개 점수 차트
- CSV 가져오기
- Docker 기반 AWS EC2 배포

## 로컬 실행

```powershell
python .\server.py
```

브라우저에서 아래 주소를 엽니다.

```text
http://127.0.0.1:8000/admin.html
```

데이터베이스 파일은 처음 실행할 때 `health_check.sqlite3`로 생성됩니다.

운영 서버처럼 모든 네트워크에서 접속 가능하게 실행하려면 아래처럼 실행합니다.

```powershell
$env:HOST="0.0.0.0"
$env:PORT="8000"
python .\server.py
```

## CSV 가져오기

엑셀 또는 Google 스프레드시트에서 CSV로 내보낸 뒤 가져올 수 있습니다.

```powershell
python .\import_csv.py .\survey.csv
```

인식하는 기본 컬럼명은 `이름`, `날짜`, `총점`, `흡연`, `걸음수`, `LDL`, `혈압`, `BMI`입니다. 영어 컬럼명 `name`, `date`, `totalScore`, `smoking`, `steps`, `ldl`, `bp`, `bmi`도 사용할 수 있습니다.

## Docker 실행

```powershell
docker compose up -d --build
```

브라우저에서 아래 주소를 엽니다.

```text
http://127.0.0.1:8000/admin.html
```

Docker 실행 시 DB는 `health-check-data` 볼륨의 `/data/health_check.sqlite3`에 저장됩니다.

## API

- `GET /api/name-summary`
- `GET /api/search-name?name=홍길동`
- `GET /api/recent-3days`
- `POST /api/survey-results`
- `GET /api/health`

`POST /api/survey-results` 예시:

```json
{
  "name": "홍길동",
  "date": "2026-06-17",
  "totalScore": 86,
  "smoking": "비흡연",
  "steps": "8500",
  "ldl": "110",
  "bp": "120/80",
  "bmi": "22.1"
}
```

원본 Google 스프레드시트 버튼을 계속 쓰려면 서버 실행 전에 환경변수 `SHEET_URL`을 지정합니다.

```powershell
$env:SHEET_URL="https://docs.google.com/spreadsheets/d/..."
python .\server.py
```

Docker에서는 `.env.example`을 `.env`로 복사한 뒤 `SHEET_URL` 값을 넣으면 됩니다.

## GitHub 업로드

```powershell
git init
git add .
git commit -m "Prepare health check admin for AWS deployment"
git branch -M main
git remote add origin https://github.com/<OWNER>/<REPO>.git
git push -u origin main
```

GitHub에 올리면 `.github/workflows/ci.yml`이 Python 문법 검사와 단위 테스트를 자동 실행합니다.

## AWS 배포

EC2 + Docker Compose 기준 배포 절차는 [deploy/aws-ec2.md](deploy/aws-ec2.md)를 참고하세요.
