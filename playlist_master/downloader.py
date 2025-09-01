# python standard library dependencies
import os
import logging
import shlex
import tomllib
import datetime as dt
from logging import Logger
from urllib.request import urlopen
from enum import Enum
from typing import Any

# external dependencies
import yt_dlp as yt
import ytmusicapi as ytm
import music_tag
import spotipy as sp
from spotipy.oauth2 import SpotifyClientCredentials
from ytmusicapi import YTMusic

# TODO:
# - output logs to console if `genlogs` is false
# - integrate thumbnail quality option for spotify as well


# default log output directory
LOG_DEFAULT_DIR = r"./log"


class ThumbnailQuality(Enum):
    """An enumeration representing thumbnail qualities to interface with the Youtube Data API V3
    """

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
    """A class representing a song/track
    """

    def __init__(self, artists: list[str], album_artists: list[str], title: str, album_title: str, release_date: str, art_url: str, track_number: int, total_tracks: int, disc_number: int, explicit: bool = False):
        r"""Creates a new ``Track`` object

        :param list[str] artists: the artists of the track
        :param list[str] album_artists: the artists of the album the track belongs to
        :param str title: the title of the track
        :param str album_title: the title of the album the track belongs to
        :param str release_date: the release date in the form 'yyyy-mm-dd'
        :param str art_url: the url of the album's (or song's) cover art
        :param int track_number: the track number in the album
        :param int total_tracks: the total number of tracks in the album
        :param int disc_number: the disc number the track belongs to
        :param bool explicit: whether the track contains profanity or is considered 'explicit', defaults to False
        """

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
    
def get_spotify_track_info(track: dict[str, Any], logger: Logger = None) -> Track | None:
    r"""Creates a new ``Track`` object from a Spotify Web API request retrieving a track

    :param dict[str, Any] track: a Spotify track dictionary
    :param Logger logger: a logger, defaults to None
    :return Track | None: a new ``Track`` object
    """

    try:
        album = track["album"]
        return Track(
            [artist["name"] for artist in track["artists"]],
            ["Various Artists"] if album["album_type"] == "compilation" else [artist["name"] for artist in album["artists"]],
            track["name"],
            None if album["album_type"] == "single" else album["name"],
            format_date(album["release_date"]),
            album["images"][0]["url"] if album["images"] else None,
            track["track_number"],
            album["total_tracks"],
            track["disc_number"],
            track["explicit"]
        )
    except Exception as e:
        if logger:
            logger.error(e, stack_info=True, exc_info=True)
            logger.error("could not retrieve track info for track: %s", track)
        return None
    
def get_youtube_track_info(track: dict[str, Any], thumbnail_quality: int, album: dict[str, Any], logger: Logger = None) -> Track | None:
    r"""Creates a new ``Track`` object from a Youtube Data API V3 request retrieving a track

    :param dict[str, Any] track: a Youtube track dictionary
    :param int thumbnail_quality: the desired thumbnail quality
    :param dict[str, Any] album: a Youtube album dictionary
    :param Logger logger: a logger, defaults to None
    :return Track | None: a new ``Track`` object
    """

    try:
        tl = len(track["thumbnails"])

        # it's worth noting that sometimes the track's video id doesn't match the one in the retrieved album
        # it doesn't make much sense but that's how it is
        track_misc_info = None if not album else list(filter(lambda t: t["videoId"] == track["videoId"], album["tracks"]))
        if track_misc_info and len(track_misc_info) == 0:
            track_misc_info = None

        # disc number is always `None` since the Youtube API doesn't have that information
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

def format_date(date: str) -> str:
    r"""Gets the year of a date in the format 'yyy-mm-dd'

    :param str date: a date
    :return str: the year of ``date``
    """
    return None if date is None else date.split('-')[0]


