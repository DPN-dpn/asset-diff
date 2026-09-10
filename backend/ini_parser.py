import os
import re

def parse_ini_for_diff(ini_path):
    """
    모드 폴더의 .ini 파일을 파싱하여 [TextureOverride...] 및 [ShaderOverride...] 섹션들 중에서
    hash 값이 정의된 섹션 정보를 추출합니다.
    """
    if not os.path.exists(ini_path):
        return {}

    with open(ini_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 섹션 단위 분리
    sections_raw = re.split(r'(^\[.*?\])', content, flags=re.MULTILINE)
    
    parsed_sections = {}
    current_section = None
    
    # 1. 모든 섹션 정보 1차 파싱
    all_sections_data = {}
    for i in range(1, len(sections_raw), 2):
        sec_name_raw = sections_raw[i].strip()
        sec_body = sections_raw[i+1] if i+1 < len(sections_raw) else ""
        sec_name = sec_name_raw.strip('[]')
        all_sections_data[sec_name] = sec_body

    # 2. Texture/Shader Override 순회
    for sec_name, sec_body in all_sections_data.items():
        if not (sec_name.startswith("TextureOverride") or sec_name.startswith("ShaderOverride")):
            continue
            
        hash_match = re.search(r'\bhash\s*=\s*([0-9a-fA-F]+)', sec_body)
        if hash_match:
            hash_val = hash_match.group(1)
            
            hints = []
            
            # 주요 힌트 추출
            for key in ['vb0', 'vb1', 'vb2', 'ib', 'handling', 'draw', 'drawindexed', 'match_first_index', 'match_index_count']:
                val_match = re.search(rf'\b{key}\s*=\s*([^\n\r]+)', sec_body)
                if val_match:
                    hints.append(f"{key} = {val_match.group(1).strip()}")
                    
            # run = CommandList... 추적
            run_matches = re.finditer(r'\brun\s*=\s*([^\n\r]+)', sec_body)
            for rm in run_matches:
                run_target = rm.group(1).strip()
                hints.append(f"run = {run_target}")
                # CommandList가 현재 파일 내에 있다면 내용 일부 힌트로 추가
                if run_target in all_sections_data:
                    target_body = all_sections_data[run_target]
                    for sub_key in ['vb0', 'vb1', 'vb2', 'ib']:
                        sub_val_match = re.search(rf'\b{sub_key}\s*=\s*([^\n\r]+)', target_body)
                        if sub_val_match:
                            hints.append(f"  -> [{run_target}] {sub_key} = {sub_val_match.group(1).strip()}")

            parsed_sections[sec_name] = {
                "hash": hash_val,
                "hints": "\n".join(hints)
            }
            
    return parsed_sections
