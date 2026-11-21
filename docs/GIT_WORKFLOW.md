# 두 사람이 함께 쓰는 Git 작업 방식

작성 2026-11-14, 저장소 옮김 반영 2026-11-16(11절). 이 저장소에 두 사람이 함께 고칠 때, 서로의 반영이 덮이거나 되돌려지지 않게 하는 규칙입니다. 확인하고 의견이 있으면 이 문서를 고치는 PR이나 댓글로 알려 주세요.

## 1. 한 줄 요약

`main`에는 직접 올리지 않습니다. 일 하나마다 브랜치를 만들고 PR(Pull Request)을 올린 뒤, **다른 사람이 확인하고 승인하면** 병합합니다. 단, 협업자 계정(워크플로의 `ALLOWED_AUTHORS`)이 올린 PR은 승인을 기다리지 않고 자동으로 병합됩니다(8절).

## 2. 왜 이렇게 하나

두 사람이 같은 `main`에 바로 올리면 다음 일이 생깁니다.
- 충돌을 풀면서 한쪽 내용을 통째로 고름
- 오래된 사본으로 덮어씀(강제 푸시)
- 그러다 다른 사람의 반영이 사라짐

브랜치와 PR로 나누면 다음이 지켜집니다.
- 병합 전에 바뀐 내용을 서로 볼 수 있음
- 충돌은 올리는 사람이 자기 브랜치에서 먼저 풂
- 문제가 생겨도 PR 하나만 되돌리면 됨

## 3. 저장소 설정 (관리자만 할 수 있음)

**Settings → Branches → Add branch ruleset**(또는 Branch protection rule)에서 대상 `main`에 다음을 켭니다.

| 설정 | 하는 일 |
|---|---|
| Require a pull request before merging | `main`에는 PR로만 반영 |
| Required approvals: 1 | 다른 한 사람이 승인해야 병합 |
| Require branches to be up to date before merging | 최신 `main`을 반영한 브랜치만 병합. 오래된 브랜치가 새 변경을 덮는 것을 막음 |
| Block force pushes | 강제 푸시 금지 |
| Restrict deletions | `main` 삭제 금지 |
| Bypass list 비우기 / Do not allow bypassing | **관리자도** 위 규칙을 지킴. 이것을 빼면 관리자는 계속 `main`에 바로 올릴 수 있음 |

`gh-pages`는 배포용이라 지금처럼 둡니다.

2026-11-16 새 저장소(`New-dss`)를 만든 때에도 위 설정은 켜져 있지 않습니다(`main` 보호 없음, 규칙 없음). 첫 내용을 올린 뒤 관리자가 켭니다. `Required approvals: 1`을 켜면 8절의 자동 병합은 멈춥니다(자동 병합은 승인을 대신하지 않습니다).

## 4. 작업 순서

```powershell
# 1) 최신 main에서 시작
git switch main
git pull --ff-only

# 2) 일 하나에 브랜치 하나
git switch -c fix/<무엇을-고치나>

# 3) 작업하고 커밋 (작게, 자주)
git add <파일>
git commit -m "무엇을 왜 바꿨는지"

# 4) 올리기 전에 최신 main을 내 브랜치로 가져와 충돌을 내 쪽에서 먼저 풂
git fetch origin
git merge origin/main        # 충돌이 나면 양쪽 내용을 다 보고 합침

# 5) 브랜치를 올리고 GitHub에서 PR 열기
git push -u origin fix/<무엇을-고치나>
```

1. PR 설명에는 무엇을 왜 바꿨는지, 시험을 돌렸는지, 숫자가 바뀌는지를 적습니다.
2. 다른 사람이 확인하고 승인합니다. 고칠 점은 PR 댓글로 남깁니다.
3. 병합은 **Squash and merge**로 합니다. PR 하나가 `main`의 커밋 하나가 되어 되돌리기 쉽습니다.
4. 병합 뒤 그 브랜치는 지웁니다(GitHub의 Delete branch 버튼).

## 5. 브랜치 이름

