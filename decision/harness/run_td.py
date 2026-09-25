# Reproduce the upstream typed-decisions benchmark (Part B of research/scripts/bench_local.py)
# on the Kai checkpoints at their pinned revisions, with the reference runtime on CPU in f32.
import importlib.util, json, os, sys, time
from huggingface_hub import hf_hub_download, snapshot_download

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ["LAYA_SRC"]  # a checkout of github.com/NandhaKishorM/laya at 0.3.20
BUNDLE, REV = "hanzoai/kai-1", "b50502c28537df49a3621f6fa543f9e8521e8a9c"

data_root = os.path.join(HERE, "data")
p = hf_hub_download("LocalLLaMA/typed-decisions", "all/test-00000-of-00001.parquet",
                    repo_type="dataset", local_dir=os.path.join(data_root, "typed-decisions"))
print("dataset", p, flush=True)
local = snapshot_download(BUNDLE, revision=REV)
print("bundle", local, flush=True)

spec = importlib.util.spec_from_file_location("bl", os.path.join(SRC, "research/scripts/bench_local.py"))
bl = importlib.util.module_from_spec(spec); spec.loader.exec_module(bl)
import laya
bl.REPO = data_root
SUB = {"english": None, "multilingual": "multilingual", "typed-decisions": "typed-decisions"}
def load(name):
    ag = laya.load(local, device="cpu", subfolder=SUB[name]); ag.model.eval(); return ag
bl.load = load
results = {"meta": {"bundle": BUNDLE, "revision": REV, "runtime": "laya " + getattr(laya, "__version__", "?"),
                    "device": "cpu", "dtype": "f32", "started": time.strftime("%Y-%m-%d %H:%M:%S")}}
bl.OUT = os.path.join(HERE, "typed_decisions_kai.json")
bl.run_part_b(results)
results["meta"]["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
json.dump(results, open(bl.OUT, "w"), indent=2)
print("wrote", bl.OUT, flush=True)
