import os, ssl, smtplib
from email.message import EmailMessage
from email.utils import formatdate

class EmailSender:
    def __init__(self,clock=None):
        self.clock=clock
        required=['EMAIL_HOST','EMAIL_PORT','EMAIL_USER','EMAIL_PASSWORD','EMAIL_TO']
        missing=[k for k in required if not os.getenv(k)]
        if missing:raise ValueError('Missing email configuration: '+', '.join(missing))
        self.host=os.environ['EMAIL_HOST']; self.port=int(os.environ['EMAIL_PORT'])
        if self.port not in (465,587):raise ValueError('Use TLS SMTP port 465 or 587')
        self.user=os.environ['EMAIL_USER']; self.password=os.environ['EMAIL_PASSWORD']; self.to=os.environ['EMAIL_TO']
    def send(self, subject, html, delivery_id):
        if self.clock:self.clock.guard()
        msg=EmailMessage(); msg['From']=self.user; msg['To']=self.to; msg['Subject']=subject
        msg['Date']=formatdate(localtime=False); msg['Message-ID']=f'<{delivery_id}@admission-monitor.local>'
        msg.set_content('2027推免监控通知，请使用支持HTML的邮件客户端查看。官方来源链接见HTML正文。')
        msg.add_alternative(html,subtype='html')
        context=ssl.create_default_context()
        if self.clock:self.clock.guard()
        server=smtplib.SMTP_SSL(self.host,self.port,timeout=30,context=context) if self.port==465 else smtplib.SMTP(self.host,self.port,timeout=30)
        with server:
            if self.port==587:server.ehlo(); server.starttls(context=context); server.ehlo()
            server.login(self.user,self.password)
            refused=server.send_message(msg)
            if refused:raise RuntimeError('SMTP recipient rejected')