| 앞말 | 쓰임 | 예 |
|---|---|---|
| `fix/` | 오류 수정 | `fix/ladder-offsite-pv` |
| `feature/` | 새 기능·큰 작업 묶음 | `feature/interview-feedback` |
| `docs/` | 문서만 | `docs/manual-terms` |

## 6. 하지 않는 것

- `main`에 직접 커밋·푸시
- `git push --force`(꼭 필요하면 자기 브랜치에서만 `--force-with-lease`로, 함께 쓰는 브랜치는 금지)
- 충돌을 "내 것 모두"나 "상대 것 모두"로 한 번에 풀기
- 다른 사람의 브랜치에 말없이 커밋
- `data/`, `.env`, 키, DB 덤프 올리기(기존 규칙 그대로. `AGENTS.md`)

## 7. 충돌을 줄이는 약속

- 시작할 때 누가 어떤 파일을 맡을지 짧게 나눕니다. 이 저장소에서 둘이 같이 고치기 쉬운 곳은 화면(`frontend/src/pages`), `backend/cases/simulation_cases.json`, `docs/USER_MANUAL.md`입니다.
- PR은 작게 만들고, 오래 열어 두지 않습니다. 하루 이틀 안에 병합하는 것이 목표입니다.
- 단, 긴 수집을 돌리며 생기는 **운영 고침**(속도 · 재시도 · 감시 · 메모리처럼 결과 숫자 · 기준 · 화면이 안 바뀌는 것)은 고칠 때마다 PR을 열지 않습니다. 브랜치 하나(예: `collect/national-run`)에 커밋을 모으고 GitHub에는 브랜치만 올려 둔 뒤, 단계가 끝날 때 PR 하나 · 기록 하나로 합칩니다(2026-11-21, 이틀 동안 PR 45개 · 기록 44개가 쌓여 정함). 워커는 로컬 폴더에서 빌드되므로 합치기 전에도 돌아갑니다. 결과 숫자 · 기준 · 화면이 바뀌는 것은 지금처럼 그때그때 PR로 엽니다. 기록만 바꾼 것은 따로 PR을 열지 않고 다음 코드 PR에 같이 넣습니다.
- 계수·상수를 바꾸는 PR은 기준 문서(`docs/DATA_STANDARD.md`)와 코드를 같은 PR에서 바꿉니다(기존 규칙).

## 8. 자동 병합 (협업자 계정이 올린 PR)

저장소 관리자(shy0401)의 결정으로, 2026-11-14부터 협업자 계정(`ALLOWED_AUTHORS`)이 이 저장소의 브랜치에서 `main`으로 여는 PR은 **승인을 기다리지 않고 자동으로 병합**됩니다. `.github/workflows/auto-merge-collaborator.yml`이 PR이 열리거나 커밋이 더해질 때와 시험이 끝날 때마다 돌아, 시험이 통과하면 Squash and merge 하고 그 브랜치를 지운 뒤 PR에 댓글을 남깁니다. 그래서 1절·4절의 "다른 사람이 승인" 단계는 협업자 계정의 PR에는 적용되지 않습니다.

자동으로 병합하지 않고 남겨 두는 경우(이유를 PR 댓글로 남깁니다):

| 경우 | 다음에 할 일 |
|---|---|
| `main`과 충돌이 있음 | 4절 4)대로 `git merge origin/main`으로 풀고 같은 브랜치에 푸시하면 다시 시도 |
| 초안(Draft) PR | Ready for review로 바꾸면 병합. 병합을 미루고 싶은 변경은 초안으로 엽니다 |
| `.github/` 아래를 바꿈(이 규칙 자체 포함) | 관리자가 직접 확인하고 병합 |
| 올리지 않기로 한 경로가 들어 있음(`.env`, `.secrets/`, `data/raw`·`data/backups`·`data/cache` 등, 키·덤프 파일) | 그 파일을 PR에서 빼고 다시 푸시 |
| 한 PR이 파일을 20개 넘게 지우거나 3,000줄 넘게 지움 | 관리자가 내용을 보고 직접 병합(잘못 푼 충돌로 다른 사람의 반영이 사라지는 것을 막기 위함) |
| 다른 저장소(fork)에서 온 PR | 이 저장소의 브랜치로 올림 |
| 더한 줄이나 파일 이름에 보낸 사람 이름으로 보이는 것이 있음(10절) | 출처를 팀 데이터셋 이름·받은 날짜로 고쳐 다시 푸시. 이름이 아니면 그 줄에 `privacy: ok` |
| 시험(백엔드 시험 · 화면 시험 · 저장소 파일 점검)이 통과하지 않음 | PR의 Checks 탭에서 로그를 보고 고쳐 같은 브랜치에 푸시. 시험이 아직 돌고 있으면 댓글 없이 기다렸다가 끝나면 다시 확인 |