def download_playlist(config_path: str, **kwargs: dict[str, Any]):
    """Downloads a playlist given command line arguments and/or a config file

    :param str config_path: the path to a config file
    """

    opts: dict[str, str | int | bool | dict[str, Any]] = {}

    # parse config file or create default dictionary if none was supplied
    if not config_path or not os.path.exists(config_path):
        opts["playlist-master"] = None
        opts["yt-dlp"] = None
        opts["yt-oauth"] = None
        opts["sp-oauth"] = None
    else:
        with open(config_path, "rb") as config:
            opts = tomllib.load(config)

    # cache oauth information so it doesn't get lost
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

    # parse command line arguments
    # command line arguments always take precedence over config arguments
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
    
    # initialize logger
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

    # restore cached oauth information if none were supplied in the command line arguments,
    # or stop execution if no oauth information were supplied at all
    if not opts["yt-oauth"]:
        if temp_client and temp_secret:
            opts["yt-oauth"] = ytm.setup_oauth(temp_client, temp_secret, open_browser=True)
        elif temp_cookie_headers:
            opts["yt-oauth"] = temp_cookie_headers
        else:
            logger.error("no youtube authentication credentials provided")
            return
    
    # download from the respective platform
    platform = opts["playlist-master"]["platform"].lower()
    if platform == "spotify":
        download_spotify_playlist(opts["playlist-master"]["playlist_id"], opts, logger)
    elif platform == "youtube":
        download_youtube_playlist(opts["playlist-master"]["playlist_id"], opts, logger)


def download_spotify_playlist(playlist_id: str, config: dict[str, str | int | bool | dict[str, Any]], logger: Logger):
    """Downloads a playlist from Spotify

    :param str playlistID: a playlist id
    :param dict[str, str  |  int  |  bool  |  dict[str, Any]] config: a dictionary containing options and oauth info
    :param Logger logger: a logger
    """

    # initialize credentials and yt-dlp options for downloading
    ytauth = YTMusic(config["yt-oauth"])
    spauth = config["sp-oauth"]
    ytdlp_options = yt.parse_options(shlex.split(config["yt-dlp"]["options"])).ydl_opts
    ytdlp_options["logger"] = YtDlpLogger(logger)

    # cache for keeping track of downloaded files to apply metadata afterwards
    outputs = []
    
    tracks = list(map(lambda track: get_spotify_track_info(track["track"]), get_spotify_tracks(playlist_id, spauth)))
    for track in tracks:
        if not track:
            logger.error("unable to retrieve track")
            continue
            
        # search for the track on Youtube by artist and track name
        try:
            logger.info(f"searching for: {track.artists[0] if track.artists[0] else "NoneType"} {track.title if track.title else "NoneType"}")
            url = search_yt(track.title, track.artists[0], ytauth, track.explicit)

            if url is None:
                logger.info(f"no results for: {track.artists[0] if track.artists[0] else "NoneType"} {track.title if track.title else "NoneType"}")
                continue
        except Exception as e:
            logger.error("exception occurred while retrieving url for %s", track)
            logger.error(e, stack_info=True, exc_info=True)
            continue
        
        # if sorting is enabled, the output directory specified in the yt-dlp options needs to be modified
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

        # apply metadata
        m = music_tag.load_file(outputs[-1])
        r = apply_metadata(m, track, logger)
        if r:
            logger.info("applied metadata")
        else:
            logger.warning("unable to apply metadata")


