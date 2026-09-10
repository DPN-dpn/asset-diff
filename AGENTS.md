# Asset-Diff — 프로그램 기능 및 로직 문서

## 개요

**Asset-Diff**는 3DMIGOTO 기반 게임 모드(Mod)의 에셋(Asset)을 버전 간 비교(diff)하여,
구버전 모드가 신버전 게임에서도 동작하도록 자동 업데이트 스크립트를 생성해주는 GUI 도구입니다.

- **언어**: Python 3
- **GUI 프레임워크**: Tkinter
- **실행**: `python app.py` 또는 `run.bat`

---

## 디렉토리 구조

```
asset-diff/
├── app.py                  # 엔트리 포인트, AppContext 초기화
├── run.bat                 # 실행 배치 파일
├── backend/
│   ├── extractor.py        # 핵심 diff 추출 로직 (LAYOUT_CHANGES 포함)
│   ├── scanner.py          # 에셋 폴더 스캐너
│   ├── script_generator.py # 픽스툴(auto_update_mod.py) 코드 생성기 (자동 버퍼 변환 탑재)
│   └── logger.py           # 로거 (콜백 기반)
├── frontend/
│   ├── main_window.py      # 메인 윈도우 (툴바 + 페이지 컨테이너)
│   └── pages.py            # DiffPage, ScriptPage UI 페이지
├── old asset/              # 구버전 에셋 폴더 (사용자가 파일 배치)
├── new asset/              # 신버전 에셋 폴더 (사용자가 파일 배치)
└── output/                 # 결과물 저장 폴더 (diff.json, auto_update_mod.py)
```

---

## 핵심 개념

| 용어 | 설명 |
|------|------|
| **에셋(Asset)** | `hash.json`이 존재하는 폴더 단위의 모드 컴포넌트 |
| **hash.json** | 각 에셋의 버퍼 해시, 인덱스, 텍스처 정보를 담은 메타데이터 파일 |
| **vb0 텍스트 파일** | 버텍스 버퍼 덤프 파일. `POSITION`, `BLENDINDICES`, `BLENDWEIGHTS` 데이터 포함 |
| **픽스툴** | 생성된 `auto_update_mod.py` 스크립트. 사용자가 모드 폴더에서 직접 실행하는 자동화 도구 |

---

## 주요 기능

### 1. Diff 추출 (`DiffPage`)

구버전/신버전 에셋 폴더를 짝지어 변경사항을 JSON으로 추출합니다.

**동작 순서:**
1. **에셋 검색** — `old asset/`, `new asset/` 하위를 재귀 탐색하여 `hash.json`이 있는 폴더 목록을 수집
2. **짝 구성** — 드롭다운(Combobox)으로 Old/New 에셋을 N:N으로 매핑
3. **Diff 추출 실행** — 각 짝에 대해 `extract_hash_diff()` 호출 → `output/diff.json`에 저장
4. 저장 완료 후 `output/` 폴더를 탐색기로 자동 오픈

---

### 2. 픽스툴 작성 (`ScriptPage`)

추출된 diff 데이터를 기반으로 모드 자동 업데이트 Python 스크립트를 생성합니다.

**동작 순서:**
1. **데이터 불러오기** (3가지 방법 중 선택)
   - `output 불러오기` — `output/diff.json` 자동 로드
   - `파일 불러오기` — 파일 다이얼로그로 임의 JSON 선택
   - `텍스트로 추가` — 팝업에 JSON 텍스트 직접 붙여넣기
2. **항목 선택** — Treeview에서 스크립트에 포함할 에셋 diff를 클릭으로 체크/언체크
3. **픽스툴 작성** — 선택된 항목으로 `generate_script()` 호출 → `output/auto_update_mod.py` 저장

---

## 백엔드 로직 상세

### `scanner.py` — 에셋 탐색

```python
scan_assets(base_dir) -> List[str]
```
- `os.walk()`로 `base_dir` 하위를 재귀 탐색
- `hash.json`이 존재하는 폴더의 **상대 경로** 리스트 반환

---

### `extractor.py` — Diff 추출

```python
extract_hash_diff(old_dir, new_dir) -> dict
```

반환 딕셔너리 구조:

```json
{
  "HASH_MAPPING":         {},
  "INDEX_CHANGES":        {},
  "VERTEX_GROUP_MAPPING": {},
  "STRIDE_CHANGES":       {},
  "LAYOUT_CHANGES":       {},
  "WARNINGS":             []
}
```

#### Step 1. 해시 매핑 (HASH_MAPPING)
- 동일 `component_name`의 `draw_vb`, `position_vb`, `blend_vb`, `texcoord_vb`, `ib` 버퍼 해시 비교
- 텍스처 해시(`texture_hashes`) 배열도 순서 기반으로 비교
- 구해시 ≠ 신해시이면 `HASH_MAPPING[구해시] = 신해시` 기록

