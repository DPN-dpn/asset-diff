import json
import os
import tkinter as tk
import tkinter.filedialog as fd
import tkinter.simpledialog as sd
import traceback
from tkinter import ttk

from backend.extractor import extract_hash_diff
from backend.mod_extractor import extract_mod_diff
from backend.scanner import scan_assets, scan_mods
from backend.script_generator import generate_script

class DiffPage(ttk.Frame):
    def __init__(self, parent, context):
        super().__init__(parent)
        self.context = context
        self.old_assets = []
        self.new_assets = []
        self.pair_rows = []
        
        self.build_ui()
        
    def build_ui(self):
        # Top: 에셋 검색 영역
        search_frame = ttk.Frame(self)
        search_frame.pack(fill=tk.X, pady=(0, 10))
        
        btn_scan = ttk.Button(search_frame, text="에셋 검색", padding=5, command=self.scan_assets_action)
        btn_scan.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        self.status_lbl = tk.Label(search_frame, text="검색된 에셋 수: 0", relief="solid", borderwidth=1, anchor="center")
        self.status_lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # Middle: 짝맞추기 캔버스 영역
        pairs_container = ttk.LabelFrame(self, text="에셋 매칭 목록")
        pairs_container.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.pairs_canvas = tk.Canvas(pairs_container, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(pairs_container, orient="vertical", command=self.pairs_canvas.yview)
        self.scrollable_frame = ttk.Frame(self.pairs_canvas)
        
        self.scrollable_frame.bind("<Configure>", lambda e: self.pairs_canvas.configure(scrollregion=self.pairs_canvas.bbox("all")))
        self.scroll_window_id = self.pairs_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        # 캔버스 너비 변경 시 프레임 너비 동기화 (가로 꽉 채우기)
        def on_canvas_configure(event):
            self.pairs_canvas.itemconfig(self.scroll_window_id, width=event.width)
        self.pairs_canvas.bind("<Configure>", on_canvas_configure)
        
        self.pairs_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.pairs_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 헤더 라벨 추가
        header_frame = ttk.Frame(self.scrollable_frame)
        header_frame.pack(fill=tk.X, pady=2, padx=5)
        ttk.Label(header_frame, text="Old Asset", anchor="center", font=("", 10, "bold")).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(header_frame, text="New Asset", anchor="center", font=("", 10, "bold")).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(header_frame, width=5).pack(side=tk.LEFT, padx=5) # 삭제 버튼 공간
        
        self.btn_add_pair = ttk.Button(self.scrollable_frame, text="＋", command=self.add_pair_row)
        self.btn_add_pair.pack(fill=tk.X, pady=10, padx=10)
        
        # Bottom: diff 추출 영역
        action_frame = ttk.Frame(self)
        action_frame.pack(fill=tk.X, pady=(10, 0))
        
        btn_exec = ttk.Button(action_frame, text="diff 추출", padding=10, command=self.execute_extraction)
        btn_exec.pack(fill=tk.X)

    def scan_assets_action(self):
        self.context.logger.log(f"스캔 시작: {self.context.old_dir} & {self.context.new_dir}")
        self.old_assets = scan_assets(self.context.old_dir)
        self.new_assets = scan_assets(self.context.new_dir)
        
        self.status_lbl.config(text=f"검색된 에셋 수: (Old: {len(self.old_assets)} / New: {len(self.new_assets)})")
        self.context.logger.log(f"스캔 완료! 구버전 {len(self.old_assets)}개, 신버전 {len(self.new_assets)}개의 에셋을 찾았습니다.")
        
        for old_cb, new_cb, _ in self.pair_rows:
            old_cb['values'] = self.old_assets
            new_cb['values'] = self.new_assets

    def add_pair_row(self):
        row_frame = ttk.Frame(self.scrollable_frame)
        row_frame.pack(fill=tk.X, pady=2, padx=5, before=self.btn_add_pair)
        
        old_cb = ttk.Combobox(row_frame, values=self.old_assets, state="readonly")
        old_cb.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        old_cb.set("Old Asset 선택")
        
        new_cb = ttk.Combobox(row_frame, values=self.new_assets, state="readonly")
        new_cb.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        new_cb.set("New Asset 선택")
        
        btn_del = ttk.Button(row_frame, text="Ｘ", width=5, command=lambda: self.delete_pair_row(row_frame))
        btn_del.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.pair_rows.append((old_cb, new_cb, row_frame))
        self.context.logger.log("새로운 짝 행이 추가되었습니다.")
        
    def delete_pair_row(self, row_frame):
        for i, (old_cb, new_cb, frame) in enumerate(self.pair_rows):
            if frame == row_frame:
                frame.destroy()
                self.pair_rows.pop(i)
                self.context.logger.log("짝 행이 삭제되었습니다.")
                break

    def execute_extraction(self):
        if not self.pair_rows:
            self.context.logger.log("[경고] 비교할 짝이 캔버스에 하나도 없습니다.")
            return
            
        if not os.path.exists(self.context.output_dir):
            os.makedirs(self.context.output_dir)
            
        final_output = {}
        processed_count = 0
        
        self.context.logger.log("=========================================")
        self.context.logger.log("Diff 추출 작업을 시작합니다...")
        
        for old_cb, new_cb, _ in self.pair_rows:
            old_val = old_cb.get()
            new_val = new_cb.get()
            
            if not old_val or not new_val or old_val == "Old Asset 선택" or new_val == "New Asset 선택":
                continue
                
            old_path = os.path.join(self.context.old_dir, old_val)
            new_path = os.path.join(self.context.new_dir, new_val)
            
            try:
                pair_name = f"{old_val} -> {new_val}"
                self.context.logger.log(f"-> 처리 중: {pair_name}")
                diff_result = extract_hash_diff(old_path, new_path)
                final_output[pair_name] = diff_result
                processed_count += 1
            except Exception as e:
                self.context.logger.log(f"[오류] '{pair_name}' 처리 실패: {e}")
                return
                
        if processed_count == 0:
            self.context.logger.log("[경고] 유효한 짝이 선택되지 않았습니다.")
            return

        output_file = os.path.join(self.context.output_dir, "diff.json")
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(final_output, f, indent=4, ensure_ascii=False)
            self.context.logger.log(f"[완료] 총 {processed_count}쌍의 비교 추출이 완료되었습니다.")
            self.context.logger.log(f"[저장됨] {output_file}")
            self.context.logger.log("=========================================")
            
            # 탐색기 열기
            if os.name == 'nt':
                os.startfile(self.context.output_dir)
                
        except Exception as e:
            self.context.logger.log(f"[오류] 저장 실패: {e}")

class ModDiffPage(ttk.Frame):
    def __init__(self, parent, context):
        super().__init__(parent)
        self.context = context
        self.old_mods = []
        self.new_assets = []
        self.pair_rows = []
        
        self.build_ui()
        
    def build_ui(self):
        # Top: 에셋 검색 영역
        search_frame = ttk.Frame(self)
        search_frame.pack(fill=tk.X, pady=(0, 10))
        
        btn_scan = ttk.Button(search_frame, text="목록 갱신", padding=5, command=self.scan_action)
        btn_scan.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        self.status_lbl = tk.Label(search_frame, text="옛 모드: 0 | 신규 에셋: 0", relief="solid", borderwidth=1, anchor="center")
        self.status_lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # Middle: 짝맞추기 캔버스 영역
        pairs_container = ttk.LabelFrame(self, text="모드 - 에셋 매칭 목록")
        pairs_container.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.pairs_canvas = tk.Canvas(pairs_container, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(pairs_container, orient="vertical", command=self.pairs_canvas.yview)
        self.scrollable_frame = ttk.Frame(self.pairs_canvas)
        
        self.scrollable_frame.bind("<Configure>", lambda e: self.pairs_canvas.configure(scrollregion=self.pairs_canvas.bbox("all")))
        self.scroll_window_id = self.pairs_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        def on_canvas_configure(event):
            self.pairs_canvas.itemconfig(self.scroll_window_id, width=event.width)
        self.pairs_canvas.bind("<Configure>", on_canvas_configure)
        
        self.pairs_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.pairs_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 헤더 라벨 추가
        header_frame = ttk.Frame(self.scrollable_frame)
        header_frame.pack(fill=tk.X, pady=2, padx=5)
        ttk.Label(header_frame, text="Old Mod Folder", anchor="center", font=("", 10, "bold")).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(header_frame, text="New Asset", anchor="center", font=("", 10, "bold")).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(header_frame, width=5).pack(side=tk.LEFT, padx=5)
        
        self.btn_add_pair = ttk.Button(self.scrollable_frame, text="＋", command=self.add_pair_row)
        self.btn_add_pair.pack(fill=tk.X, pady=10, padx=10)
        
        # Bottom: diff 추출 영역
        action_frame = ttk.Frame(self)
        action_frame.pack(fill=tk.X, pady=(10, 0))
        
        btn_exec = ttk.Button(action_frame, text="모드 diff 추출", padding=10, command=self.execute_extraction)
        btn_exec.pack(fill=tk.X)

    def scan_action(self):
        self.old_mods = scan_mods(self.context.old_mod_dir)
        self.new_assets = scan_assets(self.context.new_dir)
        self.status_lbl.config(text=f"옛 모드: {len(self.old_mods)} | 신규 에셋: {len(self.new_assets)}")
        self.context.logger.log(f"스캔 완료! 옛 모드 {len(self.old_mods)}개, 신규 에셋 {len(self.new_assets)}개를 찾았습니다.")
        
        for old_cb, new_cb, _ in self.pair_rows:
            old_cb['values'] = self.old_mods
            new_cb['values'] = self.new_assets

    def add_pair_row(self):
        row_frame = ttk.Frame(self.scrollable_frame)
        row_frame.pack(fill=tk.X, pady=2, padx=5, before=self.btn_add_pair)
        
        old_cb = ttk.Combobox(row_frame, values=self.old_mods, state="readonly")
        old_cb.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        old_cb.set("Old Mod 선택")
        
        new_cb = ttk.Combobox(row_frame, values=self.new_assets, state="readonly")
        new_cb.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        new_cb.set("New Asset 선택")
        
        btn_del = ttk.Button(row_frame, text="Ｘ", width=5, command=lambda: self.delete_pair_row(row_frame))
        btn_del.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.pair_rows.append((old_cb, new_cb, row_frame))
        
    def delete_pair_row(self, row_frame):
        for i, (mod_var, new_cb, frame) in enumerate(self.pair_rows):
            if frame == row_frame:
                frame.destroy()
                self.pair_rows.pop(i)
                break

    def execute_extraction(self):
        if not self.pair_rows:
            self.context.logger.log("[경고] 비교할 짝이 없습니다.")
            return
            
        if not os.path.exists(self.context.output_dir):
            os.makedirs(self.context.output_dir)
            
        final_output = {}
        processed_count = 0
        
        self.context.logger.log("=========================================")
        self.context.logger.log("모드 Diff 추출 작업을 시작합니다...")
        
        for old_cb, new_cb, _ in self.pair_rows:
            old_val = old_cb.get()
            new_val = new_cb.get()
            
            if not old_val or not new_val or old_val == "Old Mod 선택" or new_val == "New Asset 선택":
                continue
                
            old_path = os.path.join(self.context.old_mod_dir, old_val)
            new_path = os.path.join(self.context.new_dir, new_val)
            
            try:
                pair_name = f"[Mod]{old_val} -> {new_val}"
                self.context.logger.log(f"-> 처리 중: {pair_name}")
                diff_result = extract_mod_diff(old_path, new_path)
                final_output[pair_name] = diff_result
                processed_count += 1
            except Exception as e:
                self.context.logger.log(f"[오류] '{pair_name}' 처리 실패: {e}")
                return
                
        if processed_count == 0:
            self.context.logger.log("[경고] 유효한 짝이 선택되지 않았습니다.")
            return

        output_file = os.path.join(self.context.output_dir, "diff.json")
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(final_output, f, indent=4, ensure_ascii=False)
            self.context.logger.log(f"[완료] 총 {processed_count}쌍의 비교 추출이 완료되었습니다.")
            self.context.logger.log(f"[저장됨] {output_file}")
            self.context.logger.log("=========================================")
            
            if os.name == 'nt':
                os.startfile(self.context.output_dir)
                
        except Exception as e:
            self.context.logger.log(f"[오류] 저장 실패: {e}")


class ScriptPage(ttk.Frame):
    def __init__(self, parent, context):
        super().__init__(parent)
        self.context = context
        self.loaded_data = {}
        
        self.build_ui()
        
    def build_ui(self):
        # Left/Right Layout
        main_pane = tk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        left_frame = ttk.Frame(main_pane)
        right_frame = ttk.Frame(main_pane)
        main_pane.add(left_frame, minsize=150)
        main_pane.add(right_frame, minsize=300)
        
        # Left: Buttons
        btn_load_output = ttk.Button(left_frame, text="output 불러오기", padding=5, command=self.load_output)
        btn_load_output.pack(fill=tk.X, pady=5)
        
        btn_load_file = ttk.Button(left_frame, text="파일 불러오기", padding=5, command=self.load_file)
        btn_load_file.pack(fill=tk.X, pady=5)
        
        btn_load_text = ttk.Button(left_frame, text="텍스트로 추가", padding=5, command=self.load_text)
        btn_load_text.pack(fill=tk.X, pady=5)
        
        ttk.Frame(left_frame).pack(fill=tk.BOTH, expand=True)
        
        btn_clear = ttk.Button(left_frame, text="초기화", padding=5, command=self.clear_list)
        btn_clear.pack(fill=tk.X, pady=5)
        
        # Right: Treeview
        lbl_list = ttk.Label(right_frame, text="diff 목록 (선택)", font=("", 10, "bold"))
        lbl_list.pack(anchor=tk.W, pady=(0, 5))
        
        list_frame = ttk.Frame(right_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.tree = ttk.Treeview(list_frame, show="tree")
        self.tree.heading("#0", text="추출된 에셋 변경점")
        self.tree.column("#0", width=800, minwidth=500, stretch=tk.YES)
        
        # 클릭만으로 토글되도록 바인딩
        self.tree.bind("<Button-1>", self.on_tree_click)
        
        scroll_y = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        scroll_x = ttk.Scrollbar(list_frame, orient="horizontal", command=self.tree.xview)
        
        self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Bottom: Generate button
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill=tk.X, pady=(5, 0))
        
        btn_generate = ttk.Button(bottom_frame, text="픽스툴 작성", padding=10, command=self.generate_tool)
        btn_generate.pack(fill=tk.X)

    def _parse_and_add_json(self, data):
        added = 0
        for key, val in data.items():
            if key not in self.loaded_data:
                self.loaded_data[key] = val
                
                display_text = key
                if val.get("STRIDE_CHANGES"):
                    display_text += " (⚠️ 규격 변경됨)"
                    
                self.tree.insert("", tk.END, iid=key, text=display_text)
                self.tree.selection_add(key)
                added += 1
        self.context.logger.log(f"총 {added}개의 에셋 diff가 목록에 추가되었습니다.")

    def load_output(self):
        output_file = os.path.join(self.context.output_dir, "diff.json")
        if not os.path.exists(output_file):
            self.context.logger.log(f"[에러] {output_file} 파일이 없습니다.")
            return
            
        with open(output_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.context.logger.log(f"[진행] output/diff.json 파일을 불러왔습니다.")
        self._parse_and_add_json(data)

    def load_file(self):
        filepath = fd.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if not filepath: return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.context.logger.log(f"[진행] {os.path.basename(filepath)} 파일을 불러왔습니다.")
            self._parse_and_add_json(data)
        except Exception as e:
            self.context.logger.log(f"[에러] 파일 로드 실패: {e}")

    def load_text(self):
        dialog = tk.Toplevel(self)
        dialog.title("JSON 텍스트 입력")
        dialog.geometry("600x400")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        
        lbl = ttk.Label(dialog, text="JSON 텍스트를 아래에 붙여넣으세요:", font=("", 10, "bold"))
        lbl.pack(anchor=tk.W, padx=10, pady=(10, 5))
        
        # 버튼 프레임을 먼저 BOTTOM에 pack하여 항상 보이도록 공간 확보
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        frame = ttk.Frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        text_area = tk.Text(frame, wrap="none", font=("Consolas", 10), height=10)
        scroll_y = ttk.Scrollbar(frame, command=text_area.yview)
        scroll_x = ttk.Scrollbar(frame, orient="horizontal", command=text_area.xview)
        text_area.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        def on_submit():
            text = text_area.get("1.0", tk.END).strip()
            if text:
                try:
                    data = json.loads(text)
                    self.context.logger.log("[진행] 텍스트 입력으로 데이터를 불러왔습니다.")
                    self._parse_and_add_json(data)
                    dialog.destroy()
                except Exception as e:
                    self.context.logger.log(f"[에러] JSON 파싱 실패: {e}")
                    import tkinter.messagebox as mb
                    mb.showerror("파싱 에러", f"유효하지 않은 JSON 텍스트입니다:\\n{e}", parent=dialog)
            else:
                dialog.destroy()
                
        btn_submit = ttk.Button(btn_frame, text="불러오기", command=on_submit)
        btn_submit.pack(side=tk.RIGHT, padx=5)
        
        btn_cancel = ttk.Button(btn_frame, text="취소", command=dialog.destroy)
        btn_cancel.pack(side=tk.RIGHT)

    def clear_list(self):
        self.tree.delete(*self.tree.get_children())
        self.loaded_data.clear()
        self.context.logger.log("목록이 초기화되었습니다.")

    def generate_tool(self):
        selected = self.tree.selection()
        if not selected:
            self.context.logger.log("[경고] 픽스툴에 포함할 항목을 선택해주세요.")
            return
            
        final_data = {key: self.loaded_data[key] for key in selected}
        
        # Stride 변경 경고 팝업
        has_stride_changes = any(val.get("STRIDE_CHANGES") for val in final_data.values())
        if has_stride_changes:
            import tkinter.messagebox as mb
            answer = mb.askyesno(
                "경고", 
                "선택된 항목 중 버퍼 규격(Stride)이 변경된 에셋이 포함되어 있습니다.\n\n픽스툴로는 이러한 규격 변경을 완벽히 복구할 수 없으며, 모델이 깨질 위험이 큽니다. 블렌더를 통한 수동 업데이트가 권장됩니다.\n\n그래도 픽스툴을 생성하시겠습니까?",
                parent=self
            )
            if not answer:
                self.context.logger.log("픽스툴 작성이 취소되었습니다.")
                return
        
        if not os.path.exists(self.context.output_dir):
            os.makedirs(self.context.output_dir)
            
        output_path = os.path.join(self.context.output_dir, "auto_update_mod.py")
        
        try:
            generate_script(final_data, output_path)
            self.context.logger.log(f"=========================================")
            self.context.logger.log(f"[성공] 픽스툴 작성이 완료되었습니다!")
            self.context.logger.log(f"저장 위치: {output_path}")
            self.context.logger.log(f"선택된 {len(selected)}개의 에셋 변경사항이 스크립트에 탑재되었습니다.")
            self.context.logger.log(f"=========================================")
            
            # 탐색기 열기
            if os.name == 'nt':
                os.startfile(self.context.output_dir)
                
        except Exception as e:
            err_msg = traceback.format_exc()
            self.context.logger.log(f"[에러] 픽스툴 작성 실패:\\n{err_msg}")

    def on_tree_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            if item in self.tree.selection():
                self.tree.selection_remove(item)
            else:
                self.tree.selection_add(item)
            return "break"
