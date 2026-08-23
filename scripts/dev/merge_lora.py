from __future__ import annotations

import argparse
import json
from pathlib import Path


def resolve_model_cls(base_model_id: str):
    if "vl" in base_model_id.lower():
        from transformers import AutoModelForImageTextToText

        return AutoModelForImageTextToText
    from transformers import AutoModelForCausalLM

    return AutoModelForCausalLM


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge a LoRA adapter into its base model")
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    import torch
    from peft import PeftModel
    from transformers import AutoTokenizer

    adapter_config = json.loads((args.adapter / "adapter_config.json").read_text(encoding="utf-8"))
    base_model_id = adapter_config["base_model_name_or_path"]
    model_cls = resolve_model_cls(base_model_id)

    model = model_cls.from_pretrained(base_model_id, dtype=torch.bfloat16, device_map="cpu")
    peft_model = PeftModel.from_pretrained(model, args.adapter)
    merged = peft_model.merge_and_unload()
    args.out.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(args.out)

    tokenizer = AutoTokenizer.from_pretrained(args.adapter)
    tokenizer.save_pretrained(args.out)
    print(f"merged model saved to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
