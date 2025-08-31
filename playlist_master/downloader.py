# python standard library dependencies
import os
import logging
import shlex
import tomllib
import datetime as dt
from logging import Logger
from urllib.request import urlopen
from enum import Enum

# external dependencies
import yt_dlp as yt
import ytmusicapi as ytm
import music_tag
import spotipy as sp
from spotipy.oauth2 import SpotifyClientCredentials
from ytmusicapi import YTMusic

# TODO:
# - docs
# - integrate music output dir option
# - add options for creating directories automatically
# - dont create config if none exists

# default paths
CONFIG_DEFAULT_PATH = r"./config.toml"
LOG_DEFAULT_DIR = r"./log"
OUTPUT_DEFAULT_DIR = r"./music"

class ThumbnailQuality(Enum):
    DEFAULT = 0
    MEDIUM = 1
    HIGH = 2
    STANDARD = 3
    MAXRES = 4


class YtDlpLogger:
    """A logger object to be used by yt-dlp
    """
    def __init__(self, logger: Logger):
        r"""Creates a new ``YtDlpLogger object

        :param Logger logger: a ``Logger`` object that will be the actual logger
        """
        self.logger = logger

    def debug(self, msg: str):
        """Logs a debug message

        :param str msg: the message to log
        """

        # For compatibility with youtube-dl, both debug and info are passed into debug
        # You can distinguish them by the prefix '[debug] '
        if msg.startswith('[debug] '):
            pass
        else:
            self.info(msg)

        self.logger.debug(msg)

    def info(self, msg: str):
        """Logs an info message

        :param str msg: the message to log
        """

        self.logger.info(msg)

    def warning(self, msg: str):
        """Logs a warning message

        :param str msg: the message to log
        """

        self.logger.warning(msg)

    def error(self, msg: str):
        """Logs an error message

        :param str msg: the message to log
        """

        self.logger.error(msg)


class Track:
    def __init__(self, artists, album_artists, title, album_title, release_date, art_url, track_number, total_tracks, disc_number, explicit=False):
        self.artists = artists
        self.album_artists = album_artists
        self.title = title
        self.album_title = album_title
        self.release_date = release_date
        self.art_url = art_url
        self.track_number = track_number
        self.total_tracks = total_tracks
        self.disc_number = disc_number
        self.explicit = explicit
    
    @staticmethod
    def get_spotify_track_info(track, logger=None):
        try:
            album = track["album"]
            return Track(
                [artist["name"] for artist in track["artists"]],
                ["Various Artists"] if album["album_type"] == "compilation" else [artist["name"] for artist in album["artists"]],
                track["name"],
                None if album["album_type"] == "single" else album["name"],
                Track.format_date(album["release_date"], album["release_date_precision"]),
                album["images"][0]["url"] if album["images"] else None,
                track["track_number"],
                album["total_tracks"],
                track["disc_number"],
                album["explicit"]
            )
        except Exception as e:
            if logger:
                logger.error(e, stack_info=True, exc_info=True)
                logger.error("could not retrieve track info for track: %s", track)
            return None
        
    @staticmethod
    def get_youtube_track_info(track, thumbnail_quality, album, logger=None):
        try:
            tl = len(track["thumbnails"]) 
            track_misc_info = None if not album else list(filter(lambda t: t["videoId"] == track["videoId"], album["tracks"]))
            if track_misc_info and len(track_misc_info) == 0:
                track_misc_info = None
            return Track(
                [artist["name"] for artist in track["artists"]],
                [track["artists"][0]["name"]] if not album else [artist["name"] for artist in album["artists"]],
                track["title"],
                "Singles" if not album else album["title"],
                None if not album else album["year"],
                track["thumbnails"][min(tl - 1, thumbnail_quality)]["url"],
                None if not track_misc_info else track_misc_info["trackNumber"],
                None if not album else album["trackCount"],
                None,
                track["isExplicit"]
            )
        except Exception as e:
            if logger:
                logger.error(e, stack_info=True, exc_info=True)
                logger.error("could not retrieve track info for track: %s", track)
            return None

    @staticmethod
    def format_date(date: str):
        return None if date is None else date.split('-')[0]


