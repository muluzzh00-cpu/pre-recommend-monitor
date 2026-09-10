import argparse, logging, os
from pathlib import Path
import yaml
from dotenv import load_dotenv
from monitor_clock import MonitorClock, PeriodEnded

def main():
    ap=argparse.ArgumentParser(description='2027建筑/规划推免监控')
    group=ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--run-once',action='store_true'); group.add_argument('--test-email',action='store_true')
    group.add_argument('--check-window',action='store_true')
    ap.add_argument('--state-dir',default='state'); ap.add_argument('--console',action='store_true',help='模拟邮件，仅用于独立验收状态')
    ap.add_argument('--git-state',action='store_true'); ap.add_argument('--report-dir',default='logs')
    args=ap.parse_args(); root=Path(__file__).resolve().parent
    settings=yaml.safe_load((root/'config/settings.yaml').read_text(encoding='utf-8'))
    clock=MonitorClock(settings)
    # Before constructing HTTP or SMTP clients, or touching network-backed state.
    if clock.status()!='active':
        print('Monitoring period has ended.' if clock.status()=='ended' else 'Monitoring period has not started.')
        return 0
    if args.check_window:print('active'); return 0
    load_dotenv(root/'.env'); Path(args.report_dir).mkdir(parents=True,exist_ok=True)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',handlers=[logging.StreamHandler(),logging.FileHandler(Path(args.report_dir)/'monitor.log',encoding='utf-8')])
    if args.console and (args.git_state or args.state_dir=='state'):raise ValueError('--console requires a separate --state-dir and forbids --git-state')
    from notifier.console import ConsoleSender
    from notifier.email import EmailSender
    sender=ConsoleSender(Path(args.report_dir)/'email-previews') if args.console else EmailSender(clock)
    if args.test_email:
        sender.send('【测试】【2027推免监控】邮件连接测试','<h1>邮件连接测试成功</h1><p>此邮件不表示全部监控源或定时任务已通过验收。</p>','test-'+clock.now().strftime('%Y%m%d%H%M%S'))
        print('Simulated test email saved.' if args.console else 'Test email accepted by SMTP server. Check your inbox.'); return 0
    sites=yaml.safe_load((root/'config/sites.yaml').read_text(encoding='utf-8'))['sites']
    from crawlers.base import HttpClient
    from database.state import StateStore
    from engine import run
    try:return run(settings,sites,clock,HttpClient(settings,clock),StateStore(args.state_dir,args.git_state,clock),sender,args.report_dir)
    except PeriodEnded as exc:print(str(exc)); return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        # Never dump SMTP exception payloads, passwords or environment variables.
        logging.error('Fatal: %s. %s',type(exc).__name__,str(exc) if isinstance(exc,(ValueError,RuntimeError)) else 'See configuration/network/state health; secrets are suppressed.')
        raise SystemExit(1)
