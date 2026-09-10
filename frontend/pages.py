import json
import os
import tkinter as tk
import tkinter.filedialog as fd
import tkinter.simpledialog as sd
import traceback
from tkinter import ttk

from backend.extractor import extract_hash_diff
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
        import threading
        thread = threading.Thread(target=self._execute_extraction_thread)
        thread.daemon = True
        thread.start()

    def _execute_extraction_thread(self):
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
        self.asset_parts = []
        self.ini_sections = {}
        self.mapping_vars = {}
        
        self.text_rows = []
        self.cb_rows = []
        
        self.build_ui()
        
    def build_ui(self):
        # Top: Selection
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.X, pady=(0, 10))
        
        btn_refresh = ttk.Button(top_frame, text="갱신", command=self.refresh_lists)
        btn_refresh.pack(side=tk.LEFT, padx=5)
        
        self.cb_asset = ttk.Combobox(top_frame, state="readonly", width=30)
        self.cb_asset.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.cb_asset.set("신규 에셋 선택")
        
        self.cb_mod = ttk.Combobox(top_frame, state="readonly", width=30)
        self.cb_mod.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.cb_mod.set("구버전 모드 선택")
        
        btn_load = ttk.Button(top_frame, text="불러오기", command=self.load_data)
        btn_load.pack(side=tk.RIGHT, padx=5)

        # Middle: Lists
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)
        
        self.left_frame = ttk.LabelFrame(paned, text="신규 에셋 정보")
        self.right_frame = ttk.LabelFrame(paned, text="구버전 모드 매핑")
        paned.add(self.left_frame, minsize=200)
        paned.add(self.right_frame, minsize=400)
        
        # Left Text
        self.asset_text = tk.Text(self.left_frame, wrap="none", font=("Consolas", 9))
        scroll_al = ttk.Scrollbar(self.left_frame, command=self.asset_text.yview)
        self.asset_text.configure(yscrollcommand=scroll_al.set)
        scroll_al.pack(side=tk.RIGHT, fill=tk.Y)
        self.asset_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Right Frame - Search bar
        search_frame = ttk.Frame(self.right_frame)
        search_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(search_frame, text="검색:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.filter_mod_list())
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Right Frame - Dual Canvas
        canvas_container = ttk.Frame(self.right_frame)
        canvas_container.pack(fill=tk.BOTH, expand=True)
        
        self.mod_text_canvas = tk.Canvas(canvas_container, highlightthickness=0, borderwidth=0)
        self.mod_cb_canvas = tk.Canvas(canvas_container, highlightthickness=0, borderwidth=0, width=150)
        
        scroll_y = ttk.Scrollbar(canvas_container, orient="vertical")
        scroll_x = ttk.Scrollbar(canvas_container, orient="horizontal", command=self.mod_text_canvas.xview)
        
        self.mod_text_canvas.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.mod_cb_canvas.configure(yscrollcommand=scroll_y.set)
        
        def sync_yview(*args):
            self.mod_text_canvas.yview(*args)
            self.mod_cb_canvas.yview(*args)
        scroll_y.configure(command=sync_yview)
        
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.mod_cb_canvas.pack(side=tk.RIGHT, fill=tk.Y)
        self.mod_text_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.mod_text_frame = ttk.Frame(self.mod_text_canvas)
        self.mod_cb_frame = ttk.Frame(self.mod_cb_canvas)
        
        self.mod_text_frame.bind("<Configure>", lambda e: self.mod_text_canvas.configure(scrollregion=self.mod_text_canvas.bbox("all")))
        self.mod_cb_frame.bind("<Configure>", lambda e: self.mod_cb_canvas.configure(scrollregion=self.mod_cb_canvas.bbox("all")))
        
        self.mod_text_window = self.mod_text_canvas.create_window((0, 0), window=self.mod_text_frame, anchor="nw")
        self.mod_cb_window = self.mod_cb_canvas.create_window((0, 0), window=self.mod_cb_frame, anchor="nw")
        
        def on_mousewheel(event):
            try:
                x, y = self.winfo_pointerxy()
                rx, ry = self.right_frame.winfo_rootx(), self.right_frame.winfo_rooty()
                rw, rh = self.right_frame.winfo_width(), self.right_frame.winfo_height()
                if rx <= x <= rx+rw and ry <= y <= ry+rh:
                    delta = int(-1*(event.delta/120))
                    self.mod_text_canvas.yview_scroll(delta, "units")
                    self.mod_cb_canvas.yview_scroll(delta, "units")
                    return
                ax, ay = self.left_frame.winfo_rootx(), self.left_frame.winfo_rooty()
                aw, ah = self.left_frame.winfo_width(), self.left_frame.winfo_height()
                if ax <= x <= ax+aw and ay <= y <= ay+ah:
                    self.asset_text.yview_scroll(int(-1*(event.delta/120)), "units")
            except:
                pass
                
        self.bind_all("<MouseWheel>", on_mousewheel)
        
        # Bottom: Extract
        action_frame = ttk.Frame(self)
        action_frame.pack(fill=tk.X, pady=(10, 0))
        
        btn_extract = ttk.Button(action_frame, text="모드 diff 추출", padding=10, command=self.execute_extraction)
        btn_extract.pack(fill=tk.X)
        
    def refresh_lists(self):
        from backend.scanner import scan_assets, scan_mods
        assets = scan_assets(self.context.new_dir)
        mods = scan_mods("old mod")
        
        self.cb_asset['values'] = assets
        self.cb_mod['values'] = mods
        self.context.logger.log("에셋 및 모드 목록이 갱신되었습니다.")
        
    def load_data(self):
        import os, json, glob
        from backend.ini_parser import parse_ini_for_diff
        
        asset_val = self.cb_asset.get()
        mod_val = self.cb_mod.get()
        
        if not asset_val or asset_val.startswith("에셋"):
            self.context.logger.log("[경고] 에셋을 먼저 선택하세요.")
            return
        if not mod_val or mod_val.startswith("모드"):
            self.context.logger.log("[경고] 모드를 먼저 선택하세요.")
            return
            
        # Load Asset info
        asset_path = os.path.join(self.context.new_dir, asset_val)
        hash_file = os.path.join(asset_path, "hash.json")
        self.asset_parts = []
        self.asset_text.delete("1.0", tk.END)
        
        if os.path.exists(hash_file):
            with open(hash_file, 'r', encoding='utf-8') as f:
                asset_data = json.load(f)
            self.asset_part_details = {}
            for comp in asset_data:
                c_name = comp["component_name"]
                self.asset_parts.append(c_name)
                self.asset_text.insert(tk.END, f"[{c_name}]\n")
                
                details = []
                for key in ["draw_vb", "position_vb", "blend_vb", "texcoord_vb", "ib"]:
                    val = comp.get(key)
                    if val:
                        self.asset_text.insert(tk.END, f"  {key}: {val}\n")
                        details.append(key)
                        
                texs = comp.get("texture_hashes")
                if texs:
                    for t in texs:
                        if len(t) >= 1:
                            details.append(t[0])
                        if len(t) >= 3:
                            self.asset_text.insert(tk.END, f"  {t[0]}: {t[2]}\n")
                            
                self.asset_part_details[c_name] = details
                self.asset_text.insert(tk.END, "-"*30 + "\n")
        else:
            self.context.logger.log(f"[에러] {asset_val}에 hash.json이 없습니다.")
            return
            
        # Load Mod info
        mod_path = os.path.join("old mod", mod_val)
        ini_files = []
        for root, _, files in os.walk(mod_path):
            for f in files:
                if f.lower().endswith(".ini"):
                    base_f = f.lower()
                    if not base_f.startswith("desktop") and not base_f.startswith("disabled"):
                        ini_files.append(os.path.join(root, f))
        
        self.mapping_vars.clear()
        
        if not ini_files:
            self.context.logger.log(f"[에러] {mod_val}에 .ini 파일이 없습니다.")
            return
            
        self.ini_sections = {}
        for f in ini_files:
            self.ini_sections.update(parse_ini_for_diff(f))
            
        self.filter_mod_list()
        
        self.context.logger.log("에셋 및 모드 데이터를 성공적으로 불러왔습니다.")

    def filter_mod_list(self):
        import tkinter as tk
        from tkinter import ttk
        
        for widget in self.mod_text_frame.winfo_children(): widget.destroy()
        for widget in self.mod_cb_frame.winfo_children(): widget.destroy()
        
        keyword = self.search_var.get().lower()
        self.text_rows = []
        self.cb_rows = []
        
        for sec_name, data in self.ini_sections.items():
            content_str = f"[{sec_name}]\nhash = {data['hash']}\n{data['hints']}"
            if keyword and keyword not in content_str.lower():
                continue
                
            if self.text_rows:
                ttk.Separator(self.mod_text_frame, orient='horizontal').pack(fill=tk.X, pady=5)
                ttk.Separator(self.mod_cb_frame, orient='horizontal').pack(fill=tk.X, pady=5)
                
            t_row = ttk.Frame(self.mod_text_frame)
            t_row.pack(fill=tk.X, pady=2, padx=2)
            
            lbl = tk.Label(t_row, text=content_str, justify=tk.LEFT, anchor="w", bg="#333333", fg="white")
            lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            c_row = ttk.Frame(self.mod_cb_frame)
            c_row.pack(fill=tk.X, pady=2, padx=2)
            
            var_part = self.mapping_vars.get(f"{sec_name}_part")
            var_type = self.mapping_vars.get(f"{sec_name}_type")
            if not var_part:
                var_part = tk.StringVar(self.mod_cb_frame, value="--")
                var_part.set("--")
                self.mapping_vars[f"{sec_name}_part"] = var_part
            if not var_type:
                var_type = tk.StringVar(self.mod_cb_frame, value="--")
                var_type.set("--")
                self.mapping_vars[f"{sec_name}_type"] = var_type
                
            cb_part = ttk.Combobox(c_row, textvariable=var_part, values=["--"] + self.asset_parts, state="readonly", width=15)
            cb_part.pack(side=tk.TOP, pady=(0, 2), expand=True)
            
            cb_type = ttk.Combobox(c_row, textvariable=var_type, values=["--"], state="readonly", width=15)
            
            def on_part_change(event, vp=var_part, vt=var_type, ct=cb_type):
                part = vp.get()
                if part in self.asset_part_details:
                    ct['values'] = ["--"] + self.asset_part_details[part]
                    if not ct.winfo_manager():
                        ct.pack(side=tk.TOP, expand=True)
                else:
                    ct['values'] = ["--"]
                    if ct.winfo_manager():
                        ct.pack_forget()
                vt.set("--")
            cb_part.bind("<<ComboboxSelected>>", on_part_change)
            
            if var_part.get() in self.asset_part_details:
                cb_type['values'] = ["--"] + self.asset_part_details[var_part.get()]
                cb_type.pack(side=tk.TOP, expand=True)
            
            def on_cb_scroll(event):
                self.mod_text_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
                self.mod_cb_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
                return "break"
            cb_part.bind("<MouseWheel>", on_cb_scroll)
            cb_type.bind("<MouseWheel>", on_cb_scroll)
            
            def sync_height(event, cr=c_row):
                if cr.winfo_reqheight() != event.height or cr.winfo_height() != event.height:
                    cr.configure(height=event.height, width=150)
                    cr.pack_propagate(False)
            t_row.bind("<Configure>", sync_height)
            
            self.text_rows.append(t_row)
            self.cb_rows.append(c_row)
            
        self.mod_text_canvas.yview_moveto(0)
        self.mod_cb_canvas.yview_moveto(0)

    def execute_extraction(self):
        import os, json
        from backend.extractor import extract_mod_diff
        
        asset_val = self.cb_asset.get()
        mod_val = self.cb_mod.get()
        
        if not asset_val or not mod_val or not self.asset_parts:
            self.context.logger.log("[경고] 데이터가 제대로 로드되지 않았습니다.")
            return
            
        user_mapping = {}
        for sec_name in self.ini_sections.keys():
            part = self.mapping_vars.get(f"{sec_name}_part")
            type_val = self.mapping_vars.get(f"{sec_name}_type")
            if part and type_val:
                p = part.get()
                t = type_val.get()
                if p != "--" and t != "--":
                    user_mapping[sec_name] = {"part": p, "type": t}
                
        if not user_mapping:
            self.context.logger.log("[경고] 매핑된 항목이 없습니다.")
            return
            
        mod_dir = os.path.join("old mod", mod_val)
        asset_dir = os.path.join(self.context.new_dir, asset_val)
        
        self.context.logger.log("Mod Diff 추출을 시작합니다...")
        import threading
        thread = threading.Thread(target=self._execute_extraction_thread, args=(mod_dir, asset_dir, user_mapping, mod_val, asset_val))
        thread.daemon = True
        thread.start()

    def _execute_extraction_thread(self, mod_dir, asset_dir, user_mapping, mod_val, asset_val):
        import os, json, re
        from backend.extractor import extract_mod_diff
        try:
            diff_result = extract_mod_diff(mod_dir, asset_dir, user_mapping)
            
            output_name = f"{mod_val}_{asset_val}_diff.json"
            output_name = re.sub(r'[\\/*?:"<>|]', "", output_name)
            
            if not os.path.exists(self.context.output_dir):
                os.makedirs(self.context.output_dir)
                
            out_path = os.path.join(self.context.output_dir, output_name)
            with open(out_path, 'w', encoding='utf-8') as f:
                pair_name = f"{mod_val} -> {asset_val}"
                json.dump({pair_name: diff_result}, f, indent=4, ensure_ascii=False)
                
            self.context.logger.log(f"[완료] {output_name} 저장 완료!")
            if os.name == 'nt':
                os.startfile(self.context.output_dir)
        except Exception as e:
            import traceback
            err_msg = traceback.format_exc()
            self.context.logger.log(f"[에러] Mod Diff 추출 중 오류 발생:\n{err_msg}")

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
        
        self.tree.configure(yscrollcommand=scroll_y.set)
        
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
                    is_fixable = True
                    layout_dict = val.get("LAYOUT_CHANGES", {})
                    if not layout_dict:
                        is_fixable = False
                    else:
                        for comp_name, layout in layout_dict.items():
                            if layout.get("added") or layout.get("removed") or not layout.get("changes"):
                                is_fixable = False
                                break
                    
                    if not is_fixable:
                        display_text += " (⚠️ 수동 업데이트 필요)"
                        
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
        import threading
        thread = threading.Thread(target=self._generate_tool_thread)
        thread.daemon = True
        thread.start()

    def _generate_tool_thread(self):
        selected = self.tree.selection()
        if not selected:
            self.context.logger.log("[경고] 픽스툴에 포함할 항목을 선택해주세요.")
            return
            
        final_data = {key: self.loaded_data[key] for key in selected}
        
        # Stride 변경 경고 팝업 (자동 변환이 불가능한 경우만)
        has_unfixable_stride_changes = False
        for val in final_data.values():
            if val.get("STRIDE_CHANGES"):
                is_fixable = True
                layout_dict = val.get("LAYOUT_CHANGES", {})
                if not layout_dict:
                    is_fixable = False
                else:
                    for comp_name, layout in layout_dict.items():
                        if layout.get("added") or layout.get("removed") or not layout.get("changes"):
                            is_fixable = False
                            break
                
                if not is_fixable:
                    has_unfixable_stride_changes = True
                    break
                
        if has_unfixable_stride_changes:
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
