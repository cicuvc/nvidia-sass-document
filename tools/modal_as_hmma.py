"""B200 AS collector interference by legacy HMMA; persistent raw evidence."""
from pathlib import Path
import json
import modal

ROOT=Path(__file__).resolve().parents[1]
FILES=['tests/asm_construct/probe_sm100_as_hmma.py',
       'tests/asm_construct/probe_sm100_as_hmma_worker.py',
       'tests/asm_construct/probe_sm100_ws_throughput.py',
       'tests/asm_construct/probe_sm100_as_commit.py',
       'tests/asm_construct/probe_sm100_as_isolation.py']
IMAGE=(modal.Image.from_registry('nvidia/cuda:12.8.1-devel-ubuntu22.04',add_python='3.11')
       .entrypoint([]).add_local_dir(ROOT/'assembler','/repo/assembler')
       .add_local_file(ROOT/'sm100.json','/repo/sm100.json'))
for name in FILES:
    IMAGE=IMAGE.add_local_file(ROOT/name,'/repo/'+name)
app=modal.App('b200-as-hmma',image=IMAGE)


@app.function(gpu='B200',timeout=3600)
def run(mode: str):
    import os
    import subprocess
    import threading
    print('B200 container started; HMMA smoke then AS interference matrix.',flush=True)
    inventory={}
    for label,cmd in [('summary',['nvidia-smi']),('xml',['nvidia-smi','-q','-x']),
                      ('processes',['nvidia-smi','--query-compute-apps=pid,process_name,used_gpu_memory','--format=csv'])]:
        q=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
        inventory[label]=dict(code=q.returncode,stdout=q.stdout,stderr=q.stderr)
    script=FILES[0] if mode=='interleave' else FILES[1]
    p=subprocess.Popen(['python3','-u','/repo/'+script],stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT,text=True,bufsize=1,cwd='/repo',
                       env=dict(os.environ,PYTHONPATH='/repo',ASSEMBLER_ARCH='sm100a'))
    lines=[]
    def collect():
        for line in p.stdout:
            lines.append(line); print(line,end='',flush=True)
    reader=threading.Thread(target=collect,daemon=True);reader.start()
    try: code=p.wait(timeout=3450)
    except subprocess.TimeoutExpired:
        p.kill();p.wait();code=124
    reader.join(timeout=5)
    return dict(returncode=code,stdout=''.join(lines),inventory=inventory)


@app.local_entrypoint()
def main(output: str,mode: str='interleave'):
    if mode not in ('interleave','worker'):raise ValueError(mode)
    sources={name:(ROOT/name).read_text() for name in FILES+
             ['tools/modal_as_hmma.py','assembler/sass_matcher.py']}
    result=run.remote(mode);result['sources']=sources;result['mode']=mode
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Saved {out}/result.json')
    if result['returncode'] or '"event": "complete"' not in result['stdout']:
        raise RuntimeError('HMMA probe did not complete successfully; partial evidence saved')
