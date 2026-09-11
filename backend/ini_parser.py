import os
import re

def parse_ini_for_diff(ini_path):
    """
    모드 폴더의 .ini 파일을 파싱하여 [TextureOverride...] 및 [ShaderOverride...] 섹션들 중에서
    hash 값이 정의된 섹션 정보를 추출하고, [Resource...] 섹션의 설정도 파싱합니다.
    """
    result = {
        "overrides": {},
        "resources": {}
    }
    
    if not os.path.exists(ini_path):
        return result

    with open(ini_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 섹션 단위 분리
    sections_raw = re.split(r'(^\[.*?\])', content, flags=re.MULTILINE)
    
    all_sections_data = {}
    for i in range(1, len(sections_raw), 2):
        sec_name_raw = sections_raw[i].strip()
        sec_body = sections_raw[i+1] if i+1 < len(sections_raw) else ""
        sec_name = sec_name_raw.strip('[]')
        all_sections_data[sec_name] = sec_body

    # 1. Resource 파싱
    for sec_name, sec_body in all_sections_data.items():
        if sec_name.startswith("Resource"):
            res_info = {}
            stride_match = re.search(r'\bstride\s*=\s*([0-9]+)', sec_body)
            if stride_match:
                res_info["stride"] = int(stride_match.group(1))
            
            filename_match = re.search(r'\bfilename\s*=\s*([^\n\r]+)', sec_body)
            if filename_match:
                res_info["filename"] = filename_match.group(1).strip()
                
            if res_info:
                result["resources"][sec_name] = res_info

    # 2. Texture/Shader Override 순회
    for sec_name, sec_body in all_sections_data.items():
        if not (sec_name.startswith("TextureOverride") or sec_name.startswith("ShaderOverride")):
            continue
            
        hash_match = re.search(r'\bhash\s*=\s*([0-9a-fA-F]+)', sec_body)
        if hash_match:
            hash_val = hash_match.group(1)
            hints = []
            override_data = {
                "hash": hash_val,
                "hints": "",
                "match_first_index": None,
                "match_index_count": None,
                "vb0": None,
                "vb2": None,
                "ib": None
            }
            
            # 주요 필드 및 힌트 추출
            for key in ['vb0', 'vb1', 'vb2', 'ib', 'handling', 'draw', 'drawindexed', 'match_first_index', 'match_index_count']:
                val_match = re.search(rf'\b{key}\s*=\s*([^\n\r]+)', sec_body)
                if val_match:
                    val = val_match.group(1).strip()
                    hints.append(f"{key} = {val}")
                    
                    if key == "match_first_index":
                        override_data["match_first_index"] = int(val)
                    elif key == "match_index_count":
                        override_data["match_index_count"] = int(val)
                    elif key in ["vb0", "vb2", "ib"]:
                        override_data[key] = val
                    
            # run = CommandList... 추적
            run_matches = re.finditer(r'\brun\s*=\s*([^\n\r]+)', sec_body)
            for rm in run_matches:
                run_target = rm.group(1).strip()
                hints.append(f"run = {run_target}")
                if run_target in all_sections_data:
                    target_body = all_sections_data[run_target]
                    for sub_key in ['vb0', 'vb1', 'vb2', 'ib']:
                        sub_val_match = re.search(rf'\b{sub_key}\s*=\s*([^\n\r]+)', target_body)
                        if sub_val_match:
                            sub_val = sub_val_match.group(1).strip()
                            hints.append(f"  -> [{run_target}] {sub_key} = {sub_val}")
                            # 만약 메인 섹션에 없다면 서브 섹션 값을 기록
                            if sub_key in ["vb0", "vb2", "ib"] and not override_data[sub_key]:
                                override_data[sub_key] = sub_val
                                
            override_data["hints"] = "\n".join(hints)
            result["overrides"][sec_name] = override_data
            
    return result
