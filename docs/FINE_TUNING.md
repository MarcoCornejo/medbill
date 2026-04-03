# MedBill-OCR — Fine-Tuning Methodology

**Base Model:** Qwen2.5-VL-3B (3B parameters)
**Method:** LoRA via LLaMA-Factory
**Training Data:** MedBillGen synthetic documents
**Evaluation:** MedBillBench
**HuggingFace:** `medbill/medbill-ocr-lora` *(planned)*

## Hypothesis

Qwen2.5-VL-3B achieves SOTA on general document benchmarks (94.62 on OmniDocBench V1.5). Medical billing has domain-specific challenges: specialized codes (CPT, ICD-10, CARC), financial precision, dense tabular layouts, and domain vocabulary. A LoRA fine-tune on domain-specific synthetic data should improve extraction accuracy by 5-15 MedBillScore points.

## Why LoRA

| Factor | LoRA | Full Fine-Tune |
|---|---|---|
| Trainable params | ~14M (1.6%) | 900M (100%) |
| GPU | 1x A100 40GB | 2-4x A100 80GB |
| Training time | 4-6 hours | 20-30 hours |
| Adapter size | ~50MB | 1.8GB |
| Forgetting risk | Low | Medium |

## Configuration

```yaml
model_name_or_path: Qwen/Qwen2.5-VL-3B-Instruct
finetuning_type: lora
lora_rank: 16
lora_alpha: 32
lora_dropout: 0.05
lora_target: all
num_train_epochs: 3
per_device_train_batch_size: 4
gradient_accumulation_steps: 4
learning_rate: 2.0e-4
lr_scheduler_type: cosine
warmup_ratio: 0.1
bf16: true
seed: 42
```

## Training Data

4,000 documents from MedBillGen, converted to LLaMA-Factory conversation format.

| Subset | Count |
|---|---|
| Medical bills (clean + noisy + errors) | 1,800 |
| EOBs (clean + noisy + denials) | 1,400 |
| Denial letters (clean + noisy) | 600 |
| Mixed difficulty | 200 |

## Ablation Studies

Each ablation: mean +/- std across 3 random seeds.

| Experiment | Variable | Values |
|---|---|---|
| Data scale | Training size | 500, 1K, 2K, 4K |
| LoRA rank | Rank | 4, 8, 16, 32, 64 |
| Augmentation | Noise level | None, Moderate, Heavy, Mixed |
| Template diversity | Templates | 3, 6, 12, 25 |

## Hardware

| Component | Minimum | Recommended |
|---|---|---|
| GPU | 1x RTX 4090 (24GB) | 1x A100 40GB |
| RAM | 32GB | 64GB |
| Training time | ~8 hours | ~4 hours |
| Cloud cost | ~$8-12 (g5.xlarge spot) | |

## Reproducibility

- Training config committed to repo
- Random seeds pinned (42)
- Data generation deterministic with seed
- Training data available on HuggingFace
- Evaluation code in `medbillbench/`
- All ablation results include error bars (3 seeds)
