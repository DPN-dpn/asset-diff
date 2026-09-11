import os
import json
import glob
import re

FORMAT_INFO = {
    "R32G32B32A32_FLOAT": {"size": 16, "struct": "4f", "type": "float"},
    "R32G32B32_FLOAT": {"size": 12, "struct": "3f", "type": "float"},
    "R32G32_FLOAT": {"size": 8, "struct": "2f", "type": "float"},
    "R32_FLOAT": {"size": 4, "struct": "1f", "type": "float"},
    "R32_UINT": {"size": 4, "struct": "1I", "type": "uint"},
    "R32G32B32A32_UINT": {"size": 16, "struct": "4I", "type": "uint"},
    "R8G8B8A8_UNORM": {"size": 4, "struct": "4B", "type": "unorm"},
    "R16G16_FLOAT": {"size": 4, "struct": "2e", "type": "float"},
    "R16G16B16A16_FLOAT": {"size": 8, "struct": "4e", "type": "float"}
}

def parse_vb_layout(filepath):
    """
    vb0.txt 파일의 상단을 읽어 정점의 레이아웃(시맨틱)을 분석합니다.
    """
    elements = []
    if not os.path.exists(filepath):
        return elements
        
    with open(filepath, 'r', encoding='utf-8') as f:
        current_elem = {}
        for line in f:
            line = line.strip()
            if line.startswith('vb0['): break
            
            if line.startswith('element['):
                if current_elem:
                    elements.append(current_elem)
                current_elem = {}
            elif ':' in line and current_elem is not None:
                parts = line.split(':', 1)
                key = parts[0].strip()
                val = parts[1].strip()
                if key == 'SemanticName':
                    current_elem['semantic'] = val
                elif key == 'SemanticIndex':
                    current_elem['index'] = int(val)
                elif key == 'Format':
                    current_elem['format'] = val
                    if val in FORMAT_INFO:
                        current_elem['size'] = FORMAT_INFO[val]['size']
                elif key == 'AlignedByteOffset':
                    current_elem['offset'] = int(val)
                    
        if current_elem:
            elements.append(current_elem)
            
    return elements

def get_layout_diff(old_layout, new_layout, old_hash_str, new_hash_str, old_stride, new_stride):
    layout_diff = {
        "old_hash": old_hash_str,
        "new_hash": new_hash_str,
        "old_stride": old_stride,
        "new_stride": new_stride,
        "changes": [],
        "added": [],
        "removed": []
    }
    
    old_dict_layout = {f"{elem['semantic']}_{elem.get('index', 0)}": elem for elem in old_layout}
    new_dict_layout = {f"{elem['semantic']}_{elem.get('index', 0)}": elem for elem in new_layout}
    
    for key, old_e in old_dict_layout.items():
        if key in new_dict_layout:
            new_e = new_dict_layout[key]
            if old_e.get('format') != new_e.get('format'):
                layout_diff['changes'].append({
                    "semantic": old_e.get('semantic'),
                    "index": old_e.get('index', 0),
                    "old_format": old_e.get('format'),
                    "new_format": new_e.get('format'),
                    "old_offset": old_e.get('offset'),
                    "new_offset": new_e.get('offset'),
                    "old_size": old_e.get('size'),
                    "new_size": new_e.get('size'),
                    "old_type": FORMAT_INFO.get(old_e.get('format'), {}).get('type'),
                    "new_type": FORMAT_INFO.get(new_e.get('format'), {}).get('type'),
                    "old_struct": FORMAT_INFO.get(old_e.get('format'), {}).get('struct'),
                    "new_struct": FORMAT_INFO.get(new_e.get('format'), {}).get('struct')
                })
        else:
            layout_diff['removed'].append(old_e)
            
    for key, new_e in new_dict_layout.items():
        if key not in old_dict_layout:
            layout_diff['added'].append(new_e)
            
    if layout_diff['changes'] or layout_diff['added'] or layout_diff['removed']:
        return layout_diff
    return None