def download_playlist(config_path, **kwargs):
    opts: dict[str: str | int | bool | dict] = {}

    if not config_path or not os.path.exists(config_path):
        opts["playlist-master"] = None
        opts["yt-dlp"] = None
        opts["yt-oauth"] = None
        opts["sp-oauth"] = None
    else:
        with open(config_path, "rb") as config:
            opts = tomllib.load(config)

    temp_client = None
    temp_secret = None
    temp_cookie_headers = None
    if opts["yt-oauth"]:
        if "cookie_headers" in opts["playlist-master"] and "cookie_headers_path" in opts["yt-oauth"]:
            temp_cookie_headers = opts["yt-oauth"]["cookie_headers_path"]
        elif "client_id" in opts["yt-oauth"] and "client_secret" in opts["yt-oauth"]:
            temp_client = opts["yt-oauth"]["client_id"]
            temp_secret = opts["yt-oauth"]["client_secret"]
        opts["yt-oauth"] = None

    for key, value in kwargs.items():
        if not value:
            continue

        if key == "yt_dlp":
            opts["yt-dlp"]["options"] = value
        elif key == "yt_oauth":
            credentials = None
            if kwargs["cookie_headers"]:
                credentials = value
            else:
                credentials = ytm.setup_oauth(value["client_id"], value["client_secret"])
            opts["yt-oauth"] = credentials
        elif key == ["sp_oauth"]:
            opts["sp-oauth"] = value
        else:
            opts["playlist-master"][key] = value
    
    logdir = LOG_DEFAULT_DIR
    if "logdir" in opts["playlist-master"]:
        logdir = opts["playlist-master"]["logdir"]

    loglevel = logging.INFO
    if "loglevel" in opts["playlist-master"]:
        loglevel = opts["playlist-master"]["loglevel"]

    logger = logging.getLogger(__name__)
    date = dt.datetime.now().date().strftime(r"%Y-%m-%d")
    time = dt.datetime.now().time().strftime(r"%H-%M-%S")
    filename = os.path.join(logdir, f"{date}_{time}_playlist-master.log")
    logging.basicConfig(filename=(filename if opts["playlist-master"]["genlogs"] else None), encoding="utf-8", filemode='w', format="%(asctime)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S (%Z)", level=loglevel)

    if not opts["yt-oauth"]:
        if temp_client and temp_secret:
            opts["yt-oauth"] = ytm.setup_oauth(temp_client, temp_secret, open_browser=True)
        elif temp_cookie_headers:
            opts["yt-oauth"] = temp_cookie_headers
        else:
            logger.error("no youtube authentication credentials provided")
            return
        
    platform = opts["playlist-master"]["platform"].lower()
    if platform == "spotify":
        download_spotify_playlist(opts["playlist-master"]["playlist_id"], opts, logger)
    elif platform == "youtube":
        download_youtube_playlist(opts["playlist-master"]["playlist_id"], opts, logger)


def download_spotify_playlist(playlistID, config, logger):
    ytauth = YTMusic(config["yt-oauth"])
    spauth = config["sp-oauth"]
    ytdlp_options = yt.parse_options(shlex.split(config["yt-dlp"]["options"])).ydl_opts
    ytdlp_options["logger"] = YtDlpLogger(logger)
    outputs = []
        
    tracks = list(map(lambda track: Track.get_spotify_track_info(track["track"]), get_spotify_tracks(playlistID, spauth)))
    for track in tracks:
        if not track:
            logger.error("unable to retrieve track")
            continue

        try:
            logger.info(f"searching for: {track.artists[0] if track.artists[0] else "NoneType"} {track.title if track.title else "NoneType"}")
            url = search_yt(track.title, track.artists[0], ytauth)

            if url is None:
                logger.info(f"no results for: {track.artists[0] if track.artists[0] else "NoneType"} {track.title if track.title else "NoneType"}")
                continue
        except Exception as e:
            logger.error("exception occurred while retrieving url for %s", track)
            logger.error(e, stack_info=True, exc_info=True)
            continue
        
        if config["playlist-master"]["sort"] and ytdlp_options["outtmpl"]:
            out = ytdlp_options["outtmpl"]["default"]
            i = 0
            if '/' in out:
                i = out.rindex('/') + 1
            elif '\\' in out:
                i = out.rindex('\\') + 1

            out = out[:i] + f"{track.artists[0]}/{track.album_title if track.album_title else "Singles"}/" + out[i:]
            ytdlp_options["outtmpl"]["default"] = out

        logger.info("downloading from url: %s", url)
        download(url, ytdlp_options, outputs)
        
        if not outputs[-1]:
            logger.warning("unable to apply metadata")
            continue

        m = music_tag.load_file(outputs[-1])
        r = apply_metadata(m, track, logger)
        if r:
            logger.info("applied metadata")
        else:
            logger.warning("unable to apply metadata")