알아 둘 것:
- 2026-11-19부터 GitHub에서 PR마다 시험이 돕니다(`.github/workflows/tests.yml`): 백엔드 `pytest`(DB · `data/` 없이, 그런 자료가 필요한 시험은 건너뜀)와 화면 `npm run build` · `npm test`. 자동 병합은 그 커밋에서 세 점검이 모두 통과해야 합니다. DB까지 쓰는 시험은 여전히 PC의 컨테이너에서 돌리고 결과를 PR 설명에 적습니다.
- 병합 전에 꼭 같이 봐야 하는 변경(계수·상수, 발표 숫자가 바뀌는 변경)은 초안으로 열고 댓글로 알려 주세요.
- 대상 사용자와 기준 값은 워크플로 파일 위쪽의 `ALLOWED_AUTHORS`, `MAX_REMOVED_FILES`, `MAX_DELETED_LINES`에 있습니다.
- 멈추려면 GitHub의 Actions → "협업자 PR 자동 병합" → Disable workflow.

## 9. 지금 진행 중인 브랜치

새 저장소(`New-dss`)는 2026-11-16 첫 내용만 있고 열린 브랜치·PR이 없습니다. 이전 저장소의 브랜치·PR(`feature/interview-feedback`, `fix/feedback-audit` 등) 번호와 기록은 이전 저장소에 남아 있습니다(11절).

## 10. 보낸 사람 이름을 남기지 않기

팀원이 보낸 자료를 붙일 때 출처·폴더 이름·기록에 사람 이름을 적지 않습니다(`AGENTS.md`). 출처는 "팀 데이터셋 urban-carbon, 2026-10-20 인계"처럼 자료 이름과 받은 날짜로 씁니다.

- **가져오기 코드**: 팀 격자(`import-team-grid`)·선도소프트 100m·파일 업로드가 DB에 적는 경로·파일 이름에서 이름을 뺍니다(`backend/app/privacy.py`). 날짜나 "수집" 뒤에 붙인 이름(`…_2026-10-01_<이름>`, `데이터수집_<이름>`)은 목록 없이도 빠집니다. 시·군·구·동…으로 끝나는 이름과 다른 자리에 쓴 이름은 목록에 적어야 빠집니다. 팀 표의 칸(개발 사례·점수 줄)은 목록의 이름이 한 낱말로 든 칸만 "팀원"으로 바꿉니다(이름과 같은 글자가 든 건물 이름 '○○교회' 같은 것은 그대로). 다른 PC 묶음 합치기(`MergeBundle`)는 관측 표라 값을 바꾸지 않고 이름이 든 행 수만 보고서(`names_seen`)에 적습니다.
- **이름 목록**: 저장소에 두지 않습니다(목록이 곧 기록이므로). PC마다 `data/ops/private_names.txt`(한 줄에 하나) 또는 `.env`의 `PRIVATE_NAMES`(쉼표)에 적습니다. GitHub에서는 저장소 Settings → Secrets and variables → Actions → `PRIVATE_NAMES`.
- **점검**: 올리기 전 `python backend/app/privacy.py check`(저장소 파일. 발표자료·문서 파일(pptx·docx·xlsx)은 슬라이드·발표자 노트·본문 글자까지, PDF는 보지 않음), DB는 `docker compose -p carbon-urban-dss -f compose.yaml -f compose.demo.yaml exec -T api python -m app.privacy check --db`. GitHub에서는 "보낸 사람 이름 점검"이 푸시·PR마다, 자동 병합이 PR의 더한 줄마다 봅니다. 걸린 곳은 파일·줄만 찍고 이름은 찍지 않습니다.
- **이미 들어간 기록**: `python -m app.privacy scrub-db`(세기만) → `--apply`(경로 열은 이름 자리를 빼고, 다른 글자·JSON은 한 낱말로 쓰인 이름만 "팀원"으로). 원본 파일 자리(`storage_location`)와 다른 낱말 안의 같은 글자는 바꾸지 않고 셉니다. 먼저 `scripts\dss.cmd Backup`.
- Git 기록(지난 커밋)에 남은 이름은 지우지 않습니다(기록 다시 쓰기·강제 푸시 금지). 새 저장소(`New-dss`)는 이름이 없는 지금 파일로 기록을 새로 시작했습니다(11절).

