# AWS EC2 배포 가이드

이 프로젝트는 작은 관리자 도구 기준으로 `EC2 + Docker Compose + SQLite 볼륨` 배포를 기본으로 합니다. 데이터가 많아지거나 여러 서버에서 동시에 운영해야 하면 SQLite 대신 RDS(PostgreSQL)로 옮기는 편이 좋습니다.

## 1. EC2 생성

권장 시작값:

- Ubuntu Server 24.04 LTS
- t3.micro 또는 t3.small
- 보안 그룹 인바운드: SSH 22, HTTP 80, 앱 테스트용 TCP 8000
- 운영 도메인을 붙일 예정이면 8000은 내 IP에서만 열고, 최종 공개는 80/443으로 처리

## 2. 서버 접속

```bash
ssh -i your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
```

## 3. Docker 설치

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker ubuntu
```

설치 후 SSH를 끊고 다시 접속합니다.

## 4. GitHub 저장소 가져오기

```bash
git clone https://github.com/<OWNER>/<REPO>.git
cd <REPO>
```

## 5. 실행

관리자 계정 설정 파일을 만듭니다.

```bash
cp .env.example .env
nano .env
```

아래 값을 실제 사용할 값으로 변경합니다.

```dotenv
ADMIN_USERNAME=원하는-관리자-아이디
ADMIN_PASSWORD=16자-이상의-고유한-비밀번호
ADMIN_SESSION_SECRET=무작위-세션-서명키
ADMIN_SESSION_HOURS=8
ADMIN_COOKIE_SECURE=0
```

세션 서명키는 서버에서 아래 명령으로 생성할 수 있습니다.

```bash
openssl rand -hex 32
```

HTTP로 기능을 확인하는 동안에는 `ADMIN_COOKIE_SECURE=0`을 사용합니다.
도메인과 HTTPS를 적용한 뒤에는 반드시 `ADMIN_COOKIE_SECURE=1`로 변경합니다.

```bash
docker compose up -d --build
docker compose ps
```

브라우저에서 확인:

```text
설문조사: http://YOUR_EC2_PUBLIC_IP:8000/
DB 관리자: http://YOUR_EC2_PUBLIC_IP:8000/admin.html
```

관리자 페이지는 `.env`에 설정한 아이디와 비밀번호로 로그인합니다.

## 6. 업데이트 배포

GitHub에 새 코드를 push한 뒤 EC2에서:

```bash
git pull
docker compose up -d --build
```

SQLite DB는 Docker 볼륨에 저장되므로 일반적인 재빌드/재시작으로 삭제되지 않습니다.

## 7. 선택: 80번 포트로 공개

간단히 80번 포트로 바로 열려면 `docker-compose.yml`의 포트를 아래처럼 바꿀 수 있습니다.

```yaml
ports:
  - "80:8000"
```

도메인과 HTTPS까지 운영하려면 Nginx 또는 Caddy를 앞단에 두는 구성이 좋습니다.

## 8. 백업

운영 DB 백업:

```bash
docker run --rm -v health_check_health-check-data:/data -v "$PWD":/backup busybox cp /data/health_check.sqlite3 /backup/health_check.sqlite3
```

복구할 때는 컨테이너를 멈춘 뒤 같은 볼륨의 `/data/health_check.sqlite3` 위치로 복사합니다.
