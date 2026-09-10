from pathlib import Path
class ConsoleSender:
    """Explicit isolated acceptance-test transport; never claims real SMTP delivery."""
    def __init__(self,directory):self.directory=Path(directory); self.directory.mkdir(parents=True,exist_ok=True)
    def send(self,subject,html,delivery_id):
        (self.directory/(delivery_id+'.html')).write_text(html,encoding='utf-8')
        print('SIMULATED EMAIL:',subject)
