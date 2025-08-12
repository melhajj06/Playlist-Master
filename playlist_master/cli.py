import click
from .downloader import download_playlist

@click.group("playlist-master")
def cli():
    pass


@cli.command()
@click.option(
    "-c", "--config",
    type=click.File('r'),
    help="A path to a config file to be used by the program. Options and flags passed into the CLI while a config is specified will take precedence over the options in the config."
)
@click.option(
    "-p", "--platform",
    type=click.Choice(["spotify", "youtube"], case_sensitive=False),
    help="The platform from which to download the playlist."
)
@click.option(
    "-q", "--thumbnail-quality",
    "thumbnail_quality",
    type=click.Choice(["default", "medium", "high", "standard", "maxres"], case_sensitive=False),
    help="The quality of the thumbnail to download from YouTube."
)
@click.option(
    "-g", "--genlogs",
    is_flag=True,
    help="Whether to generate logs in a file or directly in the terminal."
)
@click.option(
    "-l", "--logdir",
    type=click.Path(file_okay=False),
    help="The directory in which to generate the log files. If `genlogs` is false, the value of this option is ignored."
)
@click.option(
    "-e", "--log-level",
    "log_level",
    type=click.Choice(["notset", "info", "warning", "error", "critical", "debug"], case_sensitive=False),
    help="The level at which to log messages."
)
@click.option(
    "-d", "--yt-dlp",
    "yt_dlp",
    help="A string of command line options and flags to be used by yt-dlp."
)
@click.option(
    "-y", "--yt-oauth",
    "yt_oauth",
    nargs=2,
    help="A client id and client secret used for Google's OAuth."
)
@click.option(
    "-s", "--sp-oauth",
    "sp_oauth",
    nargs=2,
    help="A client id and client secret used for Spotify's OAuth."
)
@click.argument("playlist_id")
def download(config, platform, thumbnail_quality, genlogs, logdir, loglevel, yt_dlp, yt_oauth, sp_oauth, playlist_id=None):
    download_playlist(
        config_path=config,
        platform=platform,
        thumbnail_quality=thumbnail_quality,
        genlogs=genlogs,
        logdir=logdir,
        loglevel=loglevel,
        yt_dlp=yt_dlp,
        yt_oauth=({"client_id": yt_oauth[0], "client_secret": yt_oauth[1]} if yt_oauth else None),
        sp_oauth=({"client_id": sp_oauth[0], "client_secret": sp_oauth[1]} if sp_oauth else None),
        playlist_id=playlist_id
    )