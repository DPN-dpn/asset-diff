import os
import json

SCRIPT_TEMPLATE = '''import os
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
    match = re.search(r"\\bhash\\s*=\\s*([0-9a-fA-F]+)", section_content)
    return match.group(1) if match else None

def get_value(section_content, key):
    match = re.search(rf"\\b{key}\\s*=\\s*([^\\n\\r]+)", section_content)
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
            pass # We write the whole file anyway
        f.seek(0)
        f.write(data)

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
            content = f.read()

        # 1. 해시 글로벌 치환
        for pair_name, diffs in DIFF_DATA.items():
            for old_h, new_h in diffs.get("HASH_MAPPING", {}).items():
                content = re.sub(rf"\\b{old_h}\\b", new_h, content)
                
        # 섹션별로 분리
        sections = re.split(r'(^\\[.*?\\])', content, flags=re.MULTILINE)
        
        # 2. 인덱스 치환 및 buf 처리
        for pair_name, diffs in DIFF_DATA.items():
            index_changes = diffs.get("INDEX_CHANGES", {})
            vertex_mapping = diffs.get("VERTEX_GROUP_MAPPING", {})
            
            # 인덱스 변경
            for part, changes in index_changes.items():
                new_ib_hash = changes.get("new_ib_hash")
                
                # content 안에서 new_ib_hash를 가진 섹션을 찾음
                for i in range(1, len(sections), 2):
                    sec_name = sections[i]
                    sec_body = sections[i+1]
                    if new_ib_hash and get_hash(sec_body) == new_ib_hash:
                        # 섹션 A, B 확인
                        for section_key, values in changes.items():
                            if section_key in ["old_ib_hash", "new_ib_hash"]: continue
                            
                            old_first, new_first = values["match_first_index"].split(" -> ")
                            old_cnt, new_cnt = values["match_index_count"].split(" -> ")
                            
                            if f"match_first_index = {old_first}" in sec_body and f"match_index_count = {old_cnt}" in sec_body:
                                sec_body = re.sub(rf"match_first_index\\s*=\\s*{old_first}", f"match_first_index = {new_first}", sec_body)
                                sec_body = re.sub(rf"match_index_count\\s*=\\s*{old_cnt}", f"match_index_count = {new_cnt}", sec_body)
                                sections[i+1] = sec_body

            # 버텍스 그룹(Blend) 처리
            for part, v_map in vertex_mapping.items():
                new_blend_hash = v_map.get("new_blend_hash")
                mapping = v_map.get("mapping", {})
                if not new_blend_hash or not mapping: continue
                
                # TextureOverride 섹션 찾기
                target_resource = None
                for i in range(1, len(sections), 2):
                    if get_hash(sections[i+1]) == new_blend_hash:
                        target_resource = get_value(sections[i+1], "vb2")
                        break
                
                if target_resource:
                    # Resource 섹션 찾아서 파일명 추출
                    buf_filename = None
                    for i in range(1, len(sections), 2):
                        if target_resource in sections[i]:
                            buf_filename = get_value(sections[i+1], "filename")
                            break
                    
                    if buf_filename:
                        process_buf_file(buf_filename, mapping)
        
        # 수정된 ini 저장
        backup_file(ini_file)
        with open(ini_file, 'w', encoding='utf-8') as f:
            f.write("".join(sections))
        print(f"[+] {ini_file} 저장 완료!")
        
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
