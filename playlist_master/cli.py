import click
from .downloader import download_playlist
import os

@click.group("playlist-master")
def cli():
    pass


@cli.command()
@click.argument(
    "playlist_id",
    required=False,
    nargs=1
)
@click.option(
    "-c", "--config",
    type=click.Path(file_okay=True, dir_okay=False, exists=True),
    help="A path to a config file to be used by the program. Options and flags passed into the CLI while a config is specified will take precedence over the options in the config."
)
@click.option(
    "-p", "--platform",
    type=click.Choice(["spotify", "youtube"], case_sensitive=False),
    help="The platform from which to download the playlist."
)
@click.option(
    "-r", "--sort",
    is_flag=True,
    default=False,
    help="Whether to sort the output files by artist and album."
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
    default=True,
    help="Whether to generate logs in a file or directly in the terminal."
)
@click.option(
    "-l", "--logdir",
    type=click.Path(file_okay=False),
    help="The directory in which to generate the log files. If `genlogs` is false, the value of this option is ignored."
)
@click.option(
    "-e", "--log-level",
    "loglevel",
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
    help="A client id and client secret used for Google's OAuth separated by a comma. If the `-k`/`--cookie-headers` flag is specified, a .json filepath containing the exported headers is used as the option's parameter."
)
@click.option(
    "-s", "--sp-oauth",
    "sp_oauth",
    nargs=2,
    help="A client id and client secret used for Spotify's OAuth."
)
@click.option(
    "-k", "--cookie-headers",
    "cookie_headers",
    is_flag=True,
    help="Whether to use exported headers from a browser to authenticate for Google's OAuth or client keys."
)
def download(playlist_id, config, platform, thumbnail_quality, genlogs, logdir, loglevel, yt_dlp, yt_oauth, sp_oauth, cookie_headers, sort):
    yauth = None

    if yt_oauth:
        if cookie_headers:
            if ',' in yt_oauth:
                raise click.BadParameter("yt-oauth option with cookie-headers flag must be a file path with no commas")
            
            if os.path.exists(yt_oauth):
                if not os.path.isfile(yt_oauth):
                    raise click.BadParameter(f"File: '{yt_oauth}' is not a file")
            else:
                raise click.BadParameter(f"File: '{yt_oauth}' does not exist")
            
            yauth = yt_oauth
        else:
            if ',' not in yt_oauth:
                raise click.BadParameter("yt-oauth option must have 2 values separated by a comma with no space")
            
            keys = yt_oauth.split(',')
            yauth = {"client_id": keys[0], "client_secret": keys[1]}
    
    download_playlist(
        config_path=str(config) if config else None,
        platform=platform,
        thumbnail_quality=thumbnail_quality,
        genlogs=genlogs,
        logdir=logdir,
        loglevel=loglevel,
        yt_dlp=yt_dlp,
        yt_oauth=yauth,
        sp_oauth=({"client_id": sp_oauth[0], "client_secret": sp_oauth[1]} if sp_oauth else None),
        playlist_id=playlist_id,
        cookie_headers=cookie_headers,
        sort=sort
    )