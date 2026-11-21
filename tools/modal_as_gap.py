"""Run the hand-SASS WS matrix with live progress and saved evidence on B200."""
from pathlib import Path
import json
import modal

ROOT=Path(__file__).resolve().parents[1]
PROBE=ROOT/'tests/asm_construct/probe_sm100_as_gap.py'
IMAGE=(modal.Image.from_registry('nvidia/cuda:12.8.1-devel-ubuntu22.04',add_python='3.11')
       .entrypoint([]).add_local_dir(ROOT/'assembler','/repo/assembler')
       .add_local_file(ROOT/'sm100.json','/repo/sm100.json')
       .add_local_file(ROOT/'tests/asm_construct/probe_sm100_ws_throughput.py','/repo/tests/asm_construct/probe_sm100_ws_throughput.py')
       .add_local_file(ROOT/'tests/asm_construct/probe_sm100_as_commit.py','/repo/tests/asm_construct/probe_sm100_as_commit.py')
       .add_local_file(ROOT/'tests/asm_construct/probe_sm100_as_isolation.py','/repo/tests/asm_construct/probe_sm100_as_isolation.py')
       .add_local_file(PROBE,'/repo/tests/asm_construct/probe_sm100_as_gap.py'))
app=modal.App('b200-as-gap',image=IMAGE)

@app.function(gpu='B200',timeout=7200)
def run(suite: str,reps: int):
    import os
    import subprocess
    import threading
    command=['python3','-u','/repo/tests/asm_construct/probe_sm100_as_gap.py','--suite',suite]
    print('B200 container started; building and launching SASS cases.',flush=True)
    gpu=subprocess.run(['nvidia-smi'],capture_output=True,text=True,check=True).stdout
    inventory={}
    for label,cmd in [('xml',['nvidia-smi','-q','-x']),('list',['nvidia-smi','-L']),('processes',['nvidia-smi','--query-compute-apps=pid,process_name,used_gpu_memory','--format=csv']),('mig_gi',['nvidia-smi','mig','-lgi']),('mig_ci',['nvidia-smi','mig','-lci'])]:
        q=subprocess.run(cmd,capture_output=True,text=True,timeout=30);inventory[label]=dict(code=q.returncode,stdout=q.stdout,stderr=q.stderr)
    inventory['env']={k:os.environ.get(k) for k in ('CUDA_VISIBLE_DEVICES','NVIDIA_VISIBLE_DEVICES','CUDA_MPS_ACTIVE_THREAD_PERCENTAGE')}
    p=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                       bufsize=1,cwd='/repo',env=dict(os.environ,PYTHONPATH='/repo',ASSEMBLER_ARCH='sm100a'))
    lines=[]
    def collect():
        for line in p.stdout:
            lines.append(line)
            print(line,end='',flush=True)
    reader=threading.Thread(target=collect,daemon=True);reader.start()
    try:
        code=p.wait(timeout=6900)
    except subprocess.TimeoutExpired:
        p.kill();p.wait();code=124
    reader.join(timeout=5)
    return dict(returncode=code,stdout=''.join(lines),gpu=gpu,inventory=inventory)

@app.local_entrypoint()
def main(suite: str='coarse',reps: int=5,output: str='/tmp/ws-sass-full'):
    if suite not in ('coarse','fine','controls','followup','spacing') or reps<1:raise ValueError('invalid suite/reps')
    generator_source=PROBE.read_text()
    result=run.remote(suite,reps)
    result.update(suite=suite,reps=reps,generator_source=generator_source,isolation_source=(ROOT/'tests/asm_construct/probe_sm100_as_isolation.py').read_text(),commit_source=(ROOT/'tests/asm_construct/probe_sm100_as_commit.py').read_text(),base_generator_source=(ROOT/'tests/asm_construct/probe_sm100_ws_throughput.py').read_text())
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Saved {out}/result.json')
    if result['returncode'] or '"event": "complete"' not in result['stdout']:
        raise RuntimeError('SASS probe did not complete successfully')
