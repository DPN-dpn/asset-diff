import os
import json

SCRIPT_TEMPLATE = r'''import os
import struct
import glob
import re
import shutil

DIFF_DATA = {diff_data}

BACKED_UP = set()

def backup_file(filepath):
    abs_path = os.path.abspath(filepath)
    if abs_path in BACKED_UP:
        return
    backup_path = filepath + ".bak"
    if not os.path.exists(backup_path):
        shutil.copy2(filepath, backup_path)
        print(f"[*] 백업 생성됨: {backup_path}")
    BACKED_UP.add(abs_path)

def get_hash(section_content):
    match = re.search(r"\bhash\s*=\s*([0-9a-fA-F]+)", section_content)
    return match.group(1) if match else None

def get_value(section_content, key):
    match = re.search(rf"\b{key}\s*=\s*([^\n\r]+)", section_content)
    return match.group(1).strip() if match else None

def process_buf_file(filepath, mapping):
    if not os.path.exists(filepath):
        print(f"[-] 파일 없음: {filepath}")
        return
        
    print(f"[+] 버퍼 수정 중: {filepath}")
    backup_file(filepath)
    with open(filepath, 'r+b') as f:
        data = bytearray(f.read())
        stride = 32
        for offset in range(0, len(data), stride):
            changed = False
            for i in (16, 20, 24, 28):
                byte_index = offset + i
                byte_val = data[byte_index]
                val_str = str(byte_val)
                if val_str in mapping:
                    data[byte_index] = int(mapping[val_str])
                    changed = True
        if changed:
            print(f"  - [버퍼] {filepath} 내부 뼈대 인덱스 수정 완료")
        f.seek(0)
        f.write(data)

def process_layout_changes(sections, diffs):
    layout_changes = diffs.get("LAYOUT_CHANGES", {})
    if not layout_changes: return
    
    for comp_name, layout in layout_changes.items():
        new_hash = layout.get("new_hash")
        if not new_hash: continue
        
        target_resource_names = []
        for i in range(1, len(sections), 2):
            if get_hash(sections[i+1]) == new_hash:
                for vb in ['vb0', 'vb1', 'vb2', 'vb3', 'vb4']:
                    res = get_value(sections[i+1], vb)
                    if res: target_resource_names.append(res)
                break
                
        if not target_resource_names: continue
        
        resources = []
        for res_name in target_resource_names:
            for i in range(1, len(sections), 2):
                if res_name in sections[i]:
                    stride = get_value(sections[i+1], "stride")
                    filename = get_value(sections[i+1], "filename")
                    if stride and filename:
                        resources.append({
                            "name": res_name,
                            "stride": int(stride),
                            "filename": filename,
                            "section_idx": i+1
                        })
                    break
                    
        current_offset = 0
        for res in resources:
            res["start_offset"] = current_offset
            current_offset += res["stride"]
            res["end_offset"] = current_offset
            
        if current_offset != layout.get("old_stride"):
            print(f"[-] [경고] {comp_name}의 버퍼 총합({current_offset})이 분석된 옛날 stride({layout.get('old_stride')})와 다릅니다. 자동 레이아웃 변환 생략.")
            continue
            
        for change in layout.get("changes", []):
            old_off = change.get("old_offset")
            old_struct = change.get("old_struct")
            new_struct = change.get("new_struct")
            
            if old_off is None or not old_struct or not new_struct: continue
            
            target_res = None
            for res in resources:
                if res["start_offset"] <= old_off < res["end_offset"]:
                    target_res = res
                    break
            
            if not target_res: continue
            
            local_off = old_off - target_res["start_offset"]
            filepath = target_res["filename"]
            
            if not os.path.exists(filepath):
                print(f"[-] 버퍼 파일 없음: {filepath}")
                continue
                
            backup_file(filepath)
            print(f"[+] 제네릭 버퍼 구조 변환 중 ({change.get('semantic')}): {filepath}")
            
            old_stride = target_res["stride"]
            size_diff = change.get("new_size", 0) - change.get("old_size", 0)
            new_stride = old_stride + size_diff
            
            with open(filepath, 'rb') as f:
                data = f.read()
            
            new_data = bytearray()
            for offset in range(0, len(data), old_stride):
                chunk = data[offset:offset+old_stride]
                if len(chunk) < old_stride: break
                
                before = chunk[:local_off]
                target_bytes = chunk[local_off:local_off+change.get("old_size")]
                after = chunk[local_off+change.get("old_size"):]
                
                try:
                    old_vals = struct.unpack(old_struct, target_bytes)
                    if change.get("old_type") == "unorm" and change.get("new_type") == "float":
                        new_vals = [v / 255.0 for v in old_vals]
                    else:
                        new_vals = old_vals
                    new_bytes = struct.pack(new_struct, *new_vals)
                    new_data.extend(before + new_bytes + after)
                except Exception as e:
                    print(f"[-] 구조체 변환 실패: {e}")
                    new_data.extend(chunk)
            
            with open(filepath, 'wb') as f:
                f.write(new_data)
                
            sec_body = sections[target_res["section_idx"]]
            sec_body, count = re.subn(rf"stride\s*=\s*{old_stride}", f"stride = {new_stride}", sec_body)
            sections[target_res["section_idx"]] = sec_body
            target_res["stride"] = new_stride
            print(f"  - [INI 업데이트] {filepath}의 stride가 {old_stride}에서 {new_stride}로 변경되었습니다.")

def main():
    print("=== 모드 자동 업데이트 시작 ===")
    ini_files = []
    for root, dirs, files in os.walk("."):
        for f in files:
            if f.endswith(".ini") and not f.lower().startswith("disabled"):
                ini_files.append(os.path.join(root, f))
    
    if not ini_files:
        print("[-] 현재 폴더에 .ini 파일이 없습니다.")
        os.system("pause")
        return
        
    for ini_file in ini_files:
        print(f"\\n[+] 분석 중: {ini_file}")
        with open(ini_file, 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        content = original_content

        for pair_name, diffs in DIFF_DATA.items():
            for old_h, new_h in diffs.get("HASH_MAPPING", {}).items():
                content, count = re.subn(rf"\b{old_h}\b", new_h, content)
                if count > 0:
                    print(f"  - [해시 치환] {old_h} ➔ {new_h} ({count}곳)")
                
        sections = re.split(r'(^\[.*?\])', content, flags=re.MULTILINE)
        
        for pair_name, diffs in DIFF_DATA.items():
            index_changes = diffs.get("INDEX_CHANGES", {})
            vertex_mapping = diffs.get("VERTEX_GROUP_MAPPING", {})
            
            for part, changes in index_changes.items():
                new_ib_hash = changes.get("new_ib_hash")
                for i in range(1, len(sections), 2):
                    sec_name = sections[i]
                    sec_body = sections[i+1]
                    if new_ib_hash and get_hash(sec_body) == new_ib_hash:
                        for section_key, values in changes.items():
                            if section_key in ["old_ib_hash", "new_ib_hash"]: continue
                            
                            old_first = new_first = old_cnt = new_cnt = None
                            if "match_first_index" in values:
                                old_first, new_first = values["match_first_index"].split(" -> ")
                            if "match_index_count" in values:
                                old_cnt, new_cnt = values["match_index_count"].split(" -> ")
                            
                            if old_first and f"match_first_index = {old_first}" in sec_body:
                                sec_body, count = re.subn(rf"match_first_index\s*=\s*{old_first}", f"match_first_index = {new_first}", sec_body)
                                if count > 0:
                                    print(f"  - [인덱스 치환] match_first_index: {old_first} ➔ {new_first}")
                            if old_cnt and f"match_index_count = {old_cnt}" in sec_body:
                                sec_body, count = re.subn(rf"match_index_count\s*=\s*{old_cnt}", f"match_index_count = {new_cnt}", sec_body)
                                if count > 0:
                                    print(f"  - [카운트 치환] match_index_count: {old_cnt} ➔ {new_cnt}")
                            
                            sections[i+1] = sec_body

            for part, v_map in vertex_mapping.items():
                new_blend_hash = v_map.get("new_blend_hash")
                mapping = v_map.get("mapping", {})
                if not new_blend_hash or not mapping: continue
                
                target_resource = None
                for i in range(1, len(sections), 2):
                    if get_hash(sections[i+1]) == new_blend_hash:
                        target_resource = get_value(sections[i+1], "vb2")
                        break
                
                if target_resource:
                    buf_filename = None
                    for i in range(1, len(sections), 2):
                        if target_resource in sections[i]:
                            buf_filename = get_value(sections[i+1], "filename")
                            break
                    if buf_filename:
                        process_buf_file(buf_filename, mapping)
                        
            # Apply Layout Changes
            process_layout_changes(sections, diffs)
        
        new_content = "".join(sections)
        if original_content != new_content:
            backup_file(ini_file)
            with open(ini_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"[+] {ini_file} 수정 및 저장 완료!")
        else:
            print(f"[-] {ini_file} 변경 사항 없음.")
        
    print("\\n=== 업데이트 완료! ===")
    os.system("pause")

if __name__ == "__main__":
    main()
'''

def generate_script(diff_data, output_path):
    data_str = json.dumps(diff_data, indent=4, ensure_ascii=False)
    final_script = SCRIPT_TEMPLATE.replace("{diff_data}", data_str)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final_script)
