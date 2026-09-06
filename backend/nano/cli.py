"""nano — emergency classifier toolkit. Run as `python -m nano.cli` or `nano`."""
import click

from nano.evaluate import evaluate, load_rows


@click.group()
def cli():
    pass


@cli.command("eval")
@click.option("--predictor", type=click.Choice(["keyword", "qwen", "llama"]), required=True)
@click.option("--model", default="Qwen/Qwen3-0.6B", help="HF path or local dir (qwen only)")
@click.option("--fewshot", is_flag=True, help="prepend 6 examples to the system prompt (qwen only)")
@click.option("--url", default="http://127.0.0.1:8081", help="llama-server base url (llama only)")
@click.option("--data", default="nano/data/seeds.yaml")
@click.option("--threshold", default=0.5, type=float)
@click.option("--name", default=None, help="report name (defaults to predictor)")
def eval_cmd(predictor, model, fewshot, url, data, threshold, name):
    rows = load_rows(data)
    if predictor == "keyword":
        from nano.predictors import keyword as predict
    elif predictor == "llama":
        from nano.predictors import LlamaPredictor
        predict = LlamaPredictor(url)
    else:
        from nano.predictors import QwenPredictor
        predict = QwenPredictor(model, fewshot=fewshot)
    label = name or (predictor + ("_fewshot" if fewshot else "") + ("" if model.startswith("Qwen/") else "_ft"))
    evaluate(label, predict, rows, thr=threshold)
    if predictor == "llama":
        import statistics
        lat = sorted(predict.latencies_ms)
        print(f"latency ms  p50={statistics.median(lat):.0f}  p95={lat[int(len(lat) * 0.95)]:.0f}  max={lat[-1]:.0f}")


if __name__ == "__main__":
    cli()
