import os
import json
import glob

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
