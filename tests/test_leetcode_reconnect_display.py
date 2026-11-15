# Author: David Choi (bestshoot21@gmail.com)
"""Check reconnect guidance and refresh after a completed login."""
import json
from pathlib import Path
import subprocess

import pytest

from test_coding_navigation_display import render


def test_expired_session_guidance_uses_the_current_dashboard_connection_controls():
    html = render('codingReviewCard', {'leetcode_history': {
        'username': 'david_choi', 'solution_sync_status': 'reauth_required'}})
    assert 'LeetCode 재로그인 필요' in html
    assert 'id="leetcode-reconnect-settings"' in html
    assert '맨 아래 계정·연결 설정' in html
    assert '공개 완료 기록과 이미 저장된 코드는 유지' in html
    assert '위의 계정' not in html and 'python3' not in html and 'DGX 터미널' not in html


@pytest.mark.parametrize(('previous', 'current', 'reloads', 'timers'), [
    ('starting', 'verified', 1, 0),
    ('awaiting_login', 'verified', 1, 0),
    ('verifying', 'verified', 1, 0),
    ('verified', 'verified', 0, 0),
    ('awaiting_login', 'awaiting_login', 0, 1),
])
def test_account_polling_refreshes_once_after_login_and_keeps_polling_focused_links(previous, current, reloads, timers):
    source = Path(__file__).resolve().parents[1] / 'browser/observatory/workbench.js'
    script = r'''
const fs=require('fs'), vm=require('vm');
const [previous,current]=JSON.parse(fs.readFileSync(0,'utf8'));
const elements={}, active={tagName:'A'};
let reloads=0,timers=0;
const context={$:id=>elements[id]||(elements[id]={contains:el=>el===active}),
document:{activeElement:active,querySelectorAll:()=>[]},window:{},state:{view:'workbench'},
setInterval:()=>0,clearTimeout:()=>{},setTimeout:()=>++timers,esc:String,
api:async()=>({accounts:[{service:'leetcode',status:current,url:'/leetcode-login/vnc.html'}]})};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
context.countReload=()=>++reloads;
vm.runInContext(`bench.room='coding'; bench.accountStatuses={leetcode:${JSON.stringify(previous)}};
loadWorkbench=async()=>countReload();`,context);
(async()=>{await context.loadAccountSettings('coding');
process.stdout.write(JSON.stringify({reloads,timers}));})()
.catch(error=>{console.error(error);process.exitCode=1;});
'''
    result = subprocess.run(['node', '-e', script, str(source)], input=json.dumps([previous, current]),
                            capture_output=True, text=True, check=True, timeout=10)
    assert json.loads(result.stdout) == {'reloads': reloads, 'timers': timers}
