"""Run sparse B-input staging tests on B200."""
from pathlib import Path
import base64,hashlib,json,zlib
import modal

ROOT=Path(__file__).resolve().parents[1]
FILES=['tests/asm_construct/probe_sm100_as_b_stage.py','tests/asm_construct/probe_sm100_as_b_fetch.py','tests/asm_construct/probe_sm100_ws_throughput.py']
IMAGE=(modal.Image.from_registry('nvidia/cuda:12.8.1-devel-ubuntu22.04',add_python='3.11').entrypoint([])
       .add_local_dir(ROOT/'assembler','/repo/assembler').add_local_file(ROOT/'sm100.json','/repo/sm100.json'))
for f in FILES:IMAGE=IMAGE.add_local_file(ROOT/f,'/repo/'+f)
app=modal.App('b200-as-b-stage',image=IMAGE)

@app.function(gpu='B200',cpu=2,timeout=1800)
def run(suite: str,reps: int):
    import os,subprocess,threading
    print('B200 started: ordered controls followed by sparse shared-B perturbations.',flush=True)
    gpu=subprocess.run(['nvidia-smi'],capture_output=True,text=True,timeout=30).stdout
    command=['python3','-u','/repo/'+FILES[0],'--suite',suite,'--reps',str(reps)]
    p=subprocess.Popen(command,cwd='/repo',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                       bufsize=1,env=dict(os.environ,PYTHONPATH='/repo',ASSEMBLER_ARCH='sm100a'))
    lines=[]
    def collect():
        results=0
        for line in p.stdout:
            lines.append(line)
            # Preserve full payloads in result.json, but avoid flooding Modal's
            # live-log channel (its drain can lag the completed result by minutes).
            if line.startswith('{'):
                record=json.loads(line)
                if record.get('event')=='launch':continue
                if record.get('event')=='result':
                    results+=1
                    if results%100 and not any(record.get(k,0) for k in ('other','control_errors','final_errors','row_disagreements')):continue
                record.pop('d_zlib_b64',None)
                record.pop('snapshot_zlib_b64',None)
                record.pop('shared_zlib_b64',None)
                record.pop('checked_zlib_b64',None)
                print(json.dumps(record),flush=True)
            else:
                print(line,end='',flush=True)
    t=threading.Thread(target=collect,daemon=True);t.start()
    try:code=p.wait(timeout=1650)
    except subprocess.TimeoutExpired:p.kill();p.wait();code=124
    t.join(timeout=5)
    return dict(returncode=code,gpu=gpu,stdout_zlib_b64=base64.b64encode(zlib.compress(''.join(lines).encode(),9)).decode())

@app.local_entrypoint()
def main(output: str,suite: str='cutoff',reps: int=1):
    if suite not in ('smoke','cutoff','joint','checked') or reps<1:raise ValueError('invalid configuration')
    sources={f:(ROOT/f).read_text() for f in FILES+['tools/modal_as_b_stage.py','assembler/sass_matcher.py']}
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'assembler').glob('*.py'))+[ROOT/'sm100.json']}
    # A durable FunctionCall survives local collection failures. In contrast,
    # the input-plane .remote() path lost its result after AttemptAwait timed out.
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    call=run.spawn(suite,reps)
    metadata=dict(sources=sources,dependency_sha256=hashes,suite=suite,reps=reps,function_call_id=call.object_id)
    (out/'request.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print('Durable call:',call.object_id,flush=True)
    connection_errors=0
    while True:
        try:r=call.get(timeout=60);break
        except (modal.exception.FunctionTimeoutError,modal.exception.OutputExpiredError):raise
        except (TimeoutError,modal.exception.TimeoutError):continue
        except (ConnectionError,modal.exception.ConnectionError):
            connection_errors+=1
            if connection_errors>=3:raise
            print('Retrying result collection for',call.object_id,flush=True)
    r['stdout']=zlib.decompress(base64.b64decode(r.pop('stdout_zlib_b64'))).decode()
    r.update(metadata)
    (out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
    print('Saved',out/'result.json')
    if r['returncode'] or '"event": "complete"' not in r['stdout']:raise RuntimeError('Incomplete probe; partial results saved')