def load_hash_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def parse_vb_txt(filepath):
    """
    vb0 텍스트 덤프 파일을 파싱하여 POSITION 값을 기준으로 {index: weight} 맵을 반환합니다.
    (소수점 4자리 반올림으로 오차 보정)
    """
    vertex_map = {}
    if not os.path.exists(filepath):
        return vertex_map
        
    vertices = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('vb0['):
                parts = line.split(':', 1)
                if len(parts) < 2:
                    continue
                header_part = parts[0]
                values_str = parts[1].strip()
                
                try:
                    v_idx = header_part.split('[')[1].split(']')[0]
                except IndexError:
                    continue
                    
                if v_idx not in vertices:
                    vertices[v_idx] = {}
                    
                if 'POSITION' in header_part:
                    try:
                        coords = [round(float(x.strip()), 4) for x in values_str.split(',')]
                        vertices[v_idx]['pos'] = tuple(coords)
                    except ValueError:
                        pass
                elif 'BLENDINDICES' in header_part:
                    try:
                        vertices[v_idx]['indices'] = [int(x.strip()) for x in values_str.split(',')]
                    except ValueError:
                        pass
                elif 'BLENDWEIGHTS' in header_part:
                    try:
                        vertices[v_idx]['weights'] = [float(x.strip()) for x in values_str.split(',')]
                    except ValueError:
                        pass

    for v in vertices.values():
        pos = v.get('pos')
        indices = v.get('indices')
        weights = v.get('weights')
        
        if pos and indices and weights:
            iw_map = {}
            for i, w in zip(indices, weights):
                if w > 0.0001:
                    iw_map[i] = iw_map.get(i, 0.0) + w
                    
            if not iw_map:
                # 가중치가 모두 0이라도 인덱스는 기록
                for i in indices:
                    iw_map[i] = 1.0
                    
            if pos not in vertex_map:
                vertex_map[pos] = []
            vertex_map[pos].append(iw_map)
                    
    return vertex_map

