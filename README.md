헥토 행동 데이터 트래커 (net_thrue_01)

웹/앱 행동 이벤트를 변수·트리거·태그 설정으로 수집하고, Kafka를 통해 저장·분석하는 자체 인프라 기반 트래킹 서비스입니다.

---

1. 실행 방법 (Docker Compose)

요구 사항

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/) (v2 권장)

서비스 기동

프로젝트 루트에서 다음 명령을 실행하세요.

```bash
docker compose up -d
```

- PostgreSQL, Zookeeper, Kafka, API 서버, Kafka 컨슈머, 퍼널 집계, Kafka UI가 함께 기동됩니다.
- 최초 실행 시 DB 테이블이 자동 생성되고, 초기 관리자 계정(admin / admin) 이 생성됩니다.

서비스 중지

```bash
docker compose down
```

---

2. 로그인

접속 주소

- 로그인·서비스 진입: [http://localhost:8000/static/login.html](http://localhost:8000/static/login.html)
- API 기준 주소: [http://localhost:8000](http://localhost:8000)

초기 관리자 계정 (Docker 기동 시 자동 생성)

| 항목 | 값 |
|------|-----|
| ID | `admin` |
| 비밀번호 | `admin` |

위 계정으로 로그인하면 관리자(admin) 로 들어가며, 컨테이너(트래커) 설정·배포·계정 관리를 할 수 있습니다.

일반 사용자

- 회원가입: [http://localhost:8000/static/signup.html](http://localhost:8000/static/signup.html) 에서 가입 가능.
- 가입 후 관리자가 승인해야 로그인할 수 있습니다.
- 관리자는 계정 관리 페이지에서 대기 중인 사용자를 승인하고, admin 또는 user 권한을 지정할 수 있습니다.

---

3. 서비스 사용 방법

3.1 관리자(admin)로 로그인한 경우

로그인 후 컨테이너 관리(Admin) 화면으로 이동합니다. (기존 와이즈콜렉터 태그 트리거 변수 설정은 되어 있어 추가 수정 할 필요 없습니다.)

| 메뉴/기능 | 설명 |
|-----------|------|
| 변수·트리거·태그 편집| 수집할 데이터와 발동 조건을 설정합니다. |
|배포| 편집한 설정을 “현재 적용 설정”으로 반영합니다. 배포 후 웹/앱에 삽입된 ntm.js가 새 설정을 받아 동작합니다. |
| 배포 이력·롤백 | 이전 버전으로 되돌리기, 버전 삭제 등이 가능합니다. |
| 행동 분석 대시보드 | 페이지뷰·퍼널·히트맵 등 행동 분석 대시보드로 이동합니다. |
| 계정 관리 | 가입 대기 사용자 승인, 권한(admin/user) 지정을 합니다. |

3.2 일반 사용자(user)로 로그인한 경우

로그인 후 행동 분석 대시보드로 이동합니다.

- 페이지별 이벤트, 퍼널 분석, 스크롤·클릭 히트맵 등을 기간·필터를 바꿔가며 조회할 수 있습니다.
- 컨테이너 설정·배포·계정 관리는 관리자만 가능하므로, 해당 메뉴는 보이지 않거나 접근 시 차단됩니다.

3.3 대시보드 사용

- 행동 분석 대시보드는 관리자·일반 사용자 모두 이용 가능합니다.
- 기간, 페이지, 채널, 행동 유형 등으로 필터링해 데이터를 조회합니다.
- 퍼널은 “퍼널 집계 실행”으로 일별 집계를 갱신할 수 있습니다 (또는 백그라운드에서 주기 실행).

---

4. 주요 URL 정리

| 용도 | URL |
|------|-----|
| 로그인 | http://localhost:8000/static/login.html |
| 회원가입 | http://localhost:8000/static/signup.html |
| 컨테이너 관리(Admin) | http://localhost:8000/static/admin.html |
| 행동 분석 대시보드 | http://localhost:8000/static/dashboard.html |
| 계정 관리(관리자 전용) | http://localhost:8000/static/accounts.html |
| Kafka UI(토픽/메시지 확인) | http://localhost:18080 |
| 설정 API(SDK용) | http://localhost:8000/settings/latest |
| 수집 API(SDK용) | http://localhost:8000/collect |

---

5. 웹/앱에 트래커 붙이기

1. 수집을 원하는 웹 페이지에 (https://ecommerce-dev.hectoinnovation.co.kr/main/home) 들어가서 개발자 모드 콘솔에 ./ntm.js 코드를 복붙 및 실행 
3. 배포된 설정이 자동으로 적용되며, 페이지뷰·클릭·스크롤·커스텀 이벤트 등이 수집되어 Kafka → DB로 적재되고, 대시보드에서 조회할 수 있습니다.

---

6. 문제 해결

- 로그인이 안 될 때: ID/비밀번호가 `admin` / `admin` 인지 확인하세요. 초기 계정은 Docker 기동 시 자동 생성됩니다.
- 대시보드에 데이터가 안 보일 때: 트래커가 붙은 페이지에서 이벤트가 발생했는지, Kafka·컨슈머가 정상 기동 중인지 확인하세요. Kafka UI(http://localhost:18080)에서 토픽 `test` 메시지 유무를 볼 수 있습니다.
- 컨테이너 관리/계정 관리가 안 보일 때: 해당 메뉴는 관리자(admin) 계정으로만 접근 가능합니다. 일반 사용자로 로그인했다면 관리자 계정으로 다시 로그인하세요.

---

