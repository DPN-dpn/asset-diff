import tkinter as tk
from tkinter import ttk
from frontend.pages import DiffPage, ScriptPage, ModDiffPage

class MainWindow(tk.Tk):
    def __init__(self, app_context):
        super().__init__()
        self.app_context = app_context
        self.title("Asset-Diff")
        self.geometry("900x700")
        
        self.create_layout()
        
    def create_layout(self):
        self.top_pane = ttk.Frame(self)
        self.top_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.bottom_pane = ttk.Frame(self, height=150)
        self.bottom_pane.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 하단 로그창 구성
        self.log_text = tk.Text(self.bottom_pane, height=8, bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 10))
        log_scroll = ttk.Scrollbar(self.bottom_pane, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 5), pady=5)
        self.log_text.config(state=tk.DISABLED)

        # 백엔드 로거에 UI 업데이트 콜백 등록
        self.app_context.logger.add_callback(self.write_log)

        # 상단 영역 분할 (좌측 툴바 / 우측 페이지 컨테이너)
        self.toolbar_frame = tk.Frame(self.top_pane, width=120, highlightbackground="#cccccc", highlightthickness=1, padx=5, pady=5)
        self.toolbar_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(5,0), pady=5)
        
        self.page_container = ttk.Frame(self.top_pane)
        self.page_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.page_container.grid_rowconfigure(0, weight=1)
        self.page_container.grid_columnconfigure(0, weight=1)

        # 우측 페이지들 생성
        self.pages = {}
        
        self.pages["diff추출"] = DiffPage(self.page_container, self.app_context)
        self.pages["모드diff"] = ModDiffPage(self.page_container, self.app_context)
        self.pages["픽스툴작성"] = ScriptPage(self.page_container, self.app_context)
        
        for frame in self.pages.values():
            frame.grid(row=0, column=0, sticky="nsew")

        # 좌측 툴바 버튼 구성
        style = ttk.Style()
        style.configure("Toolbar.TButton", font=("", 11, "bold"), padding=10)
        
        btn_diff = ttk.Button(self.toolbar_frame, text="에셋 diff", style="Toolbar.TButton", command=lambda: self.show_page("diff추출"))
        btn_diff.pack(fill=tk.X, pady=5)
        
        btn_mod_diff = ttk.Button(self.toolbar_frame, text="모드 diff", style="Toolbar.TButton", command=lambda: self.show_page("모드diff"))
        btn_mod_diff.pack(fill=tk.X, pady=5)
        
        btn_script = ttk.Button(self.toolbar_frame, text="픽스툴 작성", style="Toolbar.TButton", command=lambda: self.show_page("픽스툴작성"))
        btn_script.pack(fill=tk.X, pady=5)
        
        # 시작 시 첫 번째 페이지 띄우기
        self.show_page("diff추출")
        self.app_context.logger.log("프로그램이 시작되었습니다. 좌측 툴바에서 메뉴를 선택하세요.")

    def show_page(self, page_name):
        frame = self.pages[page_name]
        frame.tkraise()
        self.app_context.logger.log(f"페이지 이동: {page_name}")

    def write_log(self, text):
        def _update():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, text)
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.after(0, _update)
