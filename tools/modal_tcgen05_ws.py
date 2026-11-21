"""Compile unmodified CUDA+PTX WS probes and execute on Modal B200.

/home/cicuvc/miniconda3/envs/blkw/bin/python -m modal run tools/modal_tcgen05_ws.py
"""
from pathlib import Path
import modal

IMAGE = modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.11").entrypoint([])
app = modal.App("tcgen05-ws-behavior", image=IMAGE)

@app.function(gpu="B200", timeout=600)
def run(source: str, reps: int, nvcc_flags: str = "") -> dict:
    import subprocess
    import tempfile
    import hashlib
    import shlex
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        cu=root/"ws.cu"; exe=root/"ws"
        cu.write_text(source)
        command=["nvcc","-arch=sm_100a","-O3","-std=c++17",*shlex.split(nvcc_flags),str(cu),"-o",str(exe)]
        build=subprocess.run(command,capture_output=True,text=True,timeout=120)
        result={"source_text":source,"nvcc_flags":nvcc_flags,"source_sha256":hashlib.sha256(source.encode()).hexdigest(),"build_stdout":build.stdout,"build_stderr":build.stderr,"build_returncode":build.returncode}
        if build.returncode: return result
        result["sass"]=subprocess.run(["cuobjdump","-sass",str(exe)],capture_output=True,text=True,check=True).stdout
        result["nvcc"]=subprocess.run(["nvcc","--version"],capture_output=True,text=True,check=True).stdout
        result["gpu"]=subprocess.run(["nvidia-smi"],capture_output=True,text=True,check=True).stdout
        try:
            p=subprocess.run([str(exe),str(reps)],capture_output=True,text=True,timeout=180)
            result.update(stdout=p.stdout,stderr=p.stderr,returncode=p.returncode)
        except subprocess.TimeoutExpired as e:
            result.update(stdout=(e.stdout or b"").decode(),stderr="GPU subprocess timed out",returncode=124)
        return result

@app.local_entrypoint()
def main(reps: int=3, output: str="/tmp/tcgen05-ws-behavior",
         source: str="tests/tcgen05_ws_behavior.cu", nvcc_flags: str=""):
    import json
    repo=Path(__file__).resolve().parents[1]
    if reps < 1:
        raise ValueError("reps must be positive")
    result=run.remote((repo/source).read_text(),reps,nvcc_flags)
    out=Path(output); out.mkdir(parents=True,exist_ok=True)
    sass=result.pop("sass",""); (out/"ws.sass").write_text(sass)
    (out/"result.json").write_text(json.dumps(result,indent=2))
    print(result.get("build_stderr","")); print(result.get("stdout","")); print(result.get("stderr",""))
    print(f"Artifacts: {out}")
    if result.get("build_returncode") or result.get("returncode",1):
        raise RuntimeError("WS probe failed; inspect saved artifacts")
