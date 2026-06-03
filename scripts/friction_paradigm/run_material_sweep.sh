#!/bin/bash
# Rotate through 4 materials, 6h per material, total 24h
# Collects data for material × mu × mass × params formula-fit

cd /home/anton/projects/Omniverse_Nemotron_Ext
source /home/anton/miniconda3/etc/profile.d/conda.sh && conda activate isaac_lab_env

for MAT in rubber metal plastic glass; do
    echo "========================================"
    echo "MATERIAL: $MAT  ($(date +'%Y-%m-%d %H:%M'))"
    echo "========================================"
    python scripts/friction_paradigm/rl_tune_v2.py --max-hours 6 --random --material "$MAT" 2>&1 | tee -a /tmp/sweep_${MAT}.log
    echo "DONE: $MAT  ($(date +'%Y-%m-%d %H:%M'))"
done

echo "ALL MATERIALS DONE: $(date)"
