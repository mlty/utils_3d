#!/bin/bash
#SBATCH --job-name=step_batch_score
#SBATCH --array=0-19
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=32
#SBATCH --partition=hpc-high
#SBATCH --time=7-00:00:00
#SBATCH --output=logs/bt_score_%j.log
#SBATCH --error=logs/bt_score_%j.err

echo "Running task $SLURM_ARRAY_TASK_ID"
srun --cpu-bind=none python -u batch_score_glb.py \
     --rank $SLURM_ARRAY_TASK_ID
