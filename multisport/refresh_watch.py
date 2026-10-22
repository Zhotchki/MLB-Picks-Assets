"""Keep publishing fresh snapshots between delayed cron starts, within the existing provider caps."""
import argparse,json,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
PATHS=['multisport/'+name for name in ('data.json','ledger.json','model.json','feed-state.json','weekly-slips.json')]

def delay(data,now,interval=600):
    target=data.get('platformFeed',{}).get('nextRefreshAt')
    try:
        seconds=(datetime.fromisoformat(target.replace('Z','+00:00'))-now).total_seconds()+5
        return min(interval,max(5,seconds)) if seconds>0 else interval
    except (ValueError,TypeError,AttributeError):return interval

def run(cmd):return subprocess.run(cmd,cwd=ROOT,check=True)

def publish():
    run([sys.executable,'multisport/sheets_export.py'])
    run(['git','add',*PATHS,*[str(p.relative_to(ROOT)) for p in (ROOT/'multisport/sheets').glob('*.csv')]])
    if subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode==0:return
    run(['git','commit','-m','Refresh MultiSport forecasts and final results [skip ci]'])
    run(['git','pull','--rebase','origin','main'])
    run(['git','push','origin','main'])

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--minutes',type=int,default=105);args=parser.parse_args()
    deadline=time.monotonic()+max(0,args.minutes)*60
    while time.monotonic()<deadline:
        data=json.loads((ROOT/'multisport/data.json').read_text())
        seconds=delay(data,datetime.now(timezone.utc))
        if time.monotonic()+seconds>=deadline:break
        until=time.monotonic()+seconds
        while time.monotonic()<until:time.sleep(min(60,max(0,until-time.monotonic())))
        # update_with_retry isolates transient source failures and writes diagnostics.
        result=subprocess.run([sys.executable,'multisport/update_with_retry.py'],cwd=ROOT)
        if result.returncode:
            print('Refresh failed; retaining last published snapshot and retrying on next heartbeat.',flush=True);continue
        publish()
    return 0

if __name__=='__main__':sys.exit(main())
