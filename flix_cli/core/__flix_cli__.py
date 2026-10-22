#!/usr/bin/env python3

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# ruff: noqa: UP035 - allow using typing.List
from typing import Annotated, List, Optional
from urllib.parse import urljoin

import httpx
import regex as re
import typer
from bs4 import BeautifulSoup
from fzf import fzf_prompt
from platformdirs import user_downloads_path

from .__version__ import __core__
from .utils.__cast__ import cast
from .utils.__decryptor__ import decrypt_stream_url
from .utils.__downloader__ import download
from .utils.__player__ import play

FLIXHQ_BASE_URL = "https://flixhqz.net"
FLIXHQ_SEARCH_URL = f"{FLIXHQ_BASE_URL}/search"
FLIXHQ_AJAX_URL = f"{FLIXHQ_BASE_URL}/ajax"
DECODER = "https://dec.eatmynerds.live"


class Action(str, Enum):
    PLAY = "play"
    DOWNLOAD = "download"
    CAST = "cast"


class MediaType(str, Enum):
    MOVIE = "movie"
    SERIES = "series"


def episode_range(ep_input: str) -> range:
    """Parse episode input to handle ranges like '5-7' or single episodes like '5'"""
    ep_input = ep_input.strip()

    try:
        if "-" in ep_input:
            start, end = ep_input.split("-", 1)
            start_ep = int(start.strip())
            end_ep = int(end.strip())

            # prevents the last episode being played if user enters 0
            if start_ep == 0:
                start_ep = 1
            if end_ep == 0:
                end_ep = 1

            if start_ep > end_ep:
                start_ep, end_ep = end_ep, start_ep

            return range(start_ep, end_ep + 1)
        else:
            ep = int(ep_input)
            # prevents the last episode being played if user enters 0
            if ep == 0:
                ep = 1
            return range(ep, ep + 1)

    except ValueError:
        raise typer.BadParameter(
            "Invalid episode/range, input must be a number or range in the form <num>-<num>"
        )


@dataclass
class Context:
    client: httpx.Client

    query: str | None = None
    url: str | None = None
    title: str | None = None
    content_type: MediaType | None = None

    season: int | None = None
    episodes: range | None = None

    selected_media: list[dict[str, str | int | None]] | None = None
    selected_subtitles: list[str] = field(default_factory=list)

    dl_path: Path = user_downloads_path()
    play_type: Action | None = None


def search_content(query: str, client: httpx.Client):
    """Search for content on FlixHQ"""
    try:
        # Try keyword query parameter first
        response = client.get(FLIXHQ_SEARCH_URL, params={"keyword": query})
        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.find_all("div", class_="flw-item")

        # Fallback to path-based search if needed
        if not items:
            search_params = query.replace(" ", "-")
            response = client.get(f"{FLIXHQ_SEARCH_URL}/{search_params}")
            soup = BeautifulSoup(response.text, "html.parser")
            items = soup.find_all("div", class_="flw-item")

        if not items:
            raise RuntimeError("No results found for query")

        results: list[str] = []
        urls: list[str] = []
        for i, item in enumerate(items[:10]):
            poster_link = item.find("div", class_="film-poster")
            detail_section = item.find("div", class_="film-detail")
            link_elem = poster_link.find("a") if poster_link else None
            title_elem = (
                detail_section.find(["h2", "h3"], class_="film-name")
                or (detail_section.find(class_="film-name") if detail_section else None)
            )

            if not link_elem and title_elem:
                link_elem = title_elem.find("a")

            if link_elem and title_elem:
                href = link_elem.get("href", "")
                title_link = title_elem.find("a")
                title = (
                    title_link.get("title")
                    or title_elem.get_text(strip=True)
                    or "Unknown Title"
                )
                info_elem = detail_section.find("div", class_="fd-infor") if detail_section else None
                year = ""
                content_type = ""
                if info_elem:
                    type_span = info_elem.find(class_="fdi-type")
                    if type_span:
                        content_type = type_span.get_text(strip=True)
                    spans = [s.get_text(strip=True) for s in info_elem.find_all("span") if s.get_text(strip=True)]
                    for s in spans:
                        if s.isdigit() and len(s) == 4:
                            year = s
                            break
                        elif s.startswith("SS "):
                            year = s
                    if not content_type:
                        for s in spans:
                            if s in ("Movie", "TV", "TV Series"):
                                content_type = s
                                break

                display_title = f"{i + 1}. {title}"
                if year:
                    display_title += f" ({year})"
                if content_type:
                    display_title += f" [{content_type}]"
                results.append(display_title)
                urls.append(urljoin(FLIXHQ_BASE_URL, href))

        if not results:
            raise RuntimeError("No results found for query")

        selected = fzf_prompt(results)
        if not selected:
            print("No media selected, exiting")
            exit(0)

        sel_str = selected[0] if isinstance(selected, list) else str(selected)
        match = re.match(r"^(\d+)\.", sel_str)
        if match:
            selected_index = int(match.group(1)) - 1
        elif sel_str in results:
            selected_index = results.index(sel_str)
        else:
            selected_index = 0

        return urls[selected_index], results[selected_index].partition(". ")[-1]

    except Exception as e:
        err_msg = f"Search failed: {e}"
        raise RuntimeError(err_msg)


