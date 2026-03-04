# GitHub 푸시 가이드 (net_thrue_01)

프로젝트를 GitHub에 올리기 위한 단계입니다. **PowerShell 또는 터미널**에서 프로젝트 루트(`net_thrue_01`)로 이동한 뒤 아래를 순서대로 실행하세요.

---

## 1. Git 저장소 초기화 (이미 되어 있으면 생략)

```bash
cd c:\Users\Owner\Desktop\docker-compose\pipe_line\net_thrue_01
git init
```

---

## 2. .gitignore 확인

프로젝트 루트에 `.gitignore`가 있어야 합니다.  
- 제외: `venv/`, `__pycache__/`, `.env`, `*.log` 등  
- `data/*.json`, `settings/latest.json`, `settings/versions/`는 **기본적으로 포함** (클론 후 바로 동작하도록).  
- 데이터가 비대하거나 비공개로 두고 싶으면 `.gitignore`에 해당 경로를 추가한 뒤 커밋하세요.

---

## 3. 첫 커밋

```bash
git add .
git status
```

`status`로 추가된 파일을 확인한 뒤:

```bash
git commit -m "Initial commit: net_thrue_01 behavior tracking service"
```

---

## 4. GitHub에서 새 저장소 만들기

1. [GitHub](https://github.com) 로그인 후 **New repository** 클릭  
2. **Repository name**: 예) `net_thrue_01`  
3. **Public** 선택 (또는 Private)  
4. **Create repository**만 누르고, README나 .gitignore 추가 옵션은 **선택하지 마세요** (이미 로컬에 있음)

---

## 5. 원격 저장소 연결 및 푸시

GitHub에서 저장소를 만든 뒤 나오는 주소를 사용합니다.  
**HTTPS** 예시:

```bash
git remote add origin https://github.com/YOUR_USERNAME/net_thrue_01.git
git branch -M main
git push -u origin main
```

**SSH**를 쓰는 경우:

```bash
git remote add origin git@github.com:YOUR_USERNAME/net_thrue_01.git
git branch -M main
git push -u origin main
```

`YOUR_USERNAME`을 본인 GitHub 사용자명으로 바꾸세요.  
최초 푸시 시 GitHub 로그인 또는 SSH 키 인증이 필요할 수 있습니다.

---

## 6. (선택) 이후 변경사항 푸시

```bash
git add .
git commit -m "설명 메시지"
git push
```

---

## 주의사항

- **비밀번호·API 키**가 코드나 설정 파일에 있으면 제거한 뒤 푸시하세요. `.env`는 `.gitignore`에 있으므로 추가되지 않습니다.
- **data/** 나 **settings/** 를 저장소에서 제외하려면 `.gitignore`에 해당 경로를 넣고, 이미 커밋된 파일이 있다면 `git rm --cached` 로 추적 해제 후 다시 커밋·푸시하세요.
