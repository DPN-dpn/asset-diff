import datetime

class Logger:
    def __init__(self):
        self.callbacks = []
        
    def add_callback(self, callback):
        self.callbacks.append(callback)
        
    def log(self, message):
        """로그를 남기고 모든 콜백(예: UI 텍스트 출력기)에 전파합니다."""
        timestamp = datetime.datetime.now().strftime("[%H:%M:%S]")
        formatted_message = f"{timestamp} {message}\n"
        for cb in self.callbacks:
            cb(formatted_message)