def download_youtube_playlist(playlist_id: str, config: dict[str, str | int | bool | dict[str, Any]], logger: Logger):
    """Downloads a playlist from Youtube

    :param str playlistID: a playlist id
    :param dict[str, str  |  int  |  bool  |  dict[str, Any]] config: a dictionary containing options and oauth info
    :param Logger logger: a logger
    """

    # initialize credentials and yt-dlp options for downloading
    ytauth = YTMusic(config["yt-oauth"])
    ytdlp_options = yt.parse_options(shlex.split(config["yt-dlp"]["options"])).ydl_opts
    ytdlp_options["logger"] = YtDlpLogger(logger)

    # cache for keeping track of downloaded files to apply metadata afterwards
    outputs = []

    tracks = get_yt_tracks(playlist_id, ytauth)
    for track in tracks:
        # if playlistID is a valid playlist id, then no track should be `None` (i.e. all returned tracks will have a url)
        track_info = get_youtube_track_info(track, ThumbnailQuality[config["playlist-master"]["thumbnail_quality"].upper()].value if "thumbnail_quality" in config["playlist-master"] else 0, ytauth.get_album(track["album"]["id"]) if track["album"] else None, logger)
        url = f"https://music.youtube.com/watch?v={track["videoId"]}"
        logger.info("downloading from url: %s", url)

        # if sorting is enabled, the output directory specified in the yt-dlp options needs to be modified
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
        
        # apply metadata
        m = music_tag.load_file(outputs[-1])
        r = apply_metadata(m, track_info, logger)
        if r:
            logger.info("applied metadata")
        else:
            logger.warning("unable to apply metadata")


def get_spotify_tracks(playlist_id: str, credentials: dict[str, str]) -> dict[str, Any]:
    """Gets the individual tracks from a Spotify playlist

    :param str playlistID: a playlist id
    :param dict[str, str] credentials: a dictionary containing oauth info
    :return dict[str, Any]: a list containing all track dictionaries as they are in a Spotify Web API response
    """

    # initialize credentials for requesting from Spotify Web API
    client_credentials_manager = SpotifyClientCredentials(credentials["client_id"], credentials["client_secret"])
    spotify = sp.Spotify(client_credentials_manager=client_credentials_manager)
    results = spotify.playlist_items(playlist_id=playlist_id, limit=None)

    if not results:
        return []

    # in case the response is limited, all tracks will be retrieved
    tracks = results["items"]
    while results["next"]:
        results = spotify.next(results)
        tracks.extend(results["items"])

    return tracks


def get_yt_tracks(playlist_id: str, credentials: YTMusic) -> list[dict[str, Any]]:
    r"""Gets the individual tracks from a Youtube playlist

    :param str playlistID: a playlist id
    :param YTMusic credentials: an authenticated ``YTMusic`` object
    :return list[dict[str, Any]]: a list of track dictionaries as they are in a Youtube Data API V3 response
    """

    return credentials.get_playlist(playlist_id, limit=None)["tracks"]


def search_yt(artist: str, track_name: str, credentials: YTMusic, explicit: bool = False) -> str | None:
    r"""Searches for a track given the artist and the track name

    :param str artist: the name of the artist of the track
    :param str song_name: the name of the track
    :param YTMusic credentials: an authenticated ``YTMusic`` object
    :param bool explicit: whether the track contains profanity or is considered 'explicit', defaults to False
    :return str | None: the url of the track
    """

    search = f"{artist} {track_name} explicit" if explicit else f"{artist} {track_name}"
    song = credentials.search(search, filter='songs', limit=1)
    if song.count == 0:
        return None

    return f"https://music.youtube.com/watch?v={song[0]['videoId']}"


def download(url: str, options: dict[str, Any], output: list[str]):
    r"""Downloads a track from Youtube at ``url``

    :param str url: the url of the track
    :param dict[str, Any] options: yt-dlp options
    :param list[str] output: a list to append the downloaded file's path to
    """

    with yt.YoutubeDL(options) as ytdl:
        ytdl.add_post_hook(lambda p: output.append(p))
        ytdl.download(url)


def apply_metadata(file: Any, metadata: Track, logger: Logger) -> bool:
    """Applies metadata to an audio file

    :param Any file: an object returned from ``music_tag.load_file()``
    :param Track metadata: a ``Track`` object
    :param Logger logger: a logger
    :return bool: whether the metadata was successfully applied or not
    """

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
        return True
    except Exception as e:
        logger.error("exception occurred while applying metadata")
        logger.error(e, stack_info=True, exc_info=True)
        return False