#### Step 2. 인덱스 변경 (INDEX_CHANGES)
- `object_indexes`(first_index)와 `object_index_counts`(index_count) 비교
- 변경된 섹션을 `{comp_name: {section: {match_first_index, match_index_count}}}` 형태로 기록

#### Step 3. 버텍스 그룹 매핑 (VERTEX_GROUP_MAPPING)
- `*{comp_name}*-vb0=*.txt` 파일을 `parse_vb_txt()`로 파싱
- **위치(POSITION)** 기준으로 구버전/신버전 버텍스를 매칭
- 동일 위치의 버텍스에서 **가중치(BLENDWEIGHTS)가 유사**(오차 < 0.01)할 때, 뼈대 인덱스(BLENDINDICES) 변화를 빈도수로 집계
- 가장 빈도 높은 매핑 → `final_mapping = {구인덱스: 신인덱스}`

```python
parse_vb_txt(filepath) -> dict
# {(x, y, z, w): [{bone_idx: weight, ...}, ...]}
# POSITION 좌표(소수점 4자리 반올림)를 키로 사용
```

---

### `script_generator.py` — 픽스툴 코드 생성

```python
generate_script(diff_data, output_path)
```

`SCRIPT_TEMPLATE`에 `diff_data`를 JSON으로 삽입하여 독립 실행 가능한 Python 스크립트 생성.

**생성된 스크립트(`auto_update_mod.py`)의 동작:**

| 단계 | 처리 내용 |
|------|----------|
| 1. 해시 글로벌 치환 | `.ini` 파일 전체에서 `HASH_MAPPING`의 구해시를 정규식으로 신해시로 치환 |
| 2. 인덱스 치환 | `INDEX_CHANGES`의 new_ib_hash를 가진 섹션을 찾아 `match_first_index`, `match_index_count` 값 교체 |
| 3. Blend 버퍼 수정 | `VERTEX_GROUP_MAPPING`의 new_blend_hash를 참조하는 `.buf` 파일을 바이너리로 열어 뼈대 인덱스를 직접 패치 |
| 4. 제네릭 버퍼 구조 변환 | `LAYOUT_CHANGES`를 기반으로 `POSITION`, `COLOR`, `TEXCOORD` 등의 요소(Semantic)별 포맷 변환(예: 8bit UNORM -> 32bit FLOAT)을 `struct`를 사용해 자동으로 바이트 단위 재조립 |
| 5. 백업 생성 | 수정 전 원본을 `.bak` 파일로 복사 (중복 방지) |
| 6. `.ini` 저장 | 갱신된 `stride` 값 등 수정된 내용을 다시 파일에 쓰기 |

---

### `logger.py` — 로거

```python
class Logger:
    add_callback(callback)  # UI 텍스트 출력 등 콜백 등록
    log(message)            # [HH:MM:SS] 타임스탬프 포맷 후 모든 콜백에 전파
```

- 백엔드 로직과 UI를 **콜백 패턴**으로 분리
- `MainWindow`에서 `write_log()` 콜백을 등록하여 하단 로그 패널에 실시간 출력

---

## UI 구조

```
MainWindow (900x700)
├── top_pane
│   ├── toolbar_frame (좌측 120px)
│   │   ├── [버튼] diff 추출   → DiffPage로 전환
│   │   └── [버튼] 픽스툴 작성 → ScriptPage로 전환
│   └── page_container (우측, grid 스택)
│       ├── DiffPage     (에셋 기반 Diff 추출)
│       ├── ModDiffPage  (현재 수동 매칭 기능으로 재설계 대기 중)
│       └── ScriptPage   (픽스툴 작성)
└── bottom_pane (height=150)
    └── log_text (Consolas, 다크 테마 로그 패널)
```

---

## 데이터 흐름

```
[old asset/] ─┐
              ├─► scan_assets() ─► Combobox 목록
[new asset/] ─┘

사용자가 Old/New 짝 구성
         │
         ▼
extract_hash_diff(old_path, new_path)
         │
         ▼
   diff.json (output/)
         │
         ▼
 ScriptPage에서 로드 & 항목 선택
         │
         ▼
generate_script(selected_diff_data)
         │
         ▼
 auto_update_mod.py (output/)
         │
         ▼
사용자가 모드 폴더에서 직접 실행 → .ini / .buf 자동 패치
```

---

## 확장 포인트 / 미구현 기능

- **모드 수동 매칭 (Mod Diff 개편)**: 자동으로 INI 섹션 이름을 파싱하던 불안정한 기존 기능을 폐기하고, 사용자가 수동으로 해시값을 짝지어 단일 `diff.json`을 내보내는 방향으로 UI 기획 중.
- `AppContext.old_dir` / `new_dir` 경로가 하드코딩(`"old asset"`, `"new asset"`)되어 있어, 향후 사용자 지정 경로 설정 기능 추가 가능.
