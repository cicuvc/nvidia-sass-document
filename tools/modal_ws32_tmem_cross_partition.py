"""Run WS M32 same-launch cross-chunk TMEM visibility probes on B200."""
from pathlib import Path
import base64,hashlib,json,zlib
import modal

ROOT=Path(__file__).resolve().parents[1]
FILES=['tests/asm_construct/probe_sm100_ws32_tmem_cross_partition.py','tests/asm_construct/probe_sm100_tmem_cross_partition.py','tests/asm_construct/probe_sm100_as_tmem_snapshot.py','tests/asm_construct/probe_sm100_as_b_fetch.py','tests/asm_construct/probe_sm100_ws_throughput.py']
IMAGE=(modal.Image.from_registry('nvidia/cuda:12.8.1-devel-ubuntu22.04',add_python='3.11').entrypoint([])
       .add_local_dir(ROOT/'assembler','/repo/assembler').add_local_file(ROOT/'sm100.json','/repo/sm100.json'))
for f in FILES:IMAGE=IMAGE.add_local_file(ROOT/f,'/repo/'+f)
app=modal.App('b200-ws32-tmem-cross-partition',image=IMAGE)

@app.function(gpu='B200',cpu=2,timeout=1800)
def run(suite: str,reps: int):
    import os,subprocess,threading
    print('B200 started: ordered controls followed by timed LDTM snapshots.',flush=True)
    gpu=subprocess.run(['nvidia-smi'],capture_output=True,text=True,timeout=30).stdout
    # Distinguish a general cubin-loader failure from a new probe failure.
    # Each loader runs in its own process so a SIGSEGV remains recoverable.
    preflight=[]
    for name,body in (
        ('minimal', "from assembler import assemble_kernel,CudaModule\ns='#fn loader_control() {\\nEXIT;[7:7:{}:5:0]\\n}'\nc=assemble_kernel(s,arch='sm100a').code\nm=CudaModule(c)\nprint('LOAD_OK',flush=True)"),
        ('accepted_as_none', "from assembler import assemble_kernel,CudaModule\nfrom probe_sm100_as_tmem_snapshot import source\nc=assemble_kernel(source(1,1,'none'),arch='sm100a',strict_deps=True).code\nm=CudaModule(c)\nprint('LOAD_OK',flush=True)"),
        ('ws32_cross_partition_none', "from assembler import assemble_kernel,CudaModule\nfrom probe_sm100_ws32_tmem_cross_partition import source\nc=assemble_kernel(source('ws32','none'),arch='sm100a',strict_deps=True).code\nm=CudaModule(c)\nprint('LOAD_OK',flush=True)"),
    ):
        q=subprocess.run(['python3','-X','faulthandler','-u','-c',body],cwd='/repo',capture_output=True,text=True,timeout=90,
                         env=dict(os.environ,PYTHONPATH='/repo:/repo/tests/asm_construct',ASSEMBLER_ARCH='sm100a'))
        record=dict(name=name,returncode=q.returncode,stdout=q.stdout,stderr=q.stderr)
        preflight.append(record)
        print('Loader preflight:',name,q.returncode,flush=True)
    if any(q['returncode'] for q in preflight):
        return dict(returncode=125,gpu=gpu,preflight=preflight,stdout_zlib_b64=base64.b64encode(zlib.compress(b'',9)).decode())
    command=['python3','-X','faulthandler','-u','/repo/'+FILES[0],'--suite',suite,'--reps',str(reps)]
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
                    if results%100 and not any(record.get(k,0) for k in ('other','control_errors','final_errors','row_disagreements','start_inversions','strong_inversions')):continue
                record.pop('d_zlib_b64',None)
                record.pop('snapshot_zlib_b64',None)
                record.pop('raw_zlib_b64',None)
                print(json.dumps(record),flush=True)
            else:
                print(line,end='',flush=True)
    t=threading.Thread(target=collect,daemon=True);t.start()
    try:code=p.wait(timeout=1650)
    except subprocess.TimeoutExpired:p.kill();p.wait();code=124
    t.join(timeout=5)
    return dict(returncode=code,gpu=gpu,preflight=preflight,stdout_zlib_b64=base64.b64encode(zlib.compress(''.join(lines).encode(),9)).decode())

@app.local_entrypoint()
def main(output: str,suite: str='scan',reps: int=1):
    if suite not in ('smoke','scan','focus') or reps<1:raise ValueError('invalid configuration')
    sources={f:(ROOT/f).read_text() for f in FILES+['tools/modal_ws32_tmem_cross_partition.py','assembler/sass_matcher.py']}
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