def extract_hash_diff(old_dir, new_dir):
    """
    특정 old_dir와 new_dir를 입력받아 두 에셋의 변경사항을 추출하여 딕셔너리로 반환합니다.
    """
    old_hash_file = os.path.join(old_dir, "hash.json")
    new_hash_file = os.path.join(new_dir, "hash.json")
    
    if not os.path.exists(old_hash_file) or not os.path.exists(new_hash_file):
        raise FileNotFoundError(f"hash.json 파일이 누락되었습니다.")
        
    old_json = load_hash_json(old_hash_file)
    new_json = load_hash_json(new_hash_file)

    diff_result = {
        "HASH_MAPPING": {},
        "INDEX_CHANGES": {},
        "VERTEX_GROUP_MAPPING": {},
        "STRIDE_CHANGES": {},
        "LAYOUT_CHANGES": {},
        "WARNINGS": []
    }

    old_dict = {comp["component_name"]: comp for comp in old_json}
    new_dict = {comp["component_name"]: comp for comp in new_json}

    for comp_name, old_comp in old_dict.items():
        if comp_name not in new_dict:
            diff_result["WARNINGS"].append(f"구버전의 '{comp_name}' 파츠가 신버전에는 없습니다.")
            continue
        
        new_comp = new_dict[comp_name]
        
        # 1. 주요 버퍼 해시 비교
        hash_keys = ["draw_vb", "position_vb", "blend_vb", "texcoord_vb", "ib"]
        for key in hash_keys:
            old_hash = old_comp.get(key)
            new_hash = new_comp.get(key)
            if old_hash and new_hash and old_hash != new_hash:
                diff_result["HASH_MAPPING"][old_hash] = new_hash
                
        # 2. 인덱스 및 카운트 변화 비교
        old_indexes = old_comp.get("object_indexes", [])
        new_indexes = new_comp.get("object_indexes", [])
        old_counts = old_comp.get("object_index_counts", [])
        new_counts = new_comp.get("object_index_counts", [])
        classes = old_comp.get("object_classifications", [])
        
        for i in range(min(len(old_indexes), len(new_indexes))):
            cls_name = classes[i] if i < len(classes) else f"Section_{i}"
            
            old_idx = old_indexes[i]
            new_idx = new_indexes[i]
            old_cnt = old_counts[i] if i < len(old_counts) else 0
            new_cnt = new_counts[i] if i < len(new_counts) else 0
            
            if old_idx != new_idx or old_cnt != new_cnt:
                if comp_name not in diff_result["INDEX_CHANGES"]:
                    diff_result["INDEX_CHANGES"][comp_name] = {
                        "old_ib_hash": old_comp.get("ib"),
                        "new_ib_hash": new_comp.get("ib")
                    }
                diff_result["INDEX_CHANGES"][comp_name][cls_name] = {
                    "match_first_index": f"{old_idx} -> {new_idx}",
                    "match_index_count": f"{old_cnt} -> {new_cnt}"
                }

        # 3. 버텍스 그룹 (뼈대 인덱스) 밀림 추적
        old_vb0_files = glob.glob(os.path.join(old_dir, f"*{comp_name}*-vb0=*.txt"))
        new_vb0_files = glob.glob(os.path.join(new_dir, f"*{comp_name}*-vb0=*.txt"))
        
        if old_vb0_files and new_vb0_files:
            # Stride 변화 감지
            import re
            old_stride = None
            new_stride = None
            
            with open(old_vb0_files[0], 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                if first_line.startswith("stride:"):
                    old_stride = int(first_line.split(":")[1].strip())
                    
            with open(new_vb0_files[0], 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                if first_line.startswith("stride:"):
                    new_stride = int(first_line.split(":")[1].strip())
                    
            if old_stride is not None and new_stride is not None and old_stride != new_stride:
                diff_result["STRIDE_CHANGES"][comp_name] = f"{old_stride} -> {new_stride}"
                
                # Layout 변화 상세 감지
                old_layout = parse_vb_layout(old_vb0_files[0])
                new_layout = parse_vb_layout(new_vb0_files[0])
                
                old_hash_str = old_vb0_files[0].split('=')[-1].split('.')[0] if '=' in old_vb0_files[0] else ""
                new_hash_str = new_vb0_files[0].split('=')[-1].split('.')[0] if '=' in new_vb0_files[0] else ""
                
                layout_diff = get_layout_diff(old_layout, new_layout, old_hash_str, new_hash_str, old_stride, new_stride)
                if layout_diff:
                    diff_result["LAYOUT_CHANGES"][comp_name] = layout_diff
                
                
            mapping_freq = {}
            for old_f in old_vb0_files:
                section_name = os.path.basename(old_f).split('-vb0')[0]
                matching_new_files = [nf for nf in new_vb0_files if section_name in nf]
                if not matching_new_files:
                    matching_new_files = [new_vb0_files[0]]
                
                new_f = matching_new_files[0]
                
                old_map = parse_vb_txt(old_f)
                new_map = parse_vb_txt(new_f)
                
                for pos, old_iw_list in old_map.items():
                    if pos in new_map:
                        new_iw_list = new_map[pos]
                        
                        for old_iw, new_iw in zip(old_iw_list, new_iw_list):
                            old_sorted = sorted([(w, i) for i, w in old_iw.items()], reverse=True)
                            new_sorted = sorted([(w, i) for i, w in new_iw.items()], reverse=True)
                            
                            if len(old_sorted) == len(new_sorted):
                                weights_match = all(abs(o[0] - n[0]) < 0.01 for o, n in zip(old_sorted, new_sorted))
                                if weights_match:
                                    for o_item, n_item in zip(old_sorted, new_sorted):
                                        o_idx = o_item[1]
                                        n_idx = n_item[1]
                                        pair = (o_idx, n_idx)
                                        mapping_freq[pair] = mapping_freq.get(pair, 0) + 1

            if mapping_freq:
                final_mapping = {}
                from collections import defaultdict
                grouped = defaultdict(list)
                for (o_idx, n_idx), freq in mapping_freq.items():
                    grouped[o_idx].append((freq, n_idx))
                
                for o_idx, candidates in grouped.items():
                    candidates.sort(reverse=True)
                    best_n_idx = candidates[0][1]
                    if str(o_idx) != str(best_n_idx):
                        final_mapping[str(o_idx)] = best_n_idx

                if final_mapping:
                    diff_result["VERTEX_GROUP_MAPPING"][comp_name] = {
                        "old_blend_hash": old_comp.get("blend_vb"),
                        "new_blend_hash": new_comp.get("blend_vb"),
                        "mapping": final_mapping
                    }

    # 텍스처 해시 비교
    for comp_name, old_comp in old_dict.items():
        if comp_name not in new_dict:
            continue
        new_comp = new_dict[comp_name]
        
        old_textures = old_comp.get("texture_hashes", [])
        new_textures = new_comp.get("texture_hashes", [])
        
        for i in range(min(len(old_textures), len(new_textures))):
            old_tex_list = old_textures[i]
            new_tex_list = new_textures[i]
            
            for j in range(min(len(old_tex_list), len(new_tex_list))):
                if len(old_tex_list[j]) >= 3 and len(new_tex_list[j]) >= 3:
                    o_hash = old_tex_list[j][2]
                    n_hash = new_tex_list[j][2]
                    if o_hash and n_hash and o_hash != n_hash:
                        diff_result["HASH_MAPPING"][o_hash] = n_hash

    return diff_result

def extract_mod_diff(mod_dir, asset_dir, user_mapping):
    """
    사용자의 수동 매핑(user_mapping) 데이터를 기반으로
    모드 디렉토리(Old Mod)와 에셋 디렉토리(New Asset) 간의 해시 매핑(Mod Diff)을 생성합니다.
    user_mapping 구조: { "section_name": "component_name" }
    """
    from .ini_parser import parse_ini_for_diff
    
    diff_result = {
        "HASH_MAPPING": {},
        "INDEX_CHANGES": {},
        "VERTEX_GROUP_MAPPING": {},
        "STRIDE_CHANGES": {},
        "LAYOUT_CHANGES": {},
        "WARNINGS": []
    }
    
    ini_files = []
    for root, _, files in os.walk(mod_dir):
        for f in files:
            if f.lower().endswith(".ini"):
                base_f = f.lower()
                if not base_f.startswith("desktop") and not base_f.startswith("disabled"):
                    ini_files.append(os.path.join(root, f))
                    
    if not ini_files:
        diff_result["WARNINGS"].append(f"모드 폴더에 .ini 파일이 없습니다: {mod_dir}")
        return diff_result
        
    parsed_ini = {"overrides": {}, "resources": {}}
    for ini_path in ini_files:
        parsed = parse_ini_for_diff(ini_path)
        parsed_ini["overrides"].update(parsed.get("overrides", {}))
        parsed_ini["resources"].update(parsed.get("resources", {}))
    
    asset_hash_file = os.path.join(asset_dir, "hash.json")
    if not os.path.exists(asset_hash_file):
        diff_result["WARNINGS"].append(f"에셋 폴더에 hash.json 파일이 없습니다: {asset_dir}")
        return diff_result
        
    asset_json = load_hash_json(asset_hash_file)
    asset_dict = {comp["component_name"]: comp for comp in asset_json}
    
    # 1. Group sections by component
    comp_to_sections = {}
    for sec_name, mapping_info in user_mapping.items():
        comp_name = mapping_info.get("part")
        if comp_name not in comp_to_sections:
            comp_to_sections[comp_name] = []
        comp_to_sections[comp_name].append(sec_name)
        
    for comp_name, sections in comp_to_sections.items():
        if comp_name not in asset_dict:
            diff_result["WARNINGS"].append(f"선택한 파츠 '{comp_name}'가 에셋 정보에 없습니다.")
            continue
            
        asset_comp = asset_dict[comp_name]
        
        # Collect old indexes to map by match_first_index
        old_indexes_info = []
        
        for sec_name in sections:
            mapping_info = user_mapping[sec_name]
            hash_type = mapping_info.get("type")
            
            if sec_name not in parsed_ini["overrides"]:
                diff_result["WARNINGS"].append(f"선택한 섹션 [{sec_name}]이 INI 파일에 없습니다.")
                continue
                
            override_data = parsed_ini["overrides"][sec_name]
            old_hash = override_data.get("hash")
            
            if hash_type in ["draw_vb", "position_vb", "blend_vb", "texcoord_vb", "ib"]:
                new_hash = asset_comp.get(hash_type)
            else:
                new_hash = None
                def get_flat_texs(t_list):
                    res = []
                    for item in t_list:
                        if isinstance(item, list):
                            if len(item) >= 3 and isinstance(item[0], str) and isinstance(item[2], str):
                                res.append(item)
                            else:
                                res.extend(get_flat_texs(item))
                    return res
                    
                flat_texs = get_flat_texs(asset_comp.get("texture_hashes", []))
                for t in flat_texs:
                    if t[0] == hash_type:
                        new_hash = t[2]
                        break
                        
            if old_hash and new_hash and old_hash != new_hash:
                diff_result["HASH_MAPPING"][old_hash] = new_hash
                
            # Collect index for this section
            idx = override_data.get("match_first_index")
            cnt = override_data.get("match_index_count", 0)
            if idx is not None:
                old_indexes_info.append((idx, cnt, sec_name, override_data))
                
            # STRIDE and LAYOUT
            vb0_res = override_data.get("vb0")
            if vb0_res:
                res_data = parsed_ini["resources"].get(vb0_res, {})
                old_stride = res_data.get("stride")
                old_filename = res_data.get("filename")
                
                if old_stride and old_filename:
                    new_vb0_files = glob.glob(os.path.join(asset_dir, f"*{comp_name}*-vb0=*.txt"))
                    if new_vb0_files:
                        new_stride = None
                        with open(new_vb0_files[0], 'r', encoding='utf-8') as f:
                            first_line = f.readline().strip()
                            if first_line.startswith("stride:"):
                                new_stride = int(first_line.split(":")[1].strip())
                        
                        if new_stride is not None and old_stride != new_stride:
                            diff_result["STRIDE_CHANGES"][comp_name] = f"{old_stride} -> {new_stride}"
                            
                            if old_filename.lower().endswith(".txt"):
                                # Search for the old txt file recursively in mod_dir
                                found_old_txt = None
                                for root, _, files in os.walk(mod_dir):
                                    for f in files:
                                        if f.lower() == old_filename.lower():
                                            found_old_txt = os.path.join(root, f)
                                            break
                                    if found_old_txt: break
                                    
                                if found_old_txt:
                                    old_layout = parse_vb_layout(found_old_txt)
                                    new_layout = parse_vb_layout(new_vb0_files[0])
                                    
                                    old_hash_str = found_old_txt.split('=')[-1].split('.')[0] if '=' in found_old_txt else ""
                                    new_hash_str = new_vb0_files[0].split('=')[-1].split('.')[0] if '=' in new_vb0_files[0] else ""
                                    
                                    layout_diff = get_layout_diff(old_layout, new_layout, old_hash_str, new_hash_str, old_stride, new_stride)
                                    if layout_diff:
                                        diff_result["LAYOUT_CHANGES"][comp_name] = layout_diff
                                        
        # Process INDEX_CHANGES
        old_indexes_info.sort(key=lambda x: x[0]) # sort by match_first_index
        new_indexes = asset_comp.get("object_indexes", [])
        new_counts = asset_comp.get("object_index_counts", [])
        classes = asset_comp.get("object_classifications", [])
        
        for i, (old_idx, old_cnt, sec_name, override_data) in enumerate(old_indexes_info):
            if i < len(new_indexes):
                new_idx = new_indexes[i]
                new_cnt = new_counts[i] if i < len(new_counts) else 0
                cls_name = classes[i] if i < len(classes) else f"Section_{i}"
                
                if old_idx != new_idx or old_cnt != new_cnt:
                    if comp_name not in diff_result["INDEX_CHANGES"]:
                        diff_result["INDEX_CHANGES"][comp_name] = {
                            "old_ib_hash": override_data.get("ib") or asset_comp.get("ib"),
                            "new_ib_hash": asset_comp.get("ib")
                        }
                    diff_result["INDEX_CHANGES"][comp_name][cls_name] = {
                        "match_first_index": f"{old_idx} -> {new_idx}",
                        "match_index_count": f"{old_cnt} -> {new_cnt}"
                    }

    return diff_result