def get_tv_seasons(media_id: str, client: httpx.Client) -> list[dict[str, str]]:
    try:
        seasons_url = f"{FLIXHQ_AJAX_URL}/v2/tv/seasons/{media_id}"
        response = client.get(seasons_url)
        if response.status_code == 200:
            season_pattern = re.compile(r'href="[^"]*-(\d+)"[^>]*>([^<]*)</a>')
            matches = season_pattern.findall(response.text)
            seasons = []
            for season_id, season_title in matches:
                seasons.append({"id": season_id, "title": season_title.strip()})
            return seasons
        return []
    except Exception as e:
        print(f"Failed to get TV seasons: {e}")
        return []


def get_season_episodes(season_id: str, client: httpx.Client):
    try:
        episodes_url = f"{FLIXHQ_AJAX_URL}/v2/season/episodes/{season_id}"
        response = client.get(episodes_url)
        if response.status_code == 200:
            content = response.text.replace("\n", "").replace(
                'class="nav-item"', '\nclass="nav-item"'
            )
            episode_pattern = re.compile(r'data-id="(\d+)"[^>]*title="([^"]*)"')
            matches = episode_pattern.findall(content)
            episodes = []
            for data_id, episode_title in matches:
                episodes.append({"data_id": data_id, "title": episode_title.strip()})
            return episodes
        return []
    except Exception as e:
        print(f"Failed to get season episodes: {e}")
        return []


def get_episode_servers(data_id: str, client: httpx.Client, preferred_provider: str = "Vidcloud"):
    try:
        servers_url = f"{FLIXHQ_AJAX_URL}/v2/episode/servers/{data_id}"
        response = client.get(servers_url)
        if response.status_code == 200:
            content = response.text.replace("\n", "").replace(
                'class="nav-item"', '\nclass="nav-item"'
            )
            server_pattern = re.compile(r'data-id="(\d+)"[^>]*title="([^"]*)"')
            matches = server_pattern.findall(content)
            servers = []
            for server_id, server_name in matches:
                servers.append({"id": server_id, "name": server_name.strip()})
            for server in servers:
                if preferred_provider.lower() in server["name"].lower():
                    return server["id"]
            if servers:
                return servers[0]["id"]
        return None
    except Exception as e:
        print(f"Failed to get episode servers: {e}")
        return None


def get_embed_link(episode_id: str, client: httpx.Client) -> str | None:
    try:
        sources_url = f"{FLIXHQ_AJAX_URL}/episode/sources/{episode_id}"
        response = client.get(sources_url)
        if response.status_code == 200:
            link_match = re.search(r'"link":"([^"]*)"', response.text)
            if link_match:
                embed_link = link_match.group(1)
                return embed_link
        return None
    except Exception as e:
        print(f"Failed to get embed link: {e}")
        return None


