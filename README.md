# Health Check Admin

건강 점수 관리자 대시보드입니다. 기존 화면 기능은 유지하면서 Google Apps Script/엑셀 직접 연동 대신 서버 API와 SQLite DB를 사용하도록 정리했습니다.

- 참여자별 설문 날짜 수
- 이름 검색 및 날짜별 최고 점수
- 최근 3일 설문자
- 최근 4개 점수 차트
- SQLite 전체 데이터 표
- Excel 호환 CSV 다운로드
- 설문/관리자 주소 복사 및 설문 QR 코드 생성
- CSV 가져오기
- Docker 기반 AWS EC2 배포

## 로컬 실행

```powershell
$env:ADMIN_USERNAME="원하는-관리자-아이디"
$env:ADMIN_PASSWORD="16자-이상의-고유한-비밀번호"
$env:ADMIN_SESSION_SECRET="충분히-긴-무작위-문자열"
python .\server.py
```

브라우저에서 용도에 맞는 주소를 엽니다.

```text
설문조사: http://127.0.0.1:8000/
DB 관리자: http://127.0.0.1:8000/admin.html
```

설문조사는 5개 건강 항목을 합산한 25점 만점 점수를 SQLite에 직접 저장합니다.

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

`.env.example`을 `.env`로 복사하고 관리자 계정 값을 설정합니다.

```powershell
Copy-Item .env.example .env
notepad .env
```

`ADMIN_SESSION_SECRET`은 아래처럼 생성할 수 있습니다.

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

그다음 컨테이너를 실행합니다.

```powershell
docker compose up -d --build
```

브라우저에서 아래 주소를 엽니다.

```text
설문조사: http://127.0.0.1:8000/
DB 관리자: http://127.0.0.1:8000/admin.html
```

Docker 실행 시 DB는 `health-check-data` 볼륨의 `/data/health_check.sqlite3`에 저장됩니다.

## API

- `GET /api/name-summary`
- `GET /api/search-name?name=홍길동`
- `GET /api/recent-3days`
- `GET /api/results`
- `GET /api/export.csv`
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

관리자 화면의 `CSV 다운로드` 버튼으로 DB 전체 데이터를 내려받을 수 있습니다.
파일은 UTF-8 형식이며 Microsoft Excel에서 바로 열 수 있습니다.

## 관리자 인증

- 설문 페이지와 `POST /api/survey-results`는 공개됩니다.
- 관리자 페이지와 데이터 조회·검색·CSV API는 로그인 세션으로 보호됩니다.
- 아이디와 비밀번호는 `.env` 또는 서버 환경변수에만 저장하며 Git에 올리지 않습니다.
- `ADMIN_COOKIE_SECURE=0`은 HTTP 테스트용입니다. HTTPS 적용 후에는 `1`로 변경하세요.
- 로그인 세션의 기본 유효 시간은 8시간이며 `ADMIN_SESSION_HOURS`로 변경할 수 있습니다.

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