def download_youtube_playlist(playlistID, config, logger):
    ytauth = YTMusic(config["yt-oauth"])
    ytdlp_options = yt.parse_options(shlex.split(config["yt-dlp"]["options"])).ydl_opts
    ytdlp_options["logger"] = YtDlpLogger(logger)
    outputs = []

    tracks = get_yt_tracks(playlistID, ytauth)
    for track in tracks:
        track_info = Track.get_youtube_track_info(track, ThumbnailQuality[config["playlist-master"]["thumbnail_quality"].upper()].value if "thumbnail_quality" in config["playlist-master"] else 0, ytauth.get_album(track["album"]["id"]) if track["album"] else None, logger)
        url = f"https://music.youtube.com/watch?v={track["videoId"]}"
        logger.info("downloading from url: %s", url)

        if config["playlist-master"]["sort"] and ytdlp_options["outtmpl"]:
            out = ytdlp_options["outtmpl"]["default"]
            i = 0
            if '/' in out:
                i = out.rindex('/') + 1
            elif '\\' in out:
                i = out.rindex('\\') + 1

            out = out[:i] + f"{track_info.artists[0]}/{track_info.album_title if track_info.album_title else "Singles"}/" + out[i:]
            ytdlp_options["outtmpl"]["default"] = out

        download(url, ytdlp_options, outputs)
        if not outputs[-1]:
            logger.warning("unable to apply metadata")
            continue
        
        m = music_tag.load_file(outputs[-1])
        r = apply_metadata(m, track_info, logger)
        if r:
            logger.info("applied metadata")
        else:
            logger.warning("unable to apply metadata")


def get_spotify_tracks(playlistID, credentials):
    client_credentials_manager = SpotifyClientCredentials(credentials["client_id"], credentials["client_secret"])
    spotify = sp.Spotify(client_credentials_manager=client_credentials_manager)
    results = spotify.playlist_items(playlist_id=playlistID)

    if not results:
        return []

    tracks = results["items"]
    while results["next"]:
        results = spotify.next(results)
        tracks.extend(results["items"])

    return tracks


def get_yt_tracks(playlistID, credentials: YTMusic):
    return credentials.get_playlist(playlistID, limit=None)["tracks"]


def search_yt(artist, song_name, ytauth, explicit=False):
    search = f"{artist} {song_name} explicit" if explicit else f"{artist} {song_name}"
    song = ytauth.search(search, filter='songs', limit=1)
    if song.count == 0:
        return None

    return f"https://music.youtube.com/watch?v={song[0]['videoId']}"


def download(url, options, output: list[str]):
    with yt.YoutubeDL(options) as ytdl:
        ytdl.add_post_hook(lambda p: output.append(p))
        ytdl.download(url)


def apply_metadata(file, metadata, logger):
    try:
        file["tracktitle"] = metadata.title
        file["artist"] = "; ".join(metadata.artists)
        file["albumartist"] = "; ".join(metadata.album_artists)
        if metadata.album_title:
            file["album"] = metadata.album_title
        file["year"] = metadata.release_date
        file["artwork"] = urlopen(metadata.art_url).read()
        if metadata.disc_number:
            file["discnumber"] = metadata.disc_number
        if metadata.track_number:
            file["tracknumber"] = metadata.track_number
        if metadata.total_tracks:
            file["totaltracks"] = metadata.total_tracks
        file.save()
        return 1
    except Exception as e:
        logger.error("exception occurred while applying metadata")
        logger.error(e, stack_info=True, exc_info=True)
        return 0