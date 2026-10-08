"""Bounded per-game result reads. Failed games stay pending without blocking others."""
from concurrent.futures import ThreadPoolExecutor, as_completed

def load_results(game_ids, loader, workers=4):
    ids=list(dict.fromkeys(game_ids))
    results={};failed=0
    if ids:
        with ThreadPoolExecutor(max_workers=min(workers,len(ids))) as pool:
            jobs={pool.submit(loader,gid):gid for gid in ids}
            for job in as_completed(jobs):
                try:results[jobs[job]]=job.result()
                except Exception:failed+=1
    status='AWAITING_RESULT_SOURCE' if failed and failed==len(ids) else 'PARTIAL_RESULT_SOURCE' if failed else 'CURRENT'
    return results,{'gradingStatus':status,
                    'gradingGamesChecked':len(ids),'gradingGamesUnavailable':failed}