def get_episode_data(
    target_episode, season_num: int, episode_num: int, client: httpx.Client
) -> dict[str, str | int | None] | None:
    """Get stream data for a single episode"""

    episode_id = get_episode_servers(target_episode["data_id"], client, "Vidcloud")
    if episode_id is None:
        print(f"Warning: Could not get server ID for episode {episode_num}")
        return None

    embed_link = get_embed_link(episode_id, client)
    if embed_link is None:
        print(f"Warning: Could not get embed link for episode {episode_num}")
        return None

    return {
        "file": embed_link,
        "label": f"S{season_num}E{episode_num} - {target_episode['title']}",
        "type": "embed",
        "season": season_num,
        "episode": episode_num,
    }


def movie(ctx: Context):
    """Handle movie streaming"""
    assert ctx.url is not None
    try:
        response = ctx.client.get(ctx.url)
        if response.status_code != 200:
            raise RuntimeError(f"Failed to fetch movie page: HTTP {response.status_code}")

        soup = BeautifulSoup(response.text, "html.parser")
        wrapper = soup.find(id="main-wrapper") or soup.find(class_="watch_block")
        token = wrapper.get("data-token") if wrapper else None

        embed_link = None
        if token:
            ajax_res = ctx.client.post(
                f"{FLIXHQ_AJAX_URL}/ajax.php",
                data={"players": token},
                headers={"Referer": ctx.url, "X-Requested-With": "XMLHttpRequest"},
            )
            if ajax_res.status_code == 200:
                try:
                    servers = ajax_res.json()
                    if isinstance(servers, dict):
                        servers = [servers]
                    if isinstance(servers, list) and servers:
                        chosen = next(
                            (s for s in servers if "vidmoly" in s.get("name", "").lower()),
                            servers[0],
                        )
                        embed_link = chosen.get("link")
                except Exception as e:
                    print(f"Failed to parse server list: {e}")

        # Fallback to legacy FlixHQ format if token was not found
        if not embed_link:
            media_id_match = re.search(r"/(?:movie|watch-movie)/[^/]*-(\d+)", ctx.url)
            if media_id_match:
                media_id = media_id_match.group(1)
                movie_episodes_url = f"{FLIXHQ_AJAX_URL}/movie/episodes/{media_id}"
                old_resp = ctx.client.get(movie_episodes_url)
                if old_resp.status_code == 200:
                    content = old_resp.text.replace("\n", "").replace('class="nav-item"', '\nclass="nav-item"')
                    provider_pattern = re.compile(r'href="([^"]*)"[^>]*title="Vidcloud"')
                    provider_match = provider_pattern.search(content)
                    if provider_match:
                        movie_page_url = FLIXHQ_BASE_URL + provider_match.group(1)
                        episode_match = re.search(r"-(\d+)\.(\d+)$", movie_page_url)
                        if episode_match:
                            episode_id = episode_match.group(2)
                            embed_link = get_embed_link(episode_id, ctx.client)

        if not embed_link:
            raise RuntimeError("Failed to find provider for media")

        ctx.selected_media = [{"file": embed_link, "label": ctx.query, "type": "embed", "movie_title": ctx.title}]
        ctx.selected_subtitles = []
        return

    except Exception as e:
        print(f"Movie processing failed: {e}")
        exit(1)


