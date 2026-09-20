"""Shared chart PNGs (memo + deck) — matplotlib, one hue family,
constrained_layout, no tight_layout (project rules)."""

from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ACCENT = "#38bdf8"
ROSE = "#f43f5e"


def _fig(ax_rows: int = 1):
    fig, ax = plt.subplots(figsize=(7, 3.2), constrained_layout=True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(colors="#64748b", labelsize=8)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#334155")
    return fig, ax


def revenue_ebitda_png(periods: list[str], revenue: list[float],
                       ebitda: list[float], out: Path | BytesIO) -> None:
    fig, ax = _fig()
    x = range(len(periods))
    ax.bar(x, revenue, color=ACCENT, alpha=0.35, label="Revenue")
    ax.bar(x, ebitda, color=ACCENT, label="EBITDA")
    ax.set_xticks(list(x), periods)
    ax.legend(frameon=False, fontsize=8)
    ax.set_ylabel("INR crore", fontsize=8, color="#64748b")
    fig.savefig(out, dpi=150)
    plt.close(fig)


def fcf_vs_ebitda_png(periods: list[str], ebitda: list[float],
                      fcf: list[float], out: Path | BytesIO) -> None:
    fig, ax = _fig()
    x = range(len(periods))
    width = 0.38
    ax.bar([i - width / 2 for i in x], ebitda, width=width, color=ACCENT, label="EBITDA")
    ax.bar([i + width / 2 for i in x], fcf, width=width, color=ROSE, label="FCF")
    ax.axhline(0, color="#334155", linewidth=0.8)
    ax.set_xticks(list(x), periods)
    ax.legend(frameon=False, fontsize=8)
    ax.set_ylabel("INR crore", fontsize=8, color="#64748b")
    fig.savefig(out, dpi=150)
    plt.close(fig)


def sensitivity_table_png(wacc_axis: list[float], g_axis: list[float],
                          grid: list[list[float | None]], out: Path | BytesIO
                          ) -> None:
    fig, ax = plt.subplots(figsize=(6, 3.4), constrained_layout=True)
    data = [[(v if v is not None else float("nan")) for v in row] for row in grid]
    image = ax.imshow(data, cmap="BuPu", aspect="auto")
    ax.set_xticks(range(len(g_axis)), [f"{g:.1f}%" for g in g_axis], fontsize=8)
    ax.set_yticks(range(len(wacc_axis)), [f"{w:.2f}%" for w in wacc_axis], fontsize=8)
    ax.set_xlabel("terminal g", fontsize=8, color="#64748b")
    ax.set_ylabel("WACC", fontsize=8, color="#64748b")
    for i, row in enumerate(data):
        for j, v in enumerate(row):
            if v == v:
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7,
                        color="#e2e8f0")
    fig.colorbar(image, ax=ax, shrink=0.85)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def build_all(periods: list[str], series: dict, report: dict,
              out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "revenue": out_dir / "revenue_ebitda.png",
        "fcf": out_dir / "fcf_vs_ebitda.png",
        "sensitivity": out_dir / "sensitivity.png",
    }
    revenue_ebitda_png(periods, series["revenue"], series["ebitda"], paths["revenue"])
    fcf_vs_ebitda_png(periods, series["ebitda"], series["fcf"], paths["fcf"])
    sensitivity_table_png(
        report["sensitivity"]["wacc_axis"], report["sensitivity"]["g_axis"],
        report["sensitivity"]["per_share"], paths["sensitivity"])
    return paths
