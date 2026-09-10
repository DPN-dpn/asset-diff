import os
import json
import re
import glob
from backend.extractor import load_hash_json, parse_vb_txt

def extract_mod_diff(old_mod_dir, new_asset_dir):
    """
    old mod의 ini/buf 파일들과 new asset의 hash.json/vb0.txt를 비교하여
    diff 딕셔너리를 반환합니다.
    """
    new_hash_file = os.path.join(new_asset_dir, "hash.json")
    if not os.path.exists(new_hash_file):
        raise FileNotFoundError("신버전 에셋에 hash.json이 없습니다.")
        
    new_json = load_hash_json(new_hash_file)
    new_dict = {comp["component_name"]: comp for comp in new_json}
    
    # 1. old mod의 .ini 파일 수집
    ini_files = []
    for root, dirs, files in os.walk(old_mod_dir):
        for file in files:
            if file.endswith('.ini') and not file.lower().startswith('disabled'):
                ini_files.append(os.path.join(root, file))
                
    old_mod_data = {}
    
    for ini_path in ini_files:
        try:
            with open(ini_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            sections = re.split(r'(^\[.*?\])', content, flags=re.MULTILINE)
            for i in range(1, len(sections), 2):
                sec_name = sections[i].strip('[]\r\n ')
                sec_body = sections[i+1]
                
                # INI 섹션 이름이 어떤 컴포넌트인지 식별
                matched_comp = None
                for comp_name in new_dict.keys():
                    if comp_name.lower() in sec_name.lower():
                        matched_comp = comp_name
                        break
                        
                if matched_comp:
                    if matched_comp not in old_mod_data:
                        old_mod_data[matched_comp] = {}
                        
                    match_hash = re.search(r'\bhash\s*=\s*([0-9a-fA-F]+)', sec_body)
                    if match_hash:
                        h = match_hash.group(1)
                        s_lower = sec_name.lower()
                        if 'blend' in s_lower:
                            old_mod_data[matched_comp]['blend_vb'] = h
                        elif 'texcoord' in s_lower:
                            old_mod_data[matched_comp]['texcoord_vb'] = h
                        elif 'vertexlimitraise' in s_lower:
                            old_mod_data[matched_comp]['draw_vb'] = h
                        elif 'position' in s_lower:
                            old_mod_data[matched_comp]['position_vb'] = h
                        elif 'ib' in s_lower and 'texcoord' not in s_lower and 'position' not in s_lower:
                            # match_first_index가 없는 섹션을 진짜 IB 해시 섹션으로 간주
                            if 'match_first_index' not in sec_body:
                                old_mod_data[matched_comp]['ib'] = h
                                
                        match_first_idx = re.search(r'\bmatch_first_index\s*=\s*(\d+)', sec_body)
                        if match_first_idx:
                            old_mod_data[matched_comp]['match_first_index'] = int(match_first_idx.group(1))

                if sec_name.startswith('Resource'):
                    for comp_name in new_dict.keys():
                        if comp_name.lower() in sec_name.lower():
                            match_filename = re.search(r'\bfilename\s*=\s*([^\n\r]+)', sec_body)
                            match_stride = re.search(r'\bstride\s*=\s*(\d+)', sec_body)
                            if match_filename:
                                filename = match_filename.group(1).strip()
                                abs_filename = os.path.normpath(os.path.join(os.path.dirname(ini_path), filename))
                                stride = int(match_stride.group(1)) if match_stride else None
                                
                                if 'blend' in sec_name.lower():
                                    old_mod_data[comp_name]['blend_buf'] = abs_filename
                                    old_mod_data[comp_name]['blend_stride'] = stride
                                elif 'position' in sec_name.lower():
                                    old_mod_data[comp_name]['position_buf'] = abs_filename
                                    old_mod_data[comp_name]['position_stride'] = stride
                                elif 'texcoord' in sec_name.lower():
                                    old_mod_data[comp_name]['texcoord_buf'] = abs_filename
                                    old_mod_data[comp_name]['texcoord_stride'] = stride
        except Exception:
            continue

    diff_result = {
        "HASH_MAPPING": {},
        "INDEX_CHANGES": {},
        "VERTEX_GROUP_MAPPING": {},
        "STRIDE_CHANGES": {},
        "WARNINGS": []
    }
    
    for comp_name, new_comp in new_dict.items():
        if comp_name not in old_mod_data:
            diff_result["WARNINGS"].append(f"'{comp_name}' 파츠를 옛 모드(.ini)에서 찾지 못했습니다.")
            continue
            
        old_comp = old_mod_data[comp_name]
        
        # 1. 버퍼 해시 매핑
        hash_keys = ["draw_vb", "position_vb", "blend_vb", "texcoord_vb", "ib"]
        for key in hash_keys:
            old_hash = old_comp.get(key)
            new_hash = new_comp.get(key)
            if old_hash and new_hash and old_hash != new_hash:
                diff_result["HASH_MAPPING"][old_hash] = new_hash
                
        # 2. 인덱스 맵핑
        old_idx = old_comp.get("match_first_index")
        new_indexes = new_comp.get("object_indexes", [])
        new_counts = new_comp.get("object_index_counts", [])
        
        if old_idx is not None and len(new_indexes) > 0:
            new_idx = new_indexes[0]
            new_cnt = new_counts[0] if len(new_counts) > 0 else 0
            
            if old_idx != new_idx: # count changes usually accompany index changes
                if comp_name not in diff_result["INDEX_CHANGES"]:
                    diff_result["INDEX_CHANGES"][comp_name] = {
                        "old_ib_hash": old_comp.get("ib"),
                        "new_ib_hash": new_comp.get("ib")
                    }
                
                # INI 기반 추출이므로 old count를 모를 수 있음. 없으면 생략 가능하게 됨 (위에서 처리)
                cls_name = new_comp.get("object_classifications", ["Section_0"])[0]
                diff_result["INDEX_CHANGES"][comp_name][cls_name] = {
                    "match_first_index": f"{old_idx} -> {new_idx}"
                }
                
        # 3. 버퍼 규격(Stride) 변화 감지
        pos_s = old_comp.get("position_stride", 0) or 0
        blend_s = old_comp.get("blend_stride", 0) or 0
        tex_s = old_comp.get("texcoord_stride", 0) or 0
        
        old_total_stride = pos_s + blend_s + tex_s
        
        if old_total_stride > 0:
            new_vb0_files = glob.glob(os.path.join(new_asset_dir, f"*{comp_name}*-vb0=*.txt"))
            if new_vb0_files:
                new_stride = None
                with open(new_vb0_files[0], 'r', encoding='utf-8') as f:
                    first_line = f.readline().strip()
                    if first_line.startswith("stride:"):
                        new_stride = int(first_line.split(":")[1].strip())
                        
                if new_stride is not None and old_total_stride != new_stride:
                    diff_result["STRIDE_CHANGES"][comp_name] = f"{old_total_stride} (합산) -> {new_stride}"

    return diff_result