def series(ctx: Context):
    """Handle series streaming with episode range support"""
    assert ctx.url is not None

    try:
        response = ctx.client.get(ctx.url)
        if response.status_code != 200:
            raise RuntimeError(f"Failed to fetch series page: HTTP {response.status_code}")

        soup = BeautifulSoup(response.text, "html.parser")
        seasons_dropdown = soup.find("div", class_="slt-seasons-dropdown")

        if seasons_dropdown:
            season_items = seasons_dropdown.find_all("a", class_="ss-item")
            seasons_list = []
            for item in season_items:
                pane_id = item.get("href", "").lstrip("#")
                title = item.get_text(strip=True)
                num_match = re.search(r"\d+", title)
                season_num = int(num_match.group(0)) if num_match else len(seasons_list) + 1
                seasons_list.append({"id": pane_id, "title": title, "number": season_num})

            if not seasons_list:
                raise RuntimeError("Could not find seasons on series page")

            target_season = None
            if ctx.season is not None:
                target_season = next((s for s in seasons_list if s["number"] == ctx.season), None)

            if target_season is None:
                season_titles = [s["title"] for s in seasons_list]
                selected_season = fzf_prompt(season_titles)
                if not selected_season:
                    print("No selected season, exiting")
                    exit(0)
                selected_title = selected_season[0] if isinstance(selected_season, list) else str(selected_season)
                target_season = next((s for s in seasons_list if s["title"] == selected_title), seasons_list[0])
                ctx.season = target_season["number"]

            pane = soup.find(id=target_season["id"])
            if not pane:
                raise RuntimeError(f"Could not find episode list for {target_season['title']}")

            eps_links = pane.find_all("a", class_="eps-item")
            episodes = []
            for a in eps_links:
                ep_title = a.get("title") or a.get_text(strip=True)
                ep_url = urljoin(FLIXHQ_BASE_URL, a.get("href", ""))
                m = re.search(r"s\d+-e(\d+)", ep_url, re.IGNORECASE) or re.search(r"eps?\s*(\d+)", ep_title, re.IGNORECASE)
                ep_num = int(m.group(1)) if m else len(episodes) + 1
                episodes.append({"number": ep_num, "title": ep_title, "url": ep_url})

            if not episodes:
                raise RuntimeError(f"Could not get episodes for season {ctx.season}")

            if ctx.episodes is None:
                typer.echo(f"This season has {len(episodes)} episodes")
                ctx.episodes = typer.prompt(
                    "Enter episode (e.g., '5' or '5-7' for range)", type=episode_range
                )

            assert ctx.episodes is not None
            max_episode = len(episodes)
            for ep_num in ctx.episodes:
                if ep_num > max_episode:
                    raise RuntimeError(f"Episode {ep_num} not found (only {max_episode} episodes available)")

            episodes_to_process = [ep for ep in episodes if ep["number"] in ctx.episodes]
            episode_data_list = []
            failed_episodes = []

            for ep in episodes_to_process:
                try:
                    ep_res = ctx.client.get(ep["url"])
                    if ep_res.status_code != 200:
                        failed_episodes.append(ep["number"])
                        continue
                    ep_soup = BeautifulSoup(ep_res.text, "html.parser")
                    shell = ep_soup.find(id="series-player") or ep_soup.find(class_="w_b-player")
                    ep_token = shell.get("data-token") if shell else None
                    if not ep_token:
                        failed_episodes.append(ep["number"])
                        continue

                    ajax_res = ctx.client.post(
                        f"{FLIXHQ_AJAX_URL}/ajax.php",
                        data={"players_show": ep_token},
                        headers={"Referer": ep["url"], "X-Requested-With": "XMLHttpRequest"},
                    )
                    if ajax_res.status_code != 200:
                        failed_episodes.append(ep["number"])
                        continue

                    servers = ajax_res.json()
                    if isinstance(servers, dict):
                        servers = [servers]
                    if not servers:
                        failed_episodes.append(ep["number"])
                        continue

                    chosen_server = next(
                        (s for s in servers if "vidmoly" in s.get("name", "").lower()),
                        servers[0],
                    )
                    embed_link = chosen_server.get("link")
                    if not embed_link:
                        failed_episodes.append(ep["number"])
                        continue

                    episode_data_list.append({
                        "file": embed_link,
                        "label": f"S{ctx.season}E{ep['number']} - {ep['title']}",
                        "type": "embed",
                        "season": ctx.season,
                        "episode": ep["number"],
                        "episode_title": ep["title"],
                    })
                except Exception as e:
                    print(f"Warning: Failed to fetch data for episode {ep['number']}: {e}")
                    failed_episodes.append(ep["number"])

            if not episode_data_list:
                raise RuntimeError("Could not get data for any episodes")

            if failed_episodes:
                print(f"Warning: Failed to get data for episodes: {failed_episodes}")

            ctx.selected_media = episode_data_list
            ctx.selected_subtitles = []

            if len(ctx.episodes) > 1:
                print(f"Successfully prepared {len(episode_data_list)} episodes for streaming/download")
            else:
                print(f"Successfully prepared episode {ctx.episodes[0]} for streaming/download")
            return

        # Fallback to legacy series scraping
        media_id_match = re.search(r"/(?:tv|watch-series)/[^/]*-(\d+)", ctx.url)
        if not media_id_match:
            raise RuntimeError("Could not extract media ID from URL")

        media_id = media_id_match.group(1)
        target_season_id = None
        seasons = get_tv_seasons(media_id, ctx.client)
        season_titles = [season["title"] for season in seasons]

        if not seasons:
            raise RuntimeError("Could not get seasons")

        if ctx.season is None or ctx.season > len(seasons):
            selected_season = fzf_prompt(season_titles)
            if not selected_season:
                print("No selected season, exiting")
                exit(0)
            selected_title = selected_season[0] if isinstance(selected_season, list) else str(selected_season)
            for season_data in seasons:
                season_title = season_data["title"]
                if season_title == selected_title:
                    target_season_id = season_data["id"]
                    possible_separators = [" ", "-", "_"]
                    for sep in possible_separators:
                        if sep in season_title:
                            season_no = float(season_title[season_title.find(sep) + 1 :])
                            ctx.season = int(season_no)
                            target_season_id = season_data["id"]
                            break
        else:
            target_season_id = seasons[ctx.season - 1]["id"]

        assert ctx.season is not None

        episodes = get_season_episodes(target_season_id, ctx.client)
        if ctx.episodes is None:
            typer.echo(f"This season has {len(episodes)} episodes")
            ctx.episodes = typer.prompt(
                "Enter episode (e.g., '5' or '5-7' for range)", type=episode_range
            )

        assert ctx.episodes is not None

        if not episodes:
            raise RuntimeError(f"Could not get episodes for season {ctx.season}")

        max_episode = len(episodes)
        for ep_num in ctx.episodes:
            if ep_num > max_episode:
                err_msg = f"Episode {ep_num} not found (only {max_episode} episodes available)"
                raise RuntimeError(err_msg)

        episode_data_list = []
        failed_episodes = []
        for episode_num in ctx.episodes:
            target_episode = episodes[episode_num - 1]
            episode_data = get_episode_data(target_episode, ctx.season, episode_num, ctx.client)
            if episode_data:
                episode_data_list.append(episode_data)
            else:
                failed_episodes.append(episode_num)

        if not episode_data_list:
            raise RuntimeError("Could not get data for any episodes")

        if failed_episodes:
            print(f"Warning: Failed to get data for episodes: {failed_episodes}")

        ctx.selected_media = episode_data_list
        ctx.selected_subtitles = []

        if len(ctx.episodes) > 1:
            print(f"Successfully prepared {len(episode_data_list)} episodes for streaming/download")
        else:
            print(f"Successfully prepared episode {ctx.episodes[0]} for streaming/download")

    except Exception as e:
        print(f"Series processing failed: {e}")
        exit(1)


