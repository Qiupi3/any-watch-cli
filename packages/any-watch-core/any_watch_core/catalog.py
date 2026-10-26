from __future__ import annotations

"""Provider catalog: categories, active mirrors, and lazy site loading.

The CLI uses this module to present the interactive category → site picker and
to load only the providers that were selected.
"""

from dataclasses import dataclass
from importlib import import_module
from typing import Iterable, Sequence


@dataclass(frozen=True)
class CategorySpec:
    key: str
    title: str
    emoji: str
    description: str

    @property
    def menu_label(self) -> str:
        return f"{self.emoji}  {self.title} — {self.description}"


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    name: str
    category: str
    module: str
    class_name: str
    domains: tuple[str, ...]
    subtitle_format: str
    feasibility: str
    kind: str = "stream"  # "stream" or "subtitle"
    note: str = ""

    @property
    def primary_domain(self) -> str:
        return self.domains[0] if self.domains else ""

    @property
    def menu_label(self) -> str:
        if self.kind == "subtitle":
            badge = "subtitle downloader"
        else:
            badge = self.subtitle_format
        return (
            f"[{self.name}] {self.primary_domain} · {badge} · {self.feasibility}"
        )


CATEGORIES: tuple[CategorySpec, ...] = (
    CategorySpec(
        key="flix",
        title="Flix",
        emoji="🍿",
        description="Film & Serial Barat (Hollywood / Global)",
    ),
    CategorySpec(
        key="anime",
        title="Anime",
        emoji="🎌",
        description="Anime Sub Indo (Fansub & Streaming)",
    ),
    CategorySpec(
        key="drama",
        title="Drama",
        emoji="📺",
        description="Drama Korea & China (KDrama / CDrama)",
    ),
)

# Order matters: it is the order shown in the interactive picker and README.
PROVIDER_SPECS: tuple[ProviderSpec, ...] = (
    # ------------------------------------------------------------------ Flix
    ProviderSpec(
        key="flixhq",
        name="FlixHQ",
        category="flix",
        module="any_watch_flix.provider",
        class_name="FlixHQProvider",
        domains=("flixhqz.net",),
        subtitle_format="Softsub",
        feasibility="Sedang",
        note="Existing global movie/TV provider.",
    ),
    ProviderSpec(
        key="lk21",
        name="LK21",
        category="flix",
        module="any_watch_flix.lk21",
        class_name="LK21Provider",
        domains=("tv8.lk21official.my", "layarkaca21.vip", "lk21official.my", "tv.lk21official.my"),
        subtitle_format="Hardsub",
        feasibility="Sedang",
        note="WordPress Muvi theme; domain rotates often.",
    ),
    ProviderSpec(
        key="idlix",
        name="IDLIX",
        category="flix",
        module="any_watch_flix.idlix",
        class_name="IDLIXProvider",
        domains=("idlix.lat", "tv2.idlix.link", "idlix.com", "idlix.link"),
        subtitle_format="Softsub (.vtt)",
        feasibility="Tinggi / Sedang",
        note="DooPlay theme + doo_player_ajax JSON endpoint.",
    ),
    ProviderSpec(
        key="subdl",
        name="SubDL",
        category="flix",
        module="any_watch_flix.subdl",
        class_name="SubDLProvider",
        domains=("subdl.com", "api.subdl.com"),
        subtitle_format="Softsub (.srt/.zip)",
        feasibility="Sangat Tinggi (API)",
        kind="subtitle",
        note="Official REST API; requires a free SUBDL_API_KEY.",
    ),
    # ----------------------------------------------------------------- Anime
    ProviderSpec(
        key="hianime",
        name="HiAnime",
        category="anime",
        module="any_watch_anime.provider",
        class_name="HiAnimeProvider",
        domains=("hianime.at",),
        subtitle_format="Softsub + Hardsub",
        feasibility="Tinggi",
        note="Existing anime provider with encrypted embed payload.",
    ),
    ProviderSpec(
        key="anoboy",
        name="AnoBoy",
        category="anime",
        module="any_watch_anime.anoboy",
        class_name="AnoBoyProvider",
        domains=("anoboy.quest", "anoboy.live"),
        subtitle_format="Hardsub",
        feasibility="Tinggi",
        note="Light WordPress theme; Blogger/StreamWish iframes.",
    ),
    ProviderSpec(
        key="oploverz",
        name="Oploverz",
        category="anime",
        module="any_watch_anime.oploverz",
        class_name="OploverzProvider",
        domains=("oploverz.ch", "oploverz.co.in", "link.oploverz.ltd"),
        subtitle_format="Hardsub",
        feasibility="Sedang",
        note="VenoAnime-style theme; mirror domains rotate.",
    ),
    ProviderSpec(
        key="otakudesu",
        name="OtakuDesu",
        category="anime",
        module="any_watch_anime.otakudesu",
        class_name="OtakuDesuProvider",
        domains=("otakudesu.cloud", "otakudesu.camera", "otakudesu.best", "otakudesu.love"),
        subtitle_format="Hardsub + Softsub",
        feasibility="Tinggi",
        note="POST admin-ajax action=player for mirrors.",
    ),
    ProviderSpec(
        key="samehadaku",
        name="Samehadaku",
        category="anime",
        module="any_watch_anime.samehadaku",
        class_name="SamehadakuProvider",
        domains=(
            "v2.samehadaku.how",
            "samehadaku.care",
            "samehadaku.email",
            "v1.samehadaku.how",
        ),
        subtitle_format="Hardsub + Softsub",
        feasibility="Sedang",
        note="VenoAnime theme; live AJAX search available.",
    ),
    # ----------------------------------------------------------------- Drama
    ProviderSpec(
        key="kisskh",
        name="KissKH",
        category="drama",
        module="any_watch_drama.kisskh",
        class_name="KissKHProvider",
        domains=("kisskh.co", "kisskh.me", "kisskh.tv"),
        subtitle_format="Softsub (.vtt)",
        feasibility="Sangat Tinggi (API)",
        note="REST metadata API + 2ivdeo HLS/subtitle source.",
    ),
    ProviderSpec(
        key="narashika",
        name="NaraShika",
        category="drama",
        module="any_watch_drama.narashika",
        class_name="NaraShikaProvider",
        domains=("narashika.top", "narashika.vip"),
        subtitle_format="Softsub (.srt) + Hardsub",
        feasibility="Tinggi",
        note="Clean GMR theme; .srt links on episode pages.",
    ),
    ProviderSpec(
        key="nontongo",
        name="Nontongo",
        category="drama",
        module="any_watch_drama.nontongo",
        class_name="NontongoProvider",
        domains=("nontongo.site",),
        subtitle_format="Hardsub",
        feasibility="Sedang",
        note="Server-rendered player data-src + episode buttons.",
    ),
    ProviderSpec(
        key="dramaserial",
        name="DramaSerial",
        category="drama",
        module="any_watch_drama.dramaserial",
        class_name="DramaSerialProvider",
        domains=("dramaserial.movie", "tv1.dramaserial.movie"),
        subtitle_format="Hardsub",
        feasibility="Sedang",
        note="GMR/idmuvi theme; KDrama, CDrama, and Lakorn.",
    ),
    ProviderSpec(
        key="drakorindo",
        name="Drakorindo",
        category="drama",
        module="any_watch_drama.drakorindo",
        class_name="DrakorindoProvider",
        domains=("drakorindo.autos", "drakorindo.win"),
        subtitle_format="Hardsub + .srt",
        feasibility="Sedang",
        note="Download-style posts (Filemoon / Mirrored / cloud).",
    ),
)


