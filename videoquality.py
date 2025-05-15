from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
from yt_dlp.utils import ExtractorError, DownloadError
import logging
import os
import json
import tempfile
import random
import time
import re
import requests

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_video_qualities(video_url, max_retries=3):
    try:
        # List of common user agents
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'
        ]

        for attempt in range(max_retries):
            try:
                ydl_opts = {
                    'listformats': True,
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': False,
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                    'nocheckcertificate': True,
                    'ignoreerrors': True,
                    'no_color': True,
                    'geo_bypass': True,
                    'socket_timeout': 30,
                    'retries': 10,
                    'fragment_retries': 10,
                    'skip_download': True,
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['android', 'web'],
                            'player_skip': ['webpage', 'configs'],
                        }
                    },
                    'http_headers': {
                        'User-Agent': random.choice(user_agents),
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                        'Cache-Control': 'max-age=0',
                        'TE': 'trailers'
                    }
                }
                
                logger.info(f"Attempt {attempt + 1}/{max_retries} to extract video info")
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    logger.info(f"Attempting to extract info for URL: {video_url}")
                    
                    # Try different extraction methods
                    try:
                        # First try with default options
                        info_dict = ydl.extract_info(video_url, download=False)
                    except Exception as e:
                        logger.warning(f"First extraction method failed: {str(e)}")
                        try:
                            # Try with minimal options
                            ydl_opts['extractor_args']['youtube']['player_client'] = ['android']
                            ydl_opts['extractor_args']['youtube']['player_skip'] = ['webpage']
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                                info_dict = ydl2.extract_info(video_url, download=False)
                        except Exception as e2:
                            logger.warning(f"Second extraction method failed: {str(e2)}")
                            try:
                                # Try with web client and minimal options
                                ydl_opts['extractor_args']['youtube']['player_client'] = ['web']
                                ydl_opts['extractor_args']['youtube']['player_skip'] = ['webpage']
                                with yt_dlp.YoutubeDL(ydl_opts) as ydl3:
                                    info_dict = ydl3.extract_info(video_url, download=False)
                            except Exception as e3:
                                logger.error(f"All extraction methods failed: {str(e3)}")
                                if attempt < max_retries - 1:
                                    time.sleep(2 ** attempt)
                                    continue
                                raise
                    
                    if not info_dict:
                        logger.error("No info dictionary returned")
                        if attempt < max_retries - 1:
                            time.sleep(2 ** attempt)
                            continue
                        return None, None, None
                    
                    formats = info_dict.get('formats', [])
                    logger.info(f"Found {len(formats)} formats")

                    video_quality_map = {}
                    best_audio = None
                    highest_bitrate = 0

                    for f in formats:
                        # Check for video formats
                        if f.get('vcodec') != 'none':
                            resolution = f.get('height')
                            if resolution is not None and resolution not in video_quality_map:
                                # Get the direct URL if available, otherwise use format_id
                                url = f.get('url')
                                if not url:
                                    # If no direct URL, try to get the format URL
                                    try:
                                        format_url = ydl.urlopen(f['url']).geturl()
                                        url = format_url
                                    except:
                                        continue
                                video_quality_map[resolution] = url
                        
                        # Check for audio formats
                        if f.get('acodec') != 'none' and f.get('abr') is not None:
                            bitrate = f.get('abr')
                            if bitrate > highest_bitrate:
                                url = f.get('url')
                                if url:
                                    highest_bitrate = bitrate
                                    best_audio = url

                    video_quality_list = [{"resolution": res, "url": url} for res, url in video_quality_map.items()]
                    logger.info(f"Found {len(video_quality_list)} video qualities")

                    # Get the best video URL
                    best_video_url = None
                    if formats:
                        try:
                            best_info = ydl.extract_info(video_url, download=False)
                            if isinstance(best_info, dict):
                                best_video_url = best_info.get('url')
                                if not best_video_url and 'formats' in best_info:
                                    # Try to get URL from formats
                                    for f in best_info['formats']:
                                        if f.get('vcodec') != 'none':
                                            best_video_url = f.get('url')
                                            if best_video_url:
                                                break
                        except Exception as e:
                            logger.error(f"Error getting best video URL: {str(e)}")
                            best_video_url = None

                    return video_quality_list, best_audio, best_video_url

            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise

    except Exception as e:
        logger.error(f"Error in get_video_qualities: {str(e)}")
        return None, None, None


def get_video_url_by_quality(video_list, selected_quality):
    if not video_list:
        return None

    selected_resolution = selected_quality.rstrip('p')  # Remove 'p' from resolution if present
    for video in video_list:
        resolution = str(video['resolution']).rstrip('p') if video['resolution'] else None
        if resolution == selected_resolution:
            return video['url']
    return None


@app.route('/get_video_url', methods=['GET'])
def get_video_url():
    video_id = request.args.get('video_id')
    quality = request.args.get('quality')
    
    if not video_id:
        return jsonify({"error": "Video ID must be provided"}), 400

    video_url = f'https://www.youtube.com/watch?v={video_id}'
    logger.info(f"Processing request for video ID: {video_id}")
    
    try:
        video_qualities, best_audio_url, best_video_url = get_video_qualities(video_url)

        if video_qualities is None and best_audio_url is None and best_video_url is None:
            logger.error(f"Failed to extract video information for ID: {video_id}")
            return jsonify({
                "error": "Video is unavailable or restricted",
                "video_id": video_id,
                "message": "Could not extract video information. The video might be private, restricted, or unavailable in your region."
            }), 404

        response_data = {
            "best_audio_url": best_audio_url,
            "best_video_url": best_video_url,
            "video_quality_options": video_qualities
        }

        if quality:
            selected_video_url = get_video_url_by_quality(video_qualities, quality)
            if selected_video_url:
                response_data["selected_video_url"] = selected_video_url
            else:
                logger.warning(f"Requested quality {quality} not found for video ID: {video_id}")
                return jsonify({
                    "error": f"No URL found for quality {quality}",
                    "video_id": video_id,
                    "available_qualities": [q["resolution"] for q in video_qualities]
                }), 404

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Unexpected error processing video ID {video_id}: {str(e)}")
        return jsonify({
            "error": "An unexpected error occurred",
            "video_id": video_id,
            "message": str(e)
        }), 500

        
@app.route('/keep-alive', methods=['GET'])
def keep_alive():
    return jsonify({"success": True})


@app.route('/get-short-url', methods=['GET'])
def get_short_url():
    video_id = request.args.get('video_id')
    if not video_id:
        return jsonify({"error": "Video ID must be provided"}), 400

    video_url = f'https://www.youtube.com/watch?v={video_id}'
    _, _, best_video_url = get_video_qualities(video_url)

    if best_video_url is None:
        return jsonify({"error": "Video is unavailable or restricted"}), 404

    return jsonify({"stream_url": best_video_url})


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8111)
