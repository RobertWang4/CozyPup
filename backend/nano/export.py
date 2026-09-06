"""merged/ (HF fp32) → GGUF f16 → Q8_0. Then re-evaluate the quantized file via llama-server.

Usage:
  python -m nano.export --run r3
  llama-server -m nano/models/r3/clf-q8.gguf -c 512 -t 4 --port 8081 --grammar-file nano/serve/grammar.gbnf
  python -m nano.cli eval --predictor llama --name r3_q8

Needs: `brew install llama.cpp` (llama-quantize), `git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp`
and `pip install -e ~/llama.cpp/gguf-py sentencepiece` (the converter imports sentencepiece before it
decides the vocab is BPE; without the module it crashes instead of falling back).

Why quantize: fp32 merged/ is 2.2 GB; Q8 is 610 MB and 3-4x faster on CPU. Q8 keeps every weight
to ~0.4% precision, and on the 606-row test set r3's scores were identical before and after.
"""
import subprocess, sys
from pathlib import Path

import click


@click.command()
@click.option("--run", required=True)
@click.option("--llama-cpp", default=str(Path.home() / "llama.cpp"), help="llama.cpp source checkout (for the converter)")
@click.option("--quant", default="Q8_0", help="Q8_0 (default) or Q4_K_M")
def main(run, llama_cpp, quant):
    d = Path("nano/models") / run
    f16 = d / "clf-f16.gguf"
    out = d / f"clf-{quant.lower().split('_')[0]}.gguf"
    subprocess.run([sys.executable, f"{llama_cpp}/convert_hf_to_gguf.py", str(d / "merged"),
                    "--outfile", str(f16), "--outtype", "f16"], check=True)
    subprocess.run(["llama-quantize", str(f16), str(out), quant], check=True)
    print(f"\n{f16}  {f16.stat().st_size / 1e6:.0f} MB\n{out}  {out.stat().st_size / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
