from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from nic_agent.stage0 import build_sft_training_pair  # noqa: E402


device = "cuda" if torch.cuda.is_available() else "cpu"


def load_pairs(dataset_path: Path, tokenizer, max_len: int) -> list[dict]:
    pairs = []
    for line in dataset_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        sample = json.loads(line)
        pair = build_sft_training_pair(tokenizer, sample["messages"], max_len=max_len)
        pair["goal"] = sample.get("goal", "")
        pair["turn"] = sample.get("turn")
        pairs.append(pair)
    return pairs


def collate(batch: list[dict], pad_id: int):
    max_len = max(len(item["input_ids"]) for item in batch)
    input_ids, labels, attention = [], [], []
    for item in batch:
        padding = max_len - len(item["input_ids"])
        input_ids.append(item["input_ids"] + [pad_id] * padding)
        labels.append(item["labels"] + [-100] * padding)
        attention.append([1] * len(item["input_ids"]) + [0] * padding)
    return {
        "input_ids": torch.tensor(input_ids, device=device),
        "labels": torch.tensor(labels, device=device),
        "attention_mask": torch.tensor(attention, device=device),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 1 LoRA SFT for planner trajectories")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--base-model",
        default="Qwen/Qwen2.5-0.5B-Instruct",
        help="HF model id (smoke default 0.5B; use VL 3B/7B for real runs)",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--max-len", type=int, default=2048)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()

    import torch  # noqa: F401
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    pairs = load_pairs(args.dataset, tokenizer, args.max_len)
    if not pairs:
        print("no samples loaded", file=sys.stderr)
        return 1
    supervised_tokens = sum(
        sum(1 for value in pair["labels"] if value != -100) for pair in pairs
    )
    print(
        f"samples={len(pairs)} supervised_tokens={supervised_tokens}"
        f" max_len={max(len(p['input_ids']) for p in pairs)}"
    )

    pad_id = tokenizer.pad_token_id or tokenizer.eos_token_id
    example_batch = collate(pairs[: min(2, len(pairs))], pad_id)
    print(
        f"batch shape={tuple(example_batch['input_ids'].shape)}"
        f" supervised_in_batch={(example_batch['labels'] != -100).sum().item()}"
    )
    if args.prepare_only:
        return 0

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
    ).to(device)
    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_r * 2,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=args.lr
    )
    model.train()
    for epoch in range(args.epochs):
        epoch_loss = 0.0
        batches = 0
        for start in range(0, len(pairs), args.batch_size):
            batch = collate(pairs[start : start + args.batch_size], pad_id)
            output = model(**batch)
            output.loss.backward()
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            epoch_loss += float(output.loss)
            batches += 1
        mean_loss = epoch_loss / max(1, batches)
        print(f"epoch {epoch + 1}/{args.epochs} mean_loss={mean_loss:.4f}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.out_dir)
    tokenizer.save_pretrained(args.out_dir)
    print(f"adapter saved to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
