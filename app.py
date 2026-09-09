import os
from backend.logger import Logger
from frontend.main_window import MainWindow

class AppContext:
    def __init__(self):
        self.logger = Logger()
        
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.old_dir = os.path.join(self.base_dir, "old asset")
        self.new_dir = os.path.join(self.base_dir, "new asset")
        self.output_dir = os.path.join(self.base_dir, "output")
        
        for d in [self.old_dir, self.new_dir, self.output_dir]:
            os.makedirs(d, exist_ok=True)

def main():
    context = AppContext()
    app = MainWindow(context)
    app.mainloop()

if __name__ == "__main__":
    main()