def get_category(key: str) -> CategorySpec | None:
    key = (key or "").strip().lower()
    return next((c for c in CATEGORIES if c.key == key), None)


def get_specs(
    category: str | None = None, kind: str | None = None
) -> list[ProviderSpec]:
    specs: Iterable[ProviderSpec] = PROVIDER_SPECS
    if category:
        specs = [s for s in specs if s.category == category.lower()]
    if kind:
        specs = [s for s in specs if s.kind == kind]
    return list(specs)


def find_spec(value: str) -> ProviderSpec | None:
    """Find a spec by key, display name, or domain (fuzzy)."""
    needle = (value or "").strip().lower()
    if not needle:
        return None
    for spec in PROVIDER_SPECS:
        names = {spec.key.lower(), spec.name.lower(), spec.module.lower()}
        if needle in names:
            return spec
        if any(needle in d.lower() for d in spec.domains):
            return spec
    # Last chance: substring against name/key
    for spec in PROVIDER_SPECS:
        if needle in spec.name.lower() or needle in spec.key.lower():
            return spec
    return None


def load_provider(spec: ProviderSpec):
    module = import_module(spec.module)
    cls = getattr(module, spec.class_name)
    return cls()


def load_providers(
    specs: Sequence[ProviderSpec], quiet: bool = False
) -> list[tuple[ProviderSpec, object]]:
    """Load provider instances, skipping packages that are not installed."""
    loaded: list[tuple[ProviderSpec, object]] = []
    for spec in specs:
        try:
            loaded.append((spec, load_provider(spec)))
        except ImportError:
            if not quiet:
                print(f"[!] {spec.name} module is not installed ({spec.module}).")
        except Exception as exc:  # noqa: BLE001 - surface a useful message
            if not quiet:
                print(f"[!] Could not load {spec.name}: {exc}")
    return loaded


def format_catalog(category: str | None = None) -> str:
    """Render the provider catalog as a compact terminal table."""
    lines: list[str] = []
    for cat in CATEGORIES:
        if category and cat.key != category:
            continue
        specs = get_specs(cat.key)
        lines.append(f"\n{cat.emoji} {cat.title} — {cat.description}")
        lines.append("-" * 78)
        for spec in specs:
            domains = ", ".join(spec.domains)
            lines.append(f"  {spec.name:<12} {domains}")
            lines.append(
                f"  {'':<12} {spec.subtitle_format} · {spec.feasibility}"
            )
            if spec.note:
                lines.append(f"  {'':<12} {spec.note}")
    return "\n".join(lines)
