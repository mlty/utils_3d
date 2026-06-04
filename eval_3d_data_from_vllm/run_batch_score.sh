#!/bin/bash
#SBATCH --job-name=batch_score
#SBATCH --array=0-24
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=32
#SBATCH --partition=hpc-high
#SBATCH --time=7-00:00:00
#SBATCH --output=logs/bt_score_%j.log
#SBATCH --error=logs/bt_score_%j.err

echo "Running task $SLURM_ARRAY_TASK_ID"
srun --cpu-bind=none python -u run_vllm.py \
     --rank $SLURM_ARRAY_TASK_ID \
     --world_size 25