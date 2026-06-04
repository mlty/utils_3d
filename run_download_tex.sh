#!/bin/bash
#SBATCH --job-name=batch_copy
#SBATCH --array=0-5
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --partition=hpc-mid
#SBATCH --time=7-00:00:00
#SBATCH --output=logs/download_%j.log
#SBATCH --error=logs/download_%j.err

echo "Running task $SLURM_ARRAY_TASK_ID"
srun --cpu-bind=none python -u test.py \
     --world_size 6 \
     --rank $SLURM_ARRAY_TASK_ID