## 11. 저장소 옮김 (2026-11-16)

이 저장소의 주소는 **https://github.com/shy0401/New-dss** 입니다. 이전 저장소(`shy0401/Carbon-Urban-DSS`)의 2026-11-16 `main` 파일을 그대로 옮기되, 기록은 새로 시작했습니다.

| 옮길 때 | 내용 |
|---|---|
| 기록 | 이전 커밋을 가져오지 않음. 지난 커밋 일부에 보낸 사람 이름이 남아 있어(10절), 이름이 없는 지금 파일로 처음부터 커밋 |
| 뺀 파일 | 이전 저장소에 올라가 있던 `data/`(실행 증거 화면·JSON·시험 기록, 요약 스냅숏), `.idea/`(개인 설정), `tmp/`·`output/`(문서 만들 때 생긴 임시·산출 파일), 겹치는 `gitignore` 파일. 모두 "올리지 않는 것"(`AGENTS.md`)이라 `.gitignore`에 더함. PC 폴더의 파일은 그대로 있음 |
| 첫 커밋 | 빈 저장소라 첫 내용만 `main`으로 바로 올림(강제 푸시 없음). 그다음부터는 4절처럼 브랜치·PR |
| 고친 주소 | 받는 명령(`git clone`)·문서 링크·자료 안내 링크를 새 주소로. 폴더 이름은 `Carbon-Urban-DSS` 그대로 받음(명령·바로가기가 그 이름을 씀) |
| 그대로 둔 것 | 시연 안내 주소 `https://shy0401.github.io/Carbon-Urban-DSS/`와 그 `gh-pages` 브랜치는 이전 저장소에 있음([배포](DEPLOYMENT.md#github-pages-고정-안내-주소)). 2026-09-23 기록 문서 속 이전 주소도 그때 기록이라 그대로 |

관리자가 새 저장소에서 할 일: 3절의 `main` 보호, 협업자 초대, Actions 비밀값 `PRIVATE_NAMES`(10절), Actions 켜짐 확인.

PC 작업 폴더를 새 저장소로 바꿀 때: 기록이 서로 이어지지 않으므로 `git pull`로는 넘어가지 않습니다. 다른 폴더에 새로 받아(`git clone https://github.com/shy0401/New-dss.git <새 폴더>`) `.env`와 `data/`를 옮기거나, 지금 폴더에서 `origin`을 바꾼 뒤 `git fetch origin`, `git switch -c main-new`, `git reset origin/main`(파일은 건드리지 않고 가리키는 커밋만 바꿈)으로 넘어간 뒤, 올리지 않은 고침이 없는지 `git status`로 보고 `git restore .`로 새 저장소의 파일을 받습니다. 이전 저장소에만 있던 `data/`·`.idea/` 파일은 지워지지 않고 올리지 않는 파일로 남습니다. 지금 폴더의 `origin`을 바꾸면 시연 지킴이(`scripts/demo-watch.ps1`)가 `demo.json`을 새 저장소의 `gh-pages`로 올리므로, 그 전에 새 저장소의 Pages를 켜고 안내 주소(`scripts/dss-power.ps1`의 `$PagesUrl`, 문서)를 함께 바꿉니다.
