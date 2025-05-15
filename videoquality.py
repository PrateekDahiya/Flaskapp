from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
from yt_dlp.utils import ExtractorError, DownloadError
import logging
import os
import browser_cookie3

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_youtube_cookies():
    try:
        # Try to get cookies from Chrome
        cookies = browser_cookie3.chrome(domain_name='.youtube.com')
        cookie_dict = {cookie.name: cookie.value for cookie in cookies}
        return cookie_dict
    except Exception as e:
        logger.error(f"Error getting cookies: {str(e)}")
        return None

def get_video_qualities(video_url):
    cookies = get_youtube_cookies()
    
    ydl_opts = {
        'listformats': True,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    if cookies:
        ydl_opts['cookies'] = cookies
        logger.info("Using browser cookies for authentication")
    else:
        logger.warning("No cookies available, trying without authentication")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Attempting to extract info for URL: {video_url}")
            info_dict = ydl.extract_info(video_url, download=False)
            
            if not info_dict:
                logger.error("No info dictionary returned")
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
                # Try to get the best video format
                best_video_opts = {
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                    'quiet': True,
                }
                if cookies:
                    best_video_opts['cookies'] = cookies
                    
                with yt_dlp.YoutubeDL(best_video_opts) as best_ydl:
                    try:
                        best_info = best_ydl.extract_info(video_url, download=False)
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
