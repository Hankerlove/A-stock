import typer
import yaml
from pathlib import Path

app = typer.Typer(help="配置管理")


def _get_config_path() -> Path:
    return Path("config.yaml")


@app.command("show")
def show():
    """显示当前配置（隐藏敏感信息）"""
    cfg_path = _get_config_path()
    if not cfg_path.exists():
        typer.echo("配置文件不存在。")
        raise typer.Exit(1)

    with open(cfg_path) as f:
        raw = yaml.safe_load(f)

    if "tushare" in raw and "token" in raw["tushare"]:
        token = raw["tushare"]["token"]
        raw["tushare"]["token"] = token[:4] + "****" if len(token) > 4 else "****"

    typer.echo(yaml.dump(raw, allow_unicode=True, default_flow_style=False))


@app.command("set")
def set_value(key: str = typer.Argument(..., help="配置项路径，如 tushare.token"), value: str = typer.Argument(..., help="值")):
    """修改配置项"""
    cfg_path = _get_config_path()
    if not cfg_path.exists():
        typer.echo("配置文件不存在。")
        raise typer.Exit(1)

    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    keys = key.split(".")
    target = cfg
    for k in keys[:-1]:
        if k not in target:
            target[k] = {}
        target = target[k]
    target[keys[-1]] = value

    with open(cfg_path, "w") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)

    typer.echo(f"已设置 {key} = {value}")
