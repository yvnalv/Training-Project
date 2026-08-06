# Development Environments & Switching Machines

_Purpose: how to (re)start work on this project on any computer. **Step 1 is always to
check the machine's specs** — that decides which approach to use (train on a local GPU,
offload training, or run inference/integration on CPU). Companion to
[DEPLOYMENT.md](DEPLOYMENT.md), [CONTRIBUTING.md](CONTRIBUTING.md),
[NEXT_STEPS.md](NEXT_STEPS.md)._

---

## TL;DR

1. **Check specs first** (§1) — GPU? CUDA-enabled PyTorch? which env has YOLO26?
2. **Git does not carry everything** (§2) — code + docs + scripts are tracked; **model
   weights, the dataset, and virtualenvs are not** (copy/recreate them).
3. **Match env to task** (§3) — training needs a **CUDA** env with **ultralytics ≥ 8.4**;
   running the app / integration / small evals is fine on **CPU**.

---

## 1. Step 1 on any machine — check the specs

Run these before deciding how to work. They tell you whether to train locally, offload,
or just run inference.

**GPU + driver (does a usable NVIDIA GPU exist?):**
```bash
nvidia-smi        # shows GPU model, VRAM, driver, max CUDA version — or errors if none
```

**For each candidate Python env — is PyTorch CUDA-enabled, and does it have YOLO26?**
```bash
<env>/Scripts/python -c "import torch, ultralytics; \
print('torch', torch.__version__, '| cuda', torch.version.cuda, '| avail', torch.cuda.is_available()); \
print('ultralytics', ultralytics.__version__)"
```
- `cuda None` / `avail False` → that env is **CPU-only** (even if the machine has a GPU —
  it just has the CPU build of torch). Fine for inference; too slow to train.
- **ultralytics ≥ 8.4** is required for YOLO26 (8.3.x has no `yolo26` configs — see §6).

**CPU / RAM (Windows PowerShell):**
```powershell
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors
Get-CimInstance Win32_OperatingSystem | ForEach-Object { "{0:N1} GB free / {1:N1} GB" -f ($_.FreePhysicalMemory/1MB), ($_.TotalVisibleMemorySize/1MB) }
```

### Decision table

| Spec-check result | Approach |
|---|---|
| GPU **and** a CUDA env with ultralytics ≥ 8.4 | **Train locally on the GPU** (`--device 0`). Fast (~30–50 min). |
| GPU present but torch is `+cpu` | Install CUDA torch (`pip install torch torchvision --index-url https://download.pytorch.org/whl/cuXXX`) **or** use the machine's CUDA env. Then train. |
| **No GPU** (CPU only) | **Don't train locally** (10–25 h). Offload to a GPU box or Google Colab (free T4). CPU is still fine for **running the app, integration, and small evals**. |
| Low free RAM (< ~4 GB) | Close apps before training; data loading needs headroom. |

---

## 2. What's tracked vs what you must bring

| Item | In git? | How to get it on a new machine |
|---|---|---|
| App code, `docs/`, `training/` scripts, `requirements.txt` | ✅ Yes | `git pull` (`Refactor-Yolo26`) |
| **Trained weights** (`runs/`, `best_ncnn_model/`, `*.pt`) | ❌ No (gitignored) | **Copy manually** (cloud/USB) — or retrain |
| **Dataset** (`VialVision2.0 v1`) | ❌ No (external) | Re-download from Roboflow, or copy the folder |
| **Virtualenvs** (`.venv`, `testcuda`, …) | ❌ No | Recreate: `python -m venv` + `pip install` |
| `training/data.vialvision.yaml` (absolute paths) | ❌ No (gitignored) | Recreate pointing at the local dataset path |

> **Why weights aren't in git:** they're large binaries and change often — best practice
> is to keep them out of the repo (copy manually, or use release artifacts / Git LFS).

---

## 3. Environment matrix (match env to task)

| Task | Needs GPU? | PyTorch | ultralytics | Notes |
|---|---|---|---|---|
| **Train / retrain YOLO26** | Yes (practically) | CUDA build (`+cuXXX`) | **≥ 8.4** | Use a dedicated training env (e.g. `testcuda`). |
| **Export to NCNN** | No | any | ≥ 8.4 | `training/export_ncnn.py`. |
| **Run the app / integrate / small eval** | No (CPU ok) | CPU build fine | **≥ 8.4** to load a YOLO26 model | The Pi runs its own env; dev machine just needs deps. |

> `requirements.txt` currently allows `ultralytics>=8.0` — for YOLO26 work ensure the
> installed version is **≥ 8.4** (bumping the pin to `>=8.4,<9.0` is recommended).

---

## 4. Switching-computer checklists

### A. Continue APP INTEGRATION / run the app
1. Check specs (§1) — CPU is fine here.
2. `git clone`/`pull` the repo, `git checkout Refactor-Yolo26`.
3. `python -m venv .venv` → activate → `pip install -r requirements.txt` (ensure
   ultralytics ≥ 8.4).
4. **Copy the model** `runs/detect/vialvision_yolo26/weights/best_ncnn_model/` (and
   `best.pt`) from cloud/USB into the project (see §5).
5. Proceed with [NEXT_STEPS.md](NEXT_STEPS.md) **Phase 4** (swap model + `Yellow_Bubble
   → yellow_positive` rename + rack test).

### B. Continue TRAINING / retraining
1. Check specs (§1) — you need a **GPU + CUDA env**. If none, use Colab/another box.
2. `git pull` + checkout `Refactor-Yolo26`.
3. Ensure the CUDA env: `torch.cuda.is_available()` True and ultralytics ≥ 8.4.
4. **Get the dataset** (Roboflow download or copy) and create a local
   `training/data.vialvision.yaml` with the correct absolute `path:`.
5. Run `python training/train_yolo26.py --data training/data.vialvision.yaml --device 0`
   → then `training/export_ncnn.py`. (No need to copy old weights.)

---

## 5. Where to put a copied model

The app loads a model by path. Keep copied artifacts in a **stable, gitignored**
location, e.g. recreate the same layout:
```
runs/detect/vialvision_yolo26/weights/best_ncnn_model/   ← NCNN model dir (for the Pi)
runs/detect/vialvision_yolo26/weights/best.pt            ← PyTorch weights
```
or a simpler `models/` folder — just point `inference.py` at wherever you place it during
integration. `best_ncnn_model` is a **directory** (contains `model.ncnn.param`,
`model.ncnn.bin`, `metadata.yaml`, …) — copy the whole folder, not a single file.

---

## 6. Known environments on the current dev machine (reference — 2026-08-03)

These are specific to the machine used so far; **re-check on any new machine** (§1).

| Env | Python | PyTorch | CUDA | ultralytics | Use |
|---|---|---|---|---|---|
| `C:\yvnalv\yvnalvworks\env\testcuda` | 3.11.9 | 2.5.1+cu121 | ✅ | 8.4.115 | **Training** (RTX 4060) |
| `.venv` (project) | 3.13.1 | 2.11.0+cpu | ❌ | 8.4.37 | App / dev (CPU) |
| `C:\yvnalv\yvnalvworks\Clients\VialVisionEnv` | 3.13.1 | 2.9.1+cpu | ❌ | 8.3.241 | CPU, **no YOLO26** |

Machine: RTX 4060 (8 GB) · i5-12400F (6C/12T) · 16 GB RAM. Dataset:
`C:\yvnalv\yvnalvworks\Clients\VialVision\VialVision2.0.v1i.yolo26`.
