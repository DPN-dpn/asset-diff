import os

def scan_assets(base_dir):
    """
    지정된 디렉토리 하위를 탐색하여 hash.json이 존재하는 폴더들의 
    상대 경로 리스트를 반환합니다.
    """
    assets = []
    if os.path.exists(base_dir):
        for root_dir, dirs, files in os.walk(base_dir):
            if "hash.json" in files:
                rel_path = os.path.relpath(root_dir, base_dir)
                assets.append(rel_path)
    return assets
