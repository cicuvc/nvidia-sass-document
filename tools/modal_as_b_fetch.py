"""Run identity-A / shared-B mutation tomography on B200."""
from pathlib import Path
import base64,hashlib,json,zlib
import modal

ROOT=Path(__file__).resolve().parents[1]
FILES=['tests/asm_construct/probe_sm100_as_b_fetch.py','tests/asm_construct/probe_sm100_ws_throughput.py']
IMAGE=(modal.Image.from_registry('nvidia/cuda:12.8.1-devel-ubuntu22.04',add_python='3.11').entrypoint([])
       .add_local_dir(ROOT/'assembler','/repo/assembler').add_local_file(ROOT/'sm100.json','/repo/sm100.json'))
for f in FILES:IMAGE=IMAGE.add_local_file(ROOT/f,'/repo/'+f)
app=modal.App('b200-as-b-fetch',image=IMAGE)

@app.function(gpu='B200',cpu=2,timeout=1800)
def run(suite: str,reps: int):
    import os,subprocess,threading
    print('B200 started: identity-A controls followed by timed B mutation.',flush=True)
    gpu=subprocess.run(['nvidia-smi'],capture_output=True,text=True,timeout=30).stdout
    command=['python3','-u','/repo/'+FILES[0],'--suite',suite,'--reps',str(reps)]
    p=subprocess.Popen(command,cwd='/repo',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                       bufsize=1,env=dict(os.environ,PYTHONPATH='/repo',ASSEMBLER_ARCH='sm100a'))
    lines=[]
    def collect():
        for line in p.stdout:
            lines.append(line)
            # Preserve full payloads in result.json, but avoid flooding Modal's
            # live-log channel (its drain can lag the completed result by minutes).
            if line.startswith('{'):
                record=json.loads(line)
                record.pop('d_zlib_b64',None)
                print(json.dumps(record),flush=True)
            else:
                print(line,end='',flush=True)
    t=threading.Thread(target=collect,daemon=True);t.start()
    try:code=p.wait(timeout=1650)
    except subprocess.TimeoutExpired:p.kill();p.wait();code=124
    t.join(timeout=5)
    return dict(returncode=code,gpu=gpu,stdout_zlib_b64=base64.b64encode(zlib.compress(''.join(lines).encode(),9)).decode())

@app.local_entrypoint()
def main(output: str,suite: str='coarse',reps: int=3):
    if suite not in ('smoke','coarse','fine','tagged') or reps<1:raise ValueError('invalid configuration')
    sources={f:(ROOT/f).read_text() for f in FILES+['tools/modal_as_b_fetch.py','assembler/sass_matcher.py']}
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'assembler').glob('*.py'))+[ROOT/'sm100.json']}
    r=run.remote(suite,reps);r['stdout']=zlib.decompress(base64.b64decode(r.pop('stdout_zlib_b64'))).decode()
    r.update(sources=sources,dependency_sha256=hashes,suite=suite,reps=reps)
    out=Path(output);out.mkdir(parents=True,exist_ok=True);(out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
    print('Saved',out/'result.json')
    if r['returncode'] or '"event": "complete"' not in r['stdout']:raise RuntimeError('Incomplete probe; partial results saved')
