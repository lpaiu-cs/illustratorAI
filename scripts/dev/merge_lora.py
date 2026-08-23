from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge a LoRA adapter into its base model")
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    import torch
    from peft import AutoPeftModelForCausalLM

    model = AutoPeftModelForCausalLM.from_pretrained(
        args.adapter, dtype=torch.bfloat16, device_map="cpu"
    )
    merged = model.merge_and_unload()
    args.out.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(args.out)

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.adapter)
    tokenizer.save_pretrained(args.out)
    print(f"merged model saved to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