def get_id(ctx: Context) -> tuple[str, str, MediaType | None]:
    """Search and select content"""
    assert ctx.query is not None
    selected_url, title = search_content(ctx.query, ctx.client)

    if "/movie/" in selected_url or "/watch-movie/" in selected_url:
        content_type = MediaType.MOVIE
    elif "/tv/" in selected_url or "/watch-series/" in selected_url:
        content_type = MediaType.SERIES
    else:
        content_type = None
    return (selected_url, title, content_type)


def get_content_type(ctx: Context):
    """Choose content type"""
    if ctx.content_type is None:
        choice = fzf_prompt(["movie", "series"])
        if isinstance(choice, list):
            choice = choice[0] if choice else ""
        if choice == "movie":
            ctx.content_type = MediaType.MOVIE
        elif choice == "series":
            ctx.content_type = MediaType.SERIES
        else:
            exit(0)


def dl_data(ctx: Context) -> None:
    """Download media with support for episode ranges"""
    if ctx.selected_media:
        episodes_to_download = (
            ctx.selected_media if isinstance(ctx.selected_media, list) else [ctx.selected_media]
        )
        print(f"Starting download of {len(episodes_to_download)} episode(s)...")
        for i, episode_data in enumerate(episodes_to_download, 1):
            print(f"\nDownloading episode {i}/{len(episodes_to_download)}: {episode_data['label']}")
            try:
                decoded_url, subs = decrypt_stream_url(episode_data["file"])
                subs = subs if subs else []
                if "season" in episode_data and "episode" in episode_data:
                    episode_query = (
                        f"{ctx.query}_S{episode_data['season']:02d}E{episode_data['episode']:02d}"
                    )
                else:
                    episode_query = f"{ctx.query}_Episode_{i}"

                if decoded_url is None:
                    raise RuntimeError("unable to find url for episode")

                download(ctx.dl_path, episode_query, decoded_url, FLIXHQ_BASE_URL, subs)
                print(f"Successfully downloaded: {episode_data['label']}")
            except Exception as e:
                print(f"Failed to download episode {i}: {e}")
                continue
        print(f"\nDownload completed for {len(episodes_to_download)} episode(s)")
    else:
        print("No media selected for download")


def provide_data(ctx: Context) -> None:
    """Play media with support for episode ranges"""
    if ctx.selected_media:
        episodes_to_play = (
            ctx.selected_media if isinstance(ctx.selected_media, list) else [ctx.selected_media]
        )
        if ctx.content_type == MediaType.MOVIE:
            print(f"Starting playback of {ctx.title}...")
        else:
            print(f"Starting playback of {len(episodes_to_play)} episode(s)...")
        for i, episode_data in enumerate(episodes_to_play, 1):
            if ctx.content_type == MediaType.SERIES:
                print(f"\nPlaying episode {i}/{len(episodes_to_play)}: {episode_data['label']}")
            try:
                decoded_url, subs = decrypt_stream_url(episode_data["file"])
                if decoded_url is None:
                    raise RuntimeError(f"Failed to get url for episode {i}")
                subs = subs if subs else []

                if "episode_title" in episode_data:
                    episode_title = episode_data["episode_title"]
                elif "movie_title" in episode_data:
                    episode_title = episode_data["movie_title"]
                else:
                    episode_title = episode_data["label"]

                if ctx.play_type == "play":
                    play(decoded_url, episode_title, FLIXHQ_BASE_URL, subs)
                elif ctx.play_type == "cast":
                    cast(decoded_url, subs)
                if len(episodes_to_play) > 1 and i < len(episodes_to_play):
                    continue_choice = typer.confirm("Continue to next episode?")
                    if not continue_choice:
                        print("Stopping playback")
                        break
            except Exception as e:
                print(f"Failed to play episode {i}: {e}")
                if len(episodes_to_play) > 1:
                    continue_choice = typer.confirm("Continue to next episode?")
                    if not continue_choice:
                        print("Stopping playback")
                        break
                else:
                    break
    else:
        print("No media selected for playback")


app = typer.Typer()


# ruff: noqa: UP045 - allow using Optional[T] instead T | None
# ruff: noqa: UP006 - allow using typing.List
@app.command()
def main(
    query: Annotated[Optional[List[str]], typer.Argument(help="The name to search for")] = None,
    action: Annotated[
        Action,
        typer.Option(
            "--action",
            "-a",
            help="Type of playback",
        ),
    ] = Action.PLAY,
    season: Annotated[
        Optional[int], typer.Option("--season", "-s", help="Specify season number")
    ] = None,
    episodes: Annotated[
        Optional[range],
        typer.Option(
            "--episodes",
            "-e",
            help="Specify episode/range of episodes to download",
            parser=episode_range,
        ),
    ] = None,
):
    headers = {
        "User-Agent": f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 flix-cli/{__core__}",
        "Referer": f"{FLIXHQ_BASE_URL}/",
        "X-Requested-With": "XMLHttpRequest",
    }
    client = httpx.Client(headers=headers, follow_redirects=True, timeout=15)

    ctx = Context(client=client)

    if query is None:
        ctx.query = typer.prompt("Search")
    else:
        ctx.query = " ".join(query)

    ctx.play_type = action
    ctx.url, ctx.title, ctx.content_type = get_id(ctx)

    if ctx.content_type is None:
        get_content_type(ctx)

    if ctx.content_type == MediaType.MOVIE:
        movie(ctx)
    else:
        if ctx.content_type != MediaType.SERIES:
            if any((season, episodes)):
                print("Warning: content type is not 'series', ignoring season/episode parameters")
        else:
            if episodes:
                ctx.episodes = episodes
            if season:
                ctx.season = season

        series(ctx)

    if action in ("play", "cast"):
        provide_data(ctx)
    elif action == "download":
        dl_data(ctx)


if __name__ == "__main__":
    app()